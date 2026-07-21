# Med-Rag Security Phase 3 Parser Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move untrusted document parsing out of the API process into a quarantined, resource-bounded worker with malware scanning, durable job state, and fail-closed publication rules.

**Architecture:** The API streams files into a quarantine zone, records a PostgreSQL job, and submits only opaque IDs to Redis Queue. An internal worker obtains paths from trusted storage metadata, requires a successful ClamAV scan and resource inspection, runs the current format loader without network access, and writes parsed output to a separate zone before a reviewer can publish it.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Redis Queue, Redis, ClamAV, Docker Compose internal networks, existing document loaders, pytest, Vue 3

---

**Prerequisite:** Complete `2026-07-21-med-rag-security-phase-2-safety-gateway.md`.

## File Structure

- Create `app/documents/jobs.py`: parse job ORM model and status enum.
- Create `app/documents/job_repository.py`: transactional state transitions.
- Create `app/documents/storage.py`: quarantine, original, parsed, and temporary zones.
- Create `app/documents/malware.py`: ClamAV adapter.
- Create `app/documents/resource_inspector.py`: page, pixel, archive, and spreadsheet limits.
- Create `app/documents/parser_contract.py`: parser request/result and adapter protocol.
- Create `app/documents/current_parser.py`: adapter around current registered loaders.
- Create `app/documents/worker.py`: isolated job entry point.
- Create `app/documents/queue.py`: RQ submission and status lookup.
- Create `migrations/versions/20260721_05_parse_jobs.py`.
- Create `deploy/parser-worker.Dockerfile`.
- Modify document workflow, API, Compose, deployment configuration, and frontend job states.

### Task 1: Define Durable Parse Job State

**Files:**
- Create: `app/documents/jobs.py`
- Create: `app/documents/job_repository.py`
- Create: `migrations/versions/20260721_05_parse_jobs.py`
- Create: `tests/test_documents/test_parse_jobs.py`

- [ ] **Step 1: Write failing transition tests**

```python
import pytest

from app.documents.jobs import ParseJobStatus, transition_job


def test_parse_job_happy_path():
    assert transition_job(ParseJobStatus.QUARANTINED, ParseJobStatus.SCANNING) is None
    assert transition_job(ParseJobStatus.SCANNING, ParseJobStatus.PARSING) is None
    assert transition_job(ParseJobStatus.PARSING, ParseJobStatus.READY_FOR_REVIEW) is None


def test_failed_job_is_terminal():
    with pytest.raises(ValueError):
        transition_job(ParseJobStatus.FAILED, ParseJobStatus.PARSING)


def test_infected_job_is_terminal():
    with pytest.raises(ValueError):
        transition_job(ParseJobStatus.INFECTED, ParseJobStatus.READY_FOR_REVIEW)
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_documents/test_parse_jobs.py -v`

Expected: FAIL because parse job models do not exist.

- [ ] **Step 3: Implement states, model, and repository**

```python
class ParseJobStatus(str, enum.Enum):
    QUARANTINED = "quarantined"
    SCANNING = "scanning"
    PARSING = "parsing"
    READY_FOR_REVIEW = "ready_for_review"
    INFECTED = "infected"
    FAILED = "failed"


ALLOWED_JOB_TRANSITIONS = {
    ParseJobStatus.QUARANTINED: {ParseJobStatus.SCANNING, ParseJobStatus.FAILED},
    ParseJobStatus.SCANNING: {ParseJobStatus.PARSING, ParseJobStatus.INFECTED, ParseJobStatus.FAILED},
    ParseJobStatus.PARSING: {ParseJobStatus.READY_FOR_REVIEW, ParseJobStatus.FAILED},
    ParseJobStatus.READY_FOR_REVIEW: set(),
    ParseJobStatus.INFECTED: set(),
    ParseJobStatus.FAILED: set(),
}


def transition_job(current: ParseJobStatus, target: ParseJobStatus) -> None:
    if target not in ALLOWED_JOB_TRANSITIONS[current]:
        raise ValueError(f"invalid parse job transition: {current.value} -> {target.value}")
```

The `ParseJob` ORM model stores ID, document/version IDs, quarantine storage key, parsed storage key, status, safe error code, attempt count, timestamps, worker ID, content hash, and parser name/version. It must not store raw file paths or exception text.

