from __future__ import annotations

import hashlib
import os
import socket
import signal
from contextlib import contextmanager
from pathlib import Path

from app.core.config import get_config
from app.core.exceptions import FileSecurityError
from app.documents.high_fidelity_parser import HighFidelityParser
from app.documents.file_safety import inspect_file
from app.documents.job_repository import ParseJobRepository
from app.documents.jobs import ParseJobStatus
from app.documents.malware import MalwareDetected, ScannerUnavailable
from app.documents.models import KnowledgeDocumentVersion
from app.documents.parser_contract import ParseRequest
from app.documents.resource_inspector import (
    DocumentLimits,
    ResourceInspectionFailed,
    ResourceLimitExceeded,
    inspect_resources,
)
from app.documents.storage import DocumentStorage
from app.security.database import build_engine, build_session_factory


class ParseWorker:
    def __init__(
        self,
        session,
        storage,
        scanner,
        parser,
        limits,
        worker_id,
        inspector=inspect_resources,
        parser_timeout_seconds: int = 600,
    ):
        self.session = session
        self.storage = storage
        self.scanner = scanner
        self.parser = parser
        self.limits = limits
        self.worker_id = worker_id
        self.inspector = inspector
        self.parser_timeout_seconds = parser_timeout_seconds

    def process(self, parse_job_id: str) -> None:
        repository = ParseJobRepository(self.session)
        job = repository.get(parse_job_id)
        if job is None or job.status != ParseJobStatus.QUARANTINED:
            return
        quarantine_path = self.storage.resolve(job.quarantine_storage_key)
        parsed_path = None
        original_path = None
        try:
            repository.transition(
                job.id, ParseJobStatus.SCANNING, worker_id=self.worker_id
            )
            self.scanner.scan(quarantine_path)
            detected_format = inspect_file(quarantine_path)
            self.inspector(quarantine_path, self.limits)
            repository.transition(job.id, ParseJobStatus.PARSING)
            with _deadline(self.parser_timeout_seconds):
                result = self.parser.parse(
                    ParseRequest(
                        job.id,
                        job.document_version_id,
                        quarantine_path,
                        detected_format,
                    )
                )
            _validate_parse_result(result)
            parsed_key = self.storage.write_parsed(
                job.document_id, job.document_version_id, result.text
            )
            parsed_path = self.storage.resolve(parsed_key)
            original_key = self.storage.copy_original(
                job.quarantine_storage_key,
                job.document_id,
                job.document_version_id,
                quarantine_path.suffix.lower(),
            )
            original_path = self.storage.resolve(original_key)
            locked = repository.get(job.id, lock=True)
            version = self.session.get(
                KnowledgeDocumentVersion, job.document_version_id
            )
            if locked is None or version is None:
                raise RuntimeError("document parse state missing")
            locked.parsed_storage_key = parsed_key
            locked.content_hash = _file_hash(quarantine_path)
            locked.parser_name = result.parser_name
            locked.parser_version = result.parser_version
            version.storage_key = original_key
            self.session.commit()
            repository.transition(job.id, ParseJobStatus.READY_FOR_REVIEW)
        except MalwareDetected:
            repository.transition(
                job.id,
                ParseJobStatus.INFECTED,
                error_code="MALWARE_DETECTED",
            )
        except ScannerUnavailable:
            repository.transition(
                job.id,
                ParseJobStatus.FAILED,
                error_code="MALWARE_SCANNER_UNAVAILABLE",
            )
        except ResourceLimitExceeded:
            repository.transition(
                job.id,
                ParseJobStatus.FAILED,
                error_code="RESOURCE_LIMIT_EXCEEDED",
            )
        except ResourceInspectionFailed:
            repository.transition(
                job.id,
                ParseJobStatus.FAILED,
                error_code="RESOURCE_INSPECTION_FAILED",
            )
        except FileSecurityError:
            repository.transition(
                job.id,
                ParseJobStatus.FAILED,
                error_code="FILE_STRUCTURE_REJECTED",
            )
        except TimeoutError:
            repository.transition(
                job.id,
                ParseJobStatus.FAILED,
                error_code="PARSER_TIMEOUT",
            )
        except Exception:
            self.session.rollback()
            current = repository.get(job.id)
            if current and current.status in {
                ParseJobStatus.SCANNING,
                ParseJobStatus.PARSING,
            }:
                repository.transition(
                    job.id,
                    ParseJobStatus.FAILED,
                    error_code="PARSER_FAILED",
                )
        finally:
            current = repository.get(job.id)
            if current and current.status != ParseJobStatus.READY_FOR_REVIEW:
                if parsed_path:
                    parsed_path.unlink(missing_ok=True)
                if original_path:
                    original_path.unlink(missing_ok=True)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_parse_result(result) -> None:
    if not isinstance(result.text, str) or not result.text.strip():
        raise ValueError("parser returned empty output")
    if not isinstance(result.parser_name, str) or not result.parser_name.strip():
        raise ValueError("parser returned invalid name")
    if len(result.parser_name) > 128:
        raise ValueError("parser name exceeds storage limit")
    if not isinstance(result.parser_version, str) or not result.parser_version.strip():
        raise ValueError("parser returned invalid version")
    if len(result.parser_version) > 64:
        raise ValueError("parser version exceeds storage limit")


@contextmanager
def _deadline(seconds: int):
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def expired(_signum, _frame):
        raise TimeoutError("parser deadline exceeded")

    try:
        previous = signal.signal(signal.SIGALRM, expired)
    except ValueError:
        yield
        return
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _limits(config: dict) -> DocumentLimits:
    parser = config["parser"]
    security = config["security"]
    return DocumentLimits(
        security["max_upload_bytes"],
        parser["max_pdf_pages"],
        parser["max_image_width"],
        parser["max_image_height"],
        parser["max_sheet_rows"],
        parser["max_sheet_columns"],
        parser["max_nonempty_cells"],
        security["max_archive_uncompressed_bytes"],
        security["max_archive_ratio"],
    )


def process_parse_job(parse_job_id: str) -> None:
    import clamd

    from app.documents.malware import ClamAvScanner

    config = get_config()
    scanner = ClamAvScanner(
        clamd.ClamdNetworkSocket(
            host=config["parser"]["clamav_host"],
            port=config["parser"]["clamav_port"],
            timeout=30,
        )
    )
    session_factory = build_session_factory(
        build_engine(config["database"]["url"])
    )
    with session_factory() as session:
        ParseWorker(
            session,
            DocumentStorage(Path(config["storage"]["root"])),
            scanner,
            HighFidelityParser(),
            _limits(config),
            os.getenv("RQ_WORKER_ID", socket.gethostname()),
            parser_timeout_seconds=config["parser"]["timeout_seconds"],
        ).process(parse_job_id)
