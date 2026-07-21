import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.documents.jobs import ParseJob, ParseJobStatus
from app.documents.malware import MalwareDetected, ScannerUnavailable
from app.documents.models import (
    DocumentVisibility,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    ReviewStatus,
)
from app.documents.parser_contract import ParseResult
from app.documents.resource_inspector import DocumentLimits
from app.documents.storage import DocumentStorage
from app.documents.worker import ParseWorker
from app.security.database import Base
from app.security.models import Department, User


def _harness(tmp_path, scanner_error=None, parser_error=None, parser_result=None):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    department_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    storage = DocumentStorage(tmp_path)
    quarantine_key = storage.allocate_quarantine_key(
        document_id, version_id, ".txt"
    )
    quarantine = storage.resolve(quarantine_key)
    quarantine.parent.mkdir(parents=True)
    quarantine.write_text("阿司匹林适应症说明", encoding="utf-8")
    session.add_all(
        [
            Department(id=department_id, name="药学部"),
            User(id=user_id, username="editor", password_hash="hash"),
            KnowledgeDocument(
                id=document_id,
                owner_department_id=department_id,
                visibility=DocumentVisibility.DEPARTMENT_ONLY,
                created_by=user_id,
            ),
            KnowledgeDocumentVersion(
                id=version_id,
                document_id=document_id,
                version_number=1,
                display_name="manual.txt",
                storage_key=quarantine_key,
                file_hash="a" * 64,
                extension=".txt",
                size=10,
                status=ReviewStatus.DRAFT,
                created_by=user_id,
                last_edited_by=user_id,
            ),
            ParseJob(
                id=job_id,
                document_id=document_id,
                document_version_id=version_id,
                quarantine_storage_key=quarantine_key,
                status=ParseJobStatus.QUARANTINED,
            ),
        ]
    )
    session.commit()
    calls = []

    class Scanner:
        def scan(self, _path):
            calls.append("scan")
            if scanner_error:
                raise scanner_error

    class Parser:
        def parse(self, _request):
            calls.append("parse")
            if parser_error:
                raise parser_error
            return parser_result or ParseResult(
                "parsed medical text", "test-parser", "1"
            )

    def inspector(_path, _limits):
        calls.append("inspect")

    worker = ParseWorker(
        session,
        storage,
        Scanner(),
        Parser(),
        DocumentLimits(1000, 2, 100, 100, 10, 10, 20),
        "worker-1",
        inspector,
    )
    return session, storage, worker, job_id, version_id, calls


def test_worker_scans_inspects_and_parses_in_order(tmp_path):
    session, storage, worker, job_id, version_id, calls = _harness(tmp_path)
    try:
        worker.process(job_id)
        job = session.get(ParseJob, job_id)
        assert calls == ["scan", "inspect", "parse"]
        assert job.status == ParseJobStatus.READY_FOR_REVIEW
        assert storage.resolve(job.parsed_storage_key).read_text() == "parsed medical text"
        assert storage.resolve(f"original/{job.document_id}/{version_id}.txt").exists()
        assert storage.resolve(job.quarantine_storage_key).exists()
    finally:
        session.close()


def test_scanner_outage_never_calls_parser(tmp_path):
    session, _, worker, job_id, _, calls = _harness(
        tmp_path, ScannerUnavailable("offline")
    )
    try:
        worker.process(job_id)
        job = session.get(ParseJob, job_id)
        assert calls == ["scan"]
        assert job.status == ParseJobStatus.FAILED
        assert job.error_code == "MALWARE_SCANNER_UNAVAILABLE"
    finally:
        session.close()


def test_infected_file_never_leaves_quarantine(tmp_path):
    session, storage, worker, job_id, version_id, calls = _harness(
        tmp_path, MalwareDetected("Eicar-Test-Signature")
    )
    try:
        worker.process(job_id)
        job = session.get(ParseJob, job_id)
        assert calls == ["scan"]
        assert job.status == ParseJobStatus.INFECTED
        assert job.error_code == "MALWARE_DETECTED"
        assert not storage.resolve(
            f"original/{job.document_id}/{version_id}.txt"
        ).exists()
        assert storage.resolve(job.quarantine_storage_key).exists()
    finally:
        session.close()


def test_parser_timeout_is_safe_terminal_failure(tmp_path):
    session, _, worker, job_id, _, calls = _harness(
        tmp_path, parser_error=TimeoutError("deadline")
    )
    try:
        worker.process(job_id)
        job = session.get(ParseJob, job_id)
        assert calls == ["scan", "inspect", "parse"]
        assert job.status == ParseJobStatus.FAILED
        assert job.error_code == "PARSER_TIMEOUT"
    finally:
        session.close()


def test_malformed_parser_output_never_becomes_reviewable(tmp_path):
    session, _, worker, job_id, _, calls = _harness(
        tmp_path, parser_result=ParseResult("", "test-parser", "1")
    )
    try:
        worker.process(job_id)
        job = session.get(ParseJob, job_id)
        assert calls == ["scan", "inspect", "parse"]
        assert job.status == ParseJobStatus.FAILED
        assert job.error_code == "PARSER_FAILED"
    finally:
        session.close()