`ParseJobRepository.transition()` uses `SELECT FOR UPDATE`, verifies the state machine, sets timestamps, and commits once. Create the matching migration with indexes on version ID, status, and creation time.

- [ ] **Step 4: Run tests and migration**

Run: `alembic upgrade head && pytest tests/test_documents/test_parse_jobs.py -v`

Expected: migration succeeds and state tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/documents/jobs.py app/documents/job_repository.py migrations/versions/20260721_05_parse_jobs.py tests/test_documents/test_parse_jobs.py
git commit -m "feat: add durable document parse jobs"
```

### Task 2: Separate Storage Zones and Opaque Keys

**Files:**
- Create: `app/documents/storage.py`
- Modify: `app/core/config.py`
- Modify: `config.yaml`
- Modify: `.env.example`
- Create: `tests/test_documents/test_storage.py`

- [ ] **Step 1: Write failing storage boundary tests**

```python
from app.documents.storage import DocumentStorage


def test_storage_keys_do_not_include_original_filename(tmp_path):
    storage = DocumentStorage(tmp_path)
    key = storage.allocate_quarantine_key("document-id", "version-id", ".pdf")
    assert key == "quarantine/document-id/version-id.pdf"


def test_storage_cannot_resolve_escape_key(tmp_path):
    storage = DocumentStorage(tmp_path)
    try:
        storage.resolve("../outside")
    except ValueError as error:
        assert "invalid storage key" in str(error)
    else:
        raise AssertionError("escape key was accepted")


def test_copy_original_preserves_quarantine_evidence(tmp_path):
    storage = DocumentStorage(tmp_path)
    source = storage.resolve("quarantine/doc/ver.pdf")
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.7\n%%EOF")
    target = storage.copy_original("quarantine/doc/ver.pdf", "doc", "ver", ".pdf")
    assert target == "original/doc/ver.pdf"
    assert storage.resolve(target).exists()
    assert source.exists()
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_documents/test_storage.py -v`

Expected: FAIL because storage abstraction does not exist.

- [ ] **Step 3: Implement zone-aware storage**

```python
from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath


class DocumentStorage:
    ZONES = {"quarantine", "original", "parsed", "temporary"}

    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, key: str) -> Path:
        pure = PurePosixPath(key)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts or pure.parts[0] not in self.ZONES:
            raise ValueError("invalid storage key")
        candidate = (self.root / Path(*pure.parts)).resolve()
        if self.root not in candidate.parents:
            raise ValueError("invalid storage key")
        return candidate

    def allocate_quarantine_key(self, document_id: str, version_id: str, suffix: str) -> str:
        return f"quarantine/{document_id}/{version_id}{suffix}"

    def copy_original(self, source_key: str, document_id: str, version_id: str, suffix: str) -> str:
        source = self.resolve(source_key)
        target_key = f"original/{document_id}/{version_id}{suffix}"
        target = self.resolve(target_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        with source.open("rb") as input_file, temporary.open("xb") as output_file:
            shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary, target)
        return target_key
```

Add `storage.root` to configuration and map `RAG_STORAGE_ROOT`. The API container mounts all zones; the parser worker mounts quarantine read-only and parsed/temporary/original read-write. Only the isolated worker may copy a successfully scanned file into original storage. The quarantine copy remains available until the configured incident-retention cleanup runs.

- [ ] **Step 4: Run storage tests**

Run: `pytest tests/test_documents/test_storage.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/documents/storage.py app/core/config.py config.yaml .env.example tests/test_documents/test_storage.py
git commit -m "feat: isolate document storage zones"
```

### Task 3: Require Malware Scanning

**Files:**
- Modify: `pyproject.toml`
- Create: `app/documents/malware.py`
- Create: `tests/test_documents/test_malware.py`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Write failing scanner tests**

```python
import pytest

from app.documents.malware import MalwareDetected, ScannerUnavailable, parse_clamav_result


def test_clean_scan_result():
    assert parse_clamav_result({"stream": ("OK", None)}) is None


def test_infected_scan_result():
    with pytest.raises(MalwareDetected, match="Eicar"):
        parse_clamav_result({"stream": ("FOUND", "Eicar-Test-Signature")})


def test_missing_scan_result_fails_closed():
    with pytest.raises(ScannerUnavailable):
        parse_clamav_result(None)
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_documents/test_malware.py -v`

Expected: FAIL because malware adapter does not exist.

- [ ] **Step 3: Implement ClamAV adapter and service**

Add `"clamd>=1.0.2,<2.0"` to dependencies. Implement:

```python
class MalwareDetected(RuntimeError):
    pass


