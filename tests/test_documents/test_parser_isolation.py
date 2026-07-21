from pathlib import Path
import uuid

import pytest
from openpyxl import Workbook
from PIL import Image
from pypdf import PdfWriter

from app.documents.current_parser import CurrentLoaderParser
from app.documents.jobs import ParseJobStatus, transition_job
from app.documents.malware import MalwareDetected, ScannerUnavailable, parse_clamav_result
from app.documents.parser_contract import ParseRequest
from app.documents.queue import ParseQueue
from app.documents.resource_inspector import (
    DocumentLimits,
    ResourceLimitExceeded,
    inspect_resources,
)
from app.documents.storage import DocumentStorage


def test_parse_job_state_machine_is_fail_closed():
    transition_job(ParseJobStatus.QUARANTINED, ParseJobStatus.SCANNING)
    transition_job(ParseJobStatus.SCANNING, ParseJobStatus.PARSING)
    transition_job(ParseJobStatus.PARSING, ParseJobStatus.READY_FOR_REVIEW)
    with pytest.raises(ValueError):
        transition_job(ParseJobStatus.FAILED, ParseJobStatus.PARSING)
    with pytest.raises(ValueError):
        transition_job(ParseJobStatus.INFECTED, ParseJobStatus.READY_FOR_REVIEW)


def test_storage_uses_opaque_zone_keys_and_preserves_evidence(tmp_path):
    storage = DocumentStorage(tmp_path)
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    key = storage.allocate_quarantine_key(document_id, version_id, ".pdf")
    assert key == f"quarantine/{document_id}/{version_id}.pdf"
    with pytest.raises(ValueError):
        storage.resolve("../outside")
    source = storage.resolve(key)
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.7\n%%EOF")
    original = storage.copy_original(key, document_id, version_id, ".pdf")
    assert storage.resolve(original).exists()
    assert source.exists()


def test_clamav_results_fail_closed():
    parse_clamav_result({"stream": ("OK", None)})
    with pytest.raises(MalwareDetected, match="Eicar"):
        parse_clamav_result({"stream": ("FOUND", "Eicar-Test-Signature")})
    with pytest.raises(ScannerUnavailable):
        parse_clamav_result(None)


def _limits():
    return DocumentLimits(50_000_000, 2, 100, 100, 10, 10, 20)


def test_rejects_image_pixel_bomb(tmp_path):
    path = tmp_path / "large.png"
    Image.new("RGB", (101, 101)).save(path)
    with pytest.raises(ResourceLimitExceeded, match="图像"):
        inspect_resources(path, _limits())


def test_rejects_spreadsheet_shape(tmp_path):
    path = tmp_path / "large.xlsx"
    workbook = Workbook()
    workbook.active.cell(row=11, column=1, value="x")
    workbook.save(path)
    with pytest.raises(ResourceLimitExceeded, match="工作表"):
        inspect_resources(path, _limits())


def test_rejects_pdf_over_page_limit(tmp_path):
    path = tmp_path / "large.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as output:
        writer.write(output)
    with pytest.raises(ResourceLimitExceeded, match="页数"):
        inspect_resources(path, _limits())


def test_current_parser_contract_is_local_only(tmp_path):
    path = tmp_path / "manual.txt"
    path.write_text("阿司匹林适应症", encoding="utf-8")
    request = ParseRequest("job-1", "version-1", path, "txt")
    result = CurrentLoaderParser().parse(request)
    assert result.text == "阿司匹林适应症"
    assert result.parser_name == "current-loaders"
    assert not hasattr(request, "url")


def test_queue_submits_only_job_id():
    class RecordingQueue:
        def __init__(self):
            self.args = None

        def enqueue(self, function, *args, **kwargs):
            self.args = (function, args, kwargs)
            return type("Job", (), {"id": "rq-1"})()

    backend = RecordingQueue()
    assert ParseQueue(backend).submit("parse-job-id") == "rq-1"
    assert backend.args[1] == ("parse-job-id",)
    assert all(not isinstance(value, Path) for value in backend.args[1])