class ScannerUnavailable(RuntimeError):
    pass


def parse_clamav_result(result) -> None:
    if not result or "stream" not in result:
        raise ScannerUnavailable("malware scanner unavailable")
    status, signature = result["stream"]
    if status == "FOUND":
        raise MalwareDetected(signature or "unknown signature")
    if status != "OK":
        raise ScannerUnavailable("malware scanner unavailable")


class ClamAvScanner:
    def __init__(self, client):
        self.client = client

    def scan(self, path: Path) -> None:
        try:
            with path.open("rb") as source:
                parse_clamav_result(self.client.instream(source))
        except MalwareDetected:
            raise
        except Exception as exc:
            raise ScannerUnavailable("malware scanner unavailable") from exc
```

Add `clamav/clamav:1.4` on the internal parser network with a persistent signature volume and health check. Configure `StreamMaxLength 50M` so the scanner limit matches the application hard limit. Do not publish ClamAV ports to the host.

- [ ] **Step 4: Run scanner and Compose tests**

Run: `pytest tests/test_documents/test_malware.py -v && docker compose config`

Expected: tests pass and the internal ClamAV service renders.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml app/documents/malware.py tests/test_documents/test_malware.py docker-compose.yml
git commit -m "feat: require malware scanning for documents"
```

### Task 4: Enforce Deep Resource Limits

**Files:**
- Create: `app/documents/resource_inspector.py`
- Modify: `app/documents/file_safety.py`
- Create: `tests/test_documents/test_resource_inspector.py`

- [ ] **Step 1: Write failing resource-limit tests**

```python
import pytest
from openpyxl import Workbook
from PIL import Image

from app.documents.resource_inspector import DocumentLimits, ResourceLimitExceeded, inspect_resources


def limits():
    return DocumentLimits(50_000_000, 2, 100, 100, 10, 10, 20)


def test_rejects_image_pixel_bomb(tmp_path):
    path = tmp_path / "large.png"
    Image.new("RGB", (11, 11)).save(path)
    with pytest.raises(ResourceLimitExceeded, match="像素"):
        inspect_resources(path, limits())


def test_rejects_spreadsheet_shape(tmp_path):
    path = tmp_path / "large.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.cell(row=11, column=1, value="x")
    workbook.save(path)
    with pytest.raises(ResourceLimitExceeded, match="工作表"):
        inspect_resources(path, limits())
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_documents/test_resource_inspector.py -v`

Expected: FAIL because resource inspector does not exist.

- [ ] **Step 3: Implement per-format hard limits**

Define `DocumentLimits` fields for bytes, PDF pages, image width, image height, sheet rows, sheet columns, and nonempty cells. Use `pypdf.PdfReader` without extracting text, Pillow metadata without full raster conversion, `openpyxl.load_workbook(read_only=True, data_only=True)`, and Phase 0 ZIP aggregate checks.

Production limits must be exactly: 50 MB, 1000 PDF pages, 10000 x 10000 image dimensions, 200000 rows, 500 columns, 2000000 nonempty cells, 500 MB uncompressed, and 100:1 archive ratio. Any inspection exception not explicitly recognized as a clean result becomes `ResourceInspectionFailed` and keeps the file quarantined.

- [ ] **Step 4: Run resource tests**

Run: `pytest tests/test_documents/test_resource_inspector.py tests/test_documents/test_file_safety.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/documents/resource_inspector.py app/documents/file_safety.py tests/test_documents/test_resource_inspector.py
git commit -m "feat: enforce document resource limits"
```

### Task 5: Define the Parser Contract and Current Loader Adapter

**Files:**
- Create: `app/documents/parser_contract.py`
- Create: `app/documents/current_parser.py`
- Create: `tests/test_documents/test_parser_contract.py`

- [ ] **Step 1: Write failing adapter tests**

```python
from app.documents.current_parser import CurrentLoaderParser
from app.documents.parser_contract import ParseRequest


def test_current_parser_returns_safe_structured_result(tmp_path):
    path = tmp_path / "manual.txt"
    path.write_text("阿司匹林适应症", encoding="utf-8")
    result = CurrentLoaderParser().parse(ParseRequest("job-1", "version-1", path, "txt"))
    assert result.text == "阿司匹林适应症"
    assert result.parser_name == "current-loaders"
    assert result.parser_version == "1"


def test_parser_request_has_no_remote_uri(tmp_path):
    request = ParseRequest("job-1", "version-1", tmp_path / "manual.txt", "txt")
    assert not hasattr(request, "url")
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_documents/test_parser_contract.py -v`

Expected: FAIL because parser contract does not exist.

- [ ] **Step 3: Implement the local-only protocol**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ParseRequest:
    job_id: str
    document_version_id: str
    local_path: Path
    detected_format: str


@dataclass(frozen=True)
class ParseResult:
    text: str
    parser_name: str
    parser_version: str
    warnings: tuple[str, ...] = ()


class DocumentParser(Protocol):
    def parse(self, request: ParseRequest) -> ParseResult:
        raise NotImplementedError
```

`CurrentLoaderParser` verifies `request.local_path.is_file()`, calls the existing registry by local path, rejects empty output, and returns text. It does not accept a URL, plugin name, command, or arbitrary converter option. OCR and embedding model caches are pre-populated during image build or deployment; missing local model files produce a stable parser failure and never trigger a download.

- [ ] **Step 4: Run adapter tests**

Run: `pytest tests/test_documents/test_parser_contract.py tests/test_documents/test_loaders.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/documents/parser_contract.py app/documents/current_parser.py tests/test_documents/test_parser_contract.py
git commit -m "feat: define isolated parser contract"
```

### Task 6: Submit Opaque Jobs Through Redis Queue

**Files:**
- Modify: `pyproject.toml`
- Create: `app/documents/queue.py`
- Create: `tests/test_documents/test_parse_queue.py`

- [ ] **Step 1: Write failing queue tests**

```python
from app.documents.queue import ParseQueue


class RecordingQueue:
    def __init__(self):
        self.args = None

    def enqueue(self, function, *args, **kwargs):
        self.args = (function, args, kwargs)
        return type("Job", (), {"id": "rq-1"})()


def test_queue_submits_only_job_id():
    backend = RecordingQueue()
    queue = ParseQueue(backend)
    result = queue.submit("parse-job-id")
    assert result == "rq-1"
    assert backend.args[1] == ("parse-job-id",)
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_documents/test_parse_queue.py -v`

Expected: FAIL because queue adapter does not exist.

- [ ] **Step 3: Implement RQ adapter**

Add `"rq>=2.1,<3.0"` to dependencies. Implement:

```python
class ParseQueue:
    def __init__(self, queue):
        self.queue = queue

    def submit(self, parse_job_id: str) -> str:
        job = self.queue.enqueue(
            "app.documents.worker.process_parse_job",
            parse_job_id,
            job_timeout=660,
            result_ttl=86400,
            failure_ttl=604800,
        )
        return job.id
```

The API passes only the parse job UUID. The worker reloads every storage key, document ID, and policy value from PostgreSQL and configuration. Never enqueue a path, filename, URL, parser class, or shell argument.

- [ ] **Step 4: Run queue tests**

Run: `pytest tests/test_documents/test_parse_queue.py -v`

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml app/documents/queue.py tests/test_documents/test_parse_queue.py
git commit -m "feat: queue opaque document parse jobs"
```

### Task 7: Implement the Fail-Closed Worker

**Files:**
- Create: `app/documents/worker.py`
- Create: `tests/test_documents/test_parse_worker.py`

- [ ] **Step 1: Write failing worker flow tests**

```python
def test_worker_scans_before_parsing(worker_harness):
    worker_harness.process()
    assert worker_harness.calls == ["scan", "inspect", "parse", "write_result"]
    assert worker_harness.job.status.value == "ready_for_review"


def test_scanner_failure_never_calls_parser(worker_harness):
    worker_harness.scanner.fail_unavailable = True
    worker_harness.process()
    assert "parse" not in worker_harness.calls
    assert worker_harness.job.status.value == "failed"
    assert worker_harness.job.error_code == "MALWARE_SCANNER_UNAVAILABLE"


def test_infected_file_never_leaves_quarantine(worker_harness):
    worker_harness.scanner.signature = "Eicar-Test-Signature"
    worker_harness.process()
    assert worker_harness.job.status.value == "infected"
    assert not worker_harness.original_path.exists()
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_documents/test_parse_worker.py -v`

Expected: FAIL because worker does not exist.

- [ ] **Step 3: Implement the worker order and safe failures**

`process_parse_job(parse_job_id)` must:

1. Load and lock the quarantined job from PostgreSQL.
2. Resolve the quarantine key through `DocumentStorage`.
3. Transition to `scanning`.
4. Require ClamAV success.
5. Run signature and resource inspection.
6. Transition to `parsing`.
7. Call the configured `DocumentParser` with a local `ParseRequest`.
8. Write UTF-8 parsed text to `parsed/<document_id>/<version_id>.txt` with exclusive create and atomic rename.
9. Copy the scanned original into the original zone with `DocumentStorage.copy_original()`; retain the quarantine copy for controlled cleanup.
10. Store parser name/version and transition to `ready_for_review`.

Map infected, scanner unavailable, resource limit, parser timeout, empty output, and unexpected errors to stable codes. Log job ID and error class only. Ensure temporary files are removed in `finally`; never remove the quarantine file after a failure because it may be needed for controlled security investigation.

- [ ] **Step 4: Run worker tests**

Run: `pytest tests/test_documents/test_parse_worker.py -v`

Expected: all ordered-call and fail-closed tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/documents/worker.py tests/test_documents/test_parse_worker.py
git commit -m "feat: parse quarantined documents in worker"
```

### Task 8: Make Upload and Review Asynchronous

**Files:**
- Modify: `app/documents/service.py`
- Modify: `app/api/documents.py`
- Create: `tests/test_api/test_parse_jobs.py`

- [ ] **Step 1: Write failing API lifecycle tests**

```python
def test_upload_returns_accepted_parse_job(editor_client, sample_pdf):
    response = editor_client.post(
        "/api/v1/documents",
        data={"owner_department_id": "dept-a", "visibility": "department_only"},
        files={"file": ("manual.pdf", sample_pdf, "application/pdf")},
    )
    assert response.status_code == 202
    assert response.json()["processing_status"] == "quarantined"
    assert response.json()["parse_job_id"]


def test_draft_cannot_enter_review_before_parse_ready(editor_client, quarantined_document_id):
    response = editor_client.post(f"/api/v1/documents/{quarantined_document_id}/submit-review")
    assert response.status_code == 409
    assert response.json()["code"] == "DOCUMENT_NOT_PARSED"


def test_infected_job_details_are_not_exposed(editor_client, infected_job_id):
    response = editor_client.get(f"/api/v1/documents/jobs/{infected_job_id}")
    assert response.json()["status"] == "infected"
    assert "Eicar" not in response.text
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_api/test_parse_jobs.py -v`

Expected: upload still parses synchronously and returns 201.

- [ ] **Step 3: Integrate quarantine and job API**

`POST /api/v1/documents` streams to the opaque quarantine key, performs Phase 0 signature and size checks, creates document/version/job rows in one transaction, submits the job after commit, and returns 202. It does not load, OCR, chunk, embed, or index the file.

Add `GET /api/v1/documents/jobs/{job_id}` with owner-department read permission. Return only status, safe error code, parser name/version, and timestamps. `submit-review` requires `ready_for_review`; approval still performs indexing from the parsed artifact and preserves document ACL.

- [ ] **Step 4: Run API lifecycle tests**

Run: `pytest tests/test_api/test_parse_jobs.py tests/test_api/test_document_workflow.py -v`

Expected: all asynchronous lifecycle and workflow tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/documents/service.py app/api/documents.py tests/test_api/test_parse_jobs.py tests/test_api/test_document_workflow.py
git commit -m "feat: quarantine uploads before review"
```

### Task 9: Deploy a Restricted Parser Worker

**Files:**
- Create: `deploy/parser-worker.Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `Dockerfile`
- Modify: `deploy/start.sh`
- Create: `tests/test_deployment_security.py`

- [ ] **Step 1: Write a failing Compose policy test**

```python
import subprocess
import yaml


def test_parser_worker_is_restricted():
    rendered = subprocess.check_output(["docker", "compose", "config"], text=True)
    config = yaml.safe_load(rendered)
    worker = config["services"]["parser-worker"]
    assert worker["read_only"] is True
    assert worker["cap_drop"] == ["ALL"]
    assert worker["security_opt"] == ["no-new-privileges:true"]
    assert worker["pids_limit"] <= 256
    assert worker.get("ports") in (None, [])
    assert config["networks"]["parser-internal"]["internal"] is True
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_deployment_security.py -v`

Expected: FAIL because parser worker is not in Compose.

- [ ] **Step 3: Add restricted worker deployment**

`deploy/parser-worker.Dockerfile` installs only parsing dependencies, creates a non-root user, and runs `rq worker med-rag-parse`. Compose must set:

```yaml
parser-worker:
  build:
    context: .
    dockerfile: deploy/parser-worker.Dockerfile
  user: "10001:10001"
  read_only: true
  cap_drop: ["ALL"]
  security_opt: ["no-new-privileges:true"]
  pids_limit: 256
  mem_limit: 8g
  cpus: 4
  tmpfs:
    - /tmp:size=1g,noexec,nosuid,nodev
  networks: [parser-internal]
  volumes:
    - document_quarantine:/data/quarantine:ro
    - document_parsed:/data/parsed:rw
    - document_original:/data/original:rw
    - model_cache:/models:ro
```

The `parser-internal` network is `internal: true` and contains only the worker, Redis, PostgreSQL, and ClamAV. The worker has no published port, Docker socket, host path, or cloud credential. Add health-dependent startup without weakening fail-closed scanning.

- [ ] **Step 4: Run deployment tests**

Run: `pytest tests/test_deployment_security.py -v && docker compose config`

Expected: policy test and Compose validation pass.

- [ ] **Step 5: Commit**

```bash
git add deploy/parser-worker.Dockerfile docker-compose.yml Dockerfile deploy/start.sh tests/test_deployment_security.py
git commit -m "security: isolate document parser worker"
```

### Task 10: Add Processing Status UI and Release Gate

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/stores/document.js`
- Modify: `frontend/src/views/DocumentsView.vue`
- Create: `frontend/src/stores/document-jobs.spec.js`
- Create: `tests/test_documents/test_parser_release_gate.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing frontend state test**

```javascript
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDocumentStore } from './document'

describe('document processing jobs', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('marks infected jobs as non-retryable', () => {
    const store = useDocumentStore()
    store.applyJob({ id: 'job-1', status: 'infected', error_code: 'MALWARE_DETECTED' })
    expect(store.jobs['job-1'].canRetry).toBe(false)
  })
})
```

- [ ] **Step 2: Run and verify failure**

Run: `cd frontend && npm test -- document-jobs.spec.js`

Expected: FAIL because job state does not exist.

- [ ] **Step 3: Implement safe processing status UI**

Poll the job endpoint with exponential intervals of 1, 2, 4, then 8 seconds, capped at 8 seconds and stopped on terminal status or view unmount. Show `隔离检查中`, `安全扫描中`, `解析中`, `待审核`, `检测到风险`, or `处理失败`. Do not show malware signatures, paths, commands, stack traces, or worker IDs. Disable review and publish actions until ready.

- [ ] **Step 4: Add backend release scenarios**

`tests/test_documents/test_parser_release_gate.py` must cover a clean PDF, clean DOCX, fake-extension file, EICAR fixture, active PDF, external Office relationship, ZIP bomb metadata, over-page PDF, over-pixel image, scanner outage, parser timeout, and malformed parser output. Every unsafe case must remain unindexed and preserve a safe terminal status.

- [ ] **Step 5: Run all release checks**

Run: `ruff check app tests scripts && pytest tests/ -v && cd frontend && npm test && npm run build && docker compose config`

Expected: all commands exit 0.

- [ ] **Step 6: Document operations and commit**

Document quarantine retention, signature updates, worker resource tuning, incident access, retry rules, and safe cleanup in `README.md`.

```bash
git add frontend/src tests/test_documents/test_parser_release_gate.py README.md
git commit -m "test: gate isolated document parsing"
```

## Completion Criteria

- The API never parses uploaded content in-process.
- Every file remains quarantined until ClamAV, signature, and resource checks succeed.
- Scanner outage, infection, inspection ambiguity, timeout, and parser failure all fail closed.
- RQ payloads contain only opaque job IDs.
- The parser worker is non-root, read-only, capability-free, resource-bounded, and has no external network.
- Only ready-for-review parsed artifacts can enter the document approval flow.
- Unsafe files never enter Milvus, Whoosh, prompts, previews, or ordinary logs.
- Backend, frontend, deployment policy, and malicious-fixture release tests pass.
