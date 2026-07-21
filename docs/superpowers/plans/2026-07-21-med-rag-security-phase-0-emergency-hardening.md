# Med-Rag Security Phase 0 Emergency Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Immediately close path traversal, unsafe upload, management endpoint exposure, permissive CORS, and internal error leakage before the full identity system is introduced.

**Architecture:** Add small, dependency-free file safety primitives and a temporary environment-backed management credential around the existing filesystem document workflow. Fail closed on missing security configuration, stream uploads to bounded temporary files, and keep public error messages stable while retaining detailed server-side logs.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic-compatible dataclasses, pypdf, zipfile, pytest, Vue 3 client compatibility

---

## File Structure

- Create `app/security/__init__.py`: security package exports.
- Create `app/security/bootstrap_auth.py`: temporary constant-time management credential dependency.
- Create `app/documents/file_safety.py`: filename, path, signature, archive, PDF, and upload-limit checks.
- Modify `app/core/config.py`: emergency security and CORS settings.
- Modify `app/core/exceptions.py`: stable security error types.
- Modify `app/api/middleware.py`: stable status mapping and redacted exception logging.
- Modify `app/api/chat_routes.py`: remove raw exception text from SSE.
- Modify `app/api/documents.py`: stream uploads and use safe paths.
- Modify `app/api/evaluation.py`: protect operational endpoints.
- Modify `app/api/health.py`: protect engine metadata.
- Modify `app/main.py`: restricted CORS.
- Modify `.env.example`: required bootstrap credential and origin configuration.
- Test `tests/test_core/test_security_config.py`.
- Test `tests/test_documents/test_file_safety.py`.
- Test `tests/test_api/test_document_security.py`.
- Test `tests/test_api/test_bootstrap_auth.py`.
- Test `tests/test_api/test_error_redaction.py`.

### Task 1: Add Emergency Security Configuration

**Files:**
- Create: `tests/test_core/test_security_config.py`
- Modify: `app/core/config.py`
- Modify: `config.yaml`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Write failing configuration tests**

```python
from app.core import config as config_module


def _reload(monkeypatch, **values):
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    if hasattr(config_module.get_config, "_cache"):
        del config_module.get_config._cache
    return config_module.get_config()


def test_security_defaults_fail_closed(monkeypatch):
    cfg = _reload(monkeypatch)
    assert cfg["security"]["bootstrap_admin_key"] == ""
    assert cfg["security"]["max_upload_bytes"] == 50 * 1024 * 1024
    assert cfg["security"]["max_archive_ratio"] == 100
    assert cfg["security"]["max_archive_uncompressed_bytes"] == 500 * 1024 * 1024


def test_security_environment_overrides(monkeypatch):
    cfg = _reload(
        monkeypatch,
        RAG_BOOTSTRAP_ADMIN_KEY="test-admin-key-32-characters-long",
        RAG_CORS_ORIGINS="http://localhost:3000,https://med.example.test",
    )
    assert cfg["security"]["bootstrap_admin_key"].startswith("test-admin")
    assert cfg["cors"]["allowed_origins"] == [
        "http://localhost:3000",
        "https://med.example.test",
    ]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_core/test_security_config.py -v`

Expected: FAIL with `KeyError: 'security'`.

- [ ] **Step 3: Add typed security defaults and environment parsing**

Add these sections to `DEFAULTS` in `app/core/config.py`:

```python
    "security": {
        "bootstrap_admin_key": "",
        "max_upload_bytes": 50 * 1024 * 1024,
        "max_archive_ratio": 100,
        "max_archive_uncompressed_bytes": 500 * 1024 * 1024,
        "max_archive_members": 10000,
    },
    "cors": {
        "allowed_origins": ["http://localhost:3000"],
    },
```

Add mappings and parsing:

```python
ENV_MAPPINGS.update({
    "RAG_BOOTSTRAP_ADMIN_KEY": ("security", "bootstrap_admin_key"),
    "RAG_CORS_ORIGINS": ("cors", "allowed_origins"),
})

INT_FIELDS.extend([
    ("security", "max_upload_bytes"),
    ("security", "max_archive_ratio"),
    ("security", "max_archive_uncompressed_bytes"),
    ("security", "max_archive_members"),
])
```

In `load_config()`, normalize the origin list after environment values are applied:

```python
    origins = config["cors"]["allowed_origins"]
    if isinstance(origins, str):
        config["cors"]["allowed_origins"] = [
            item.strip() for item in origins.split(",") if item.strip()
        ]
```

Add matching YAML keys to `config.yaml` and documented environment values to `.env.example`:

```dotenv
RAG_BOOTSTRAP_ADMIN_KEY=replace-with-at-least-32-random-characters
RAG_CORS_ORIGINS=http://localhost:3000
```

Pass both values into the application service in `docker-compose.yml` and require the management key at Compose rendering time:

```yaml
RAG_BOOTSTRAP_ADMIN_KEY: ${RAG_BOOTSTRAP_ADMIN_KEY:?RAG_BOOTSTRAP_ADMIN_KEY is required}
RAG_CORS_ORIGINS: ${RAG_CORS_ORIGINS:-http://localhost:3000}
```

- [ ] **Step 4: Run tests and verify pass**

Run: `pytest tests/test_core/test_security_config.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py config.yaml .env.example docker-compose.yml tests/test_core/test_security_config.py
git commit -m "security: add emergency hardening configuration"
```

### Task 2: Add Safe Filename and Path Primitives

**Files:**
- Create: `app/security/__init__.py`
- Create: `app/documents/file_safety.py`
- Create: `tests/test_documents/test_file_safety.py`

- [ ] **Step 1: Write failing path safety tests**

```python
from pathlib import Path

import pytest

from app.core.exceptions import FileSecurityError
from app.documents.file_safety import resolve_child, validate_client_filename


@pytest.mark.parametrize(
    "name",
    ["../secret.txt", "..\\secret.txt", "/etc/passwd", "C:\\Windows\\win.ini", "a/b.txt", "a\\b.txt"],
)
def test_rejects_path_like_filenames(name):
    with pytest.raises(FileSecurityError):
        validate_client_filename(name)


def test_accepts_plain_unicode_filename():
    assert validate_client_filename("阿司匹林说明书.pdf") == "阿司匹林说明书.pdf"


def test_resolve_child_cannot_escape_root(tmp_path):
    with pytest.raises(FileSecurityError):
        resolve_child(tmp_path, "../outside.txt")


def test_resolve_child_returns_resolved_path(tmp_path):
    result = resolve_child(tmp_path, "safe.txt")
    assert result == (tmp_path / "safe.txt").resolve()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_documents/test_file_safety.py -v`

Expected: FAIL because `app.documents.file_safety` does not exist.

- [ ] **Step 3: Add the security exception and path helpers**

Add to `app/core/exceptions.py`:

```python
class SecurityError(MedRagError):
    def __init__(self, message: str, code: str = "SECURITY_ERROR"):
        super().__init__(message, code=code)


class FileSecurityError(SecurityError):
    def __init__(self, message: str = "文件未通过安全检查"):
        super().__init__(message, code="FILE_SECURITY_REJECTED")
```

Create `app/documents/file_safety.py`:

```python
from __future__ import annotations

import re
import unicodedata
from pathlib import Path, PurePath

from app.core.exceptions import FileSecurityError

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def validate_client_filename(value: str | None) -> str:
    if not value:
        raise FileSecurityError("文件名不能为空")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized or normalized in {".", ".."}:
        raise FileSecurityError("文件名无效")
    if "/" in normalized or "\\" in normalized or _DRIVE_PREFIX.match(normalized):
        raise FileSecurityError("文件名不能包含路径")
    if PurePath(normalized).name != normalized:
        raise FileSecurityError("文件名不能包含路径")
    if any(ord(char) < 32 for char in normalized):
        raise FileSecurityError("文件名包含控制字符")
    return normalized


def resolve_child(root: Path, filename: str) -> Path:
    safe_name = validate_client_filename(filename)
    resolved_root = root.resolve()
    candidate = (resolved_root / safe_name).resolve()
    if candidate.parent != resolved_root:
        raise FileSecurityError("文件路径越界")
    return candidate
```

Create `app/security/__init__.py` with an empty module docstring:

```python
"""Med-Rag authentication, authorization, and safety controls."""
```

- [ ] **Step 4: Run tests and verify pass**

Run: `pytest tests/test_documents/test_file_safety.py -v`

Expected: all path safety tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/security/__init__.py app/core/exceptions.py app/documents/file_safety.py tests/test_documents/test_file_safety.py
git commit -m "security: reject unsafe document paths"
```

### Task 3: Validate Signatures, Archives, and Active PDF Content

**Files:**
- Modify: `app/documents/file_safety.py`
- Modify: `tests/test_documents/test_file_safety.py`

- [ ] **Step 1: Add failing content inspection tests**

```python
import io
import zipfile

import pytest

from app.core.exceptions import FileSecurityError
from app.documents.file_safety import inspect_file


def _write_zip(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_rejects_extension_signature_mismatch(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(FileSecurityError):
        inspect_file(path, "application/pdf")


def test_accepts_real_docx_structure(tmp_path):
    path = tmp_path / "manual.docx"
    _write_zip(path, {"[Content_Types].xml": "<Types/>", "word/document.xml": "<document/>"})
    assert inspect_file(path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document") == "docx"


def test_rejects_office_external_relationship(tmp_path):
    path = tmp_path / "manual.docx"
    relationship = '<Relationship TargetMode="External" Target="https://internal.example"/>'
    _write_zip(
        path,
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": "<document/>",
            "word/_rels/document.xml.rels": relationship,
        },
    )
    with pytest.raises(FileSecurityError, match="外部关系"):
        inspect_file(path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def test_rejects_office_embedded_object(tmp_path):
    path = tmp_path / "manual.docx"
    _write_zip(
        path,
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": "<document/>",
            "word/embeddings/oleObject1.bin": b"embedded executable",
        },
    )
    with pytest.raises(FileSecurityError, match="嵌入对象"):
        inspect_file(path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def test_rejects_pdf_javascript(tmp_path):
    path = tmp_path / "active.pdf"
    path.write_bytes(b"%PDF-1.7\n1 0 obj << /JavaScript (alert) >> endobj\n%%EOF")
    with pytest.raises(FileSecurityError, match="活动内容"):
        inspect_file(path, "application/pdf")
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/test_documents/test_file_safety.py -k "signature or docx or external or embedded or javascript" -v`

Expected: FAIL because `inspect_file` is not defined.

- [ ] **Step 3: Implement bounded file inspection**

Add to `app/documents/file_safety.py`:

```python
import zipfile

from app.core.config import get_config

_IMAGE_SIGNATURES = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".bmp": b"BM",
}
_OFFICE_MARKERS = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}


def _inspect_archive(path: Path, marker: str) -> None:
    cfg = get_config()["security"]
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > cfg["max_archive_members"]:
                raise FileSecurityError("压缩成员数量超限")
            total = sum(item.file_size for item in infos)
            compressed = max(1, sum(item.compress_size for item in infos))
            if total > cfg["max_archive_uncompressed_bytes"]:
                raise FileSecurityError("解压后文件过大")
            if total / compressed > cfg["max_archive_ratio"]:
                raise FileSecurityError("压缩比异常")
            names = {item.filename for item in infos}
            if marker not in names or "[Content_Types].xml" not in names:
                raise FileSecurityError("Office 文件结构无效")
            for item in infos:
                lowered_name = item.filename.lower()
                if "/embeddings/" in lowered_name or "oleobject" in lowered_name:
                    raise FileSecurityError("Office 文件包含嵌入对象")
                if lowered_name.endswith(".rels"):
                    content = archive.read(item).decode("utf-8", errors="ignore")
                    if 'TargetMode="External"' in content:
                        raise FileSecurityError("Office 文件包含外部关系")
                if lowered_name.endswith("vbaproject.bin"):
                    raise FileSecurityError("Office 文件包含宏")
    except zipfile.BadZipFile as exc:
        raise FileSecurityError("Office 文件结构无效") from exc


def inspect_file(path: Path, declared_mime: str | None) -> str:
    suffix = path.suffix.lower()
    size = path.stat().st_size
    if size <= 0:
        raise FileSecurityError("文件为空")
    if size > get_config()["security"]["max_upload_bytes"]:
        raise FileSecurityError("文件大小超过限制")
    with path.open("rb") as source:
        prefix = source.read(16)
    if suffix == ".pdf":
        if not prefix.startswith(b"%PDF-"):
            raise FileSecurityError("文件扩展名与内容不一致")
        with path.open("rb") as source:
            sample = source.read(2 * 1024 * 1024)
        if any(marker in sample for marker in (b"/JavaScript", b"/JS", b"/OpenAction", b"/Launch", b"/EmbeddedFiles", b"/Filespec")):
            raise FileSecurityError("PDF 包含活动内容")
        detected = "pdf"
    elif suffix in _OFFICE_MARKERS:
        _inspect_archive(path, _OFFICE_MARKERS[suffix])
        detected = suffix[1:]
    elif suffix in _IMAGE_SIGNATURES:
        expected = _IMAGE_SIGNATURES[suffix]
        signatures = expected if isinstance(expected, tuple) else (expected,)
        if not any(prefix.startswith(signature) for signature in signatures):
            raise FileSecurityError("文件扩展名与内容不一致")
        detected = suffix[1:]
    elif suffix in {".txt", ".md", ".csv"}:
        path.read_text(encoding="utf-8")
        detected = suffix[1:]
    else:
        raise FileSecurityError("不支持的文件格式")
    allowed_mimes = {
        "pdf": {"application/pdf"},
        "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        "pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
        "png": {"image/png"},
        "jpg": {"image/jpeg"},
        "jpeg": {"image/jpeg"},
        "tiff": {"image/tiff"},
        "bmp": {"image/bmp"},
        "txt": {"text/plain", "application/octet-stream"},
        "md": {"text/markdown", "text/plain", "application/octet-stream"},
        "csv": {"text/csv", "text/plain", "application/vnd.ms-excel"},
    }
    if declared_mime and declared_mime.lower() not in allowed_mimes[detected]:
        raise FileSecurityError("声明 MIME 与文件内容不一致")
    return detected
```

- [ ] **Step 4: Run inspection tests and verify pass**

Run: `pytest tests/test_documents/test_file_safety.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/documents/file_safety.py tests/test_documents/test_file_safety.py
git commit -m "security: inspect uploaded document structure"
```

### Task 4: Stream Uploads Through Safe Temporary Files

**Files:**
- Modify: `app/api/documents.py`
- Modify: `app/documents/validator.py`
- Create: `tests/test_api/test_document_security.py`

- [ ] **Step 1: Write failing route security tests**

```python
from fastapi.testclient import TestClient

from app.core.dependencies import get_config_dep, get_document_sync
from app.main import app

client = TestClient(app)


class RecordingSync:
    def __init__(self):
        self.names = []

    def sync_file(self, filename, force=False):
        self.names.append(filename)
        return 1


def _override(tmp_path):
    cfg = {
        "knowledge_dir": str(tmp_path),
        "security": {
            "max_upload_bytes": 128,
            "max_archive_ratio": 100,
            "max_archive_uncompressed_bytes": 1024,
            "max_archive_members": 100,
        },
    }
    app.dependency_overrides[get_config_dep] = lambda: cfg
    app.dependency_overrides[get_document_sync] = lambda: RecordingSync()


def test_upload_rejects_path_traversal_filename(tmp_path):
    _override(tmp_path)
    try:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("../escape.txt", b"medical content", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    assert not (tmp_path.parent / "escape.txt").exists()


def test_upload_rejects_body_over_limit(tmp_path):
    _override(tmp_path)
    try:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("large.txt", b"x" * 129, "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    assert response.json()["code"] == "FILE_SECURITY_REJECTED"


def test_delete_rejects_path_traversal(tmp_path):
    _override(tmp_path)
    try:
        response = client.delete("/api/v1/documents/..%2Foutside.txt")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code in {400, 404}
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_api/test_document_security.py -v`

Expected: at least the oversized upload test fails because the route reads the full body before enforcing a limit.

- [ ] **Step 3: Add a bounded upload helper**

Add to `app/api/documents.py`:

```python
import os
import uuid

from app.documents.file_safety import inspect_file, resolve_child, validate_client_filename


async def _save_bounded_upload(file: UploadFile, directory: Path, max_bytes: int) -> tuple[str, Path]:
    filename = validate_client_filename(file.filename)
    directory.mkdir(parents=True, exist_ok=True)
    destination = resolve_child(directory, filename)
    temporary = resolve_child(directory, f".upload-{uuid.uuid4().hex}.tmp")
    written = 0
    try:
        with temporary.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise FileSecurityError("文件大小超过限制")
                output.write(chunk)
        inspection_path = resolve_child(directory, f".inspect-{uuid.uuid4().hex}{destination.suffix}")
        os.replace(temporary, inspection_path)
        try:
            inspect_file(inspection_path, file.content_type)
            os.replace(inspection_path, destination)
        finally:
            inspection_path.unlink(missing_ok=True)
        return filename, destination
    finally:
        temporary.unlink(missing_ok=True)
```

Use `_save_bounded_upload()` in `/upload` and `/validate`. Replace every `knowledge_dir / filename` expression in sync and delete routes with `resolve_child(knowledge_dir, filename)`. Pass only the validated filename to `DocumentSync`.

Update `DocumentValidator.validate()` so content loading happens only after `inspect_file()` succeeds:

```python
        try:
            inspect_file(file_path, None)
        except FileSecurityError as exc:
            errors.append(exc.message)
            return ValidationResult(False, errors, warnings)
```

- [ ] **Step 4: Run route and existing document tests**

Run: `pytest tests/test_api/test_document_security.py tests/test_documents -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/documents.py app/documents/validator.py tests/test_api/test_document_security.py tests/test_documents
git commit -m "security: bound and validate document uploads"
```

### Task 5: Protect Management Endpoints With a Bootstrap Credential

**Files:**
- Create: `app/security/bootstrap_auth.py`
- Create: `tests/test_api/test_bootstrap_auth.py`
- Modify: `app/api/documents.py`
- Modify: `app/api/evaluation.py`
- Modify: `app/api/health.py`
- Modify: `tests/test_api/test_routes.py`
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: Write failing bootstrap authentication tests**

```python
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.dependencies import get_config_dep
from app.security.bootstrap_auth import require_bootstrap_admin


def _client(key):
    app = FastAPI()
    app.dependency_overrides[get_config_dep] = lambda: {
        "security": {"bootstrap_admin_key": key}
    }

    @app.get("/protected")
    def protected(_: None = require_bootstrap_admin):
        return {"ok": True}

    return TestClient(app)


def test_missing_server_key_fails_closed():
    response = _client("").get("/protected")
    assert response.status_code == 503


def test_missing_request_key_is_unauthorized():
    response = _client("a" * 32).get("/protected")
    assert response.status_code == 401


def test_valid_request_key_is_accepted():
    response = _client("a" * 32).get("/protected", headers={"X-Med-Rag-Admin-Key": "a" * 32})
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_api/test_bootstrap_auth.py -v`

Expected: FAIL because `app.security.bootstrap_auth` does not exist.

- [ ] **Step 3: Implement constant-time bootstrap authentication**

Create `app/security/bootstrap_auth.py`:

```python
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException

from app.core.dependencies import get_config_dep


def verify_bootstrap_admin(
    x_med_rag_admin_key: str | None = Header(default=None),
    config: dict = Depends(get_config_dep),
) -> None:
    expected = config["security"]["bootstrap_admin_key"]
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="管理认证尚未配置")
    if x_med_rag_admin_key is None or not hmac.compare_digest(x_med_rag_admin_key, expected):
        raise HTTPException(status_code=401, detail="管理认证失败")


require_bootstrap_admin = Depends(verify_bootstrap_admin)
```

Add `dependencies=[Depends(verify_bootstrap_admin)]` to the documents and evaluation routers. Split `/health` into a public router and protect `/api/v1/engines` with the same dependency.

Update route tests to provide a dependency override with a 32-character key and use a shared header:

```python
ADMIN_HEADERS = {"X-Med-Rag-Admin-Key": "t" * 32}
```

Every documents, evaluation, and engines request must pass `headers=ADMIN_HEADERS`. Add explicit tests that those routes return `401` without it.

- [ ] **Step 4: Run API and smoke tests**

Run: `pytest tests/test_api tests/test_smoke.py -v`

Expected: all tests pass; protected endpoints return 401 without the header and preserve their existing response with it.

- [ ] **Step 5: Commit**

```bash
git add app/security/bootstrap_auth.py app/api/documents.py app/api/evaluation.py app/api/health.py tests/test_api tests/test_smoke.py
git commit -m "security: protect management endpoints"
```

### Task 6: Redact Errors and Restrict CORS

**Files:**
- Modify: `app/api/middleware.py`
- Modify: `app/api/chat_routes.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_error_redaction.py`
- Modify: `tests/test_api/test_routes.py`

- [ ] **Step 1: Write failing redaction and CORS tests**

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_unhandled_error_never_returns_exception_text(monkeypatch):
    from app.api import chat_routes

    def explode():
        raise RuntimeError("postgresql://admin:secret@internal-db/private")

    monkeypatch.setattr(chat_routes, "get_chat_orchestrator", explode)
    body = client.get("/api/v1/chat/stream?question=test").text
    assert "secret" not in body
    assert "internal-db" not in body
    assert "INTERNAL_ERROR" in body


def test_unknown_cors_origin_is_not_allowed():
    response = client.options(
        "/health",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") is None
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_api/test_error_redaction.py -v`

Expected: FAIL because the SSE route returns `str(e)` and CORS allows every origin.

- [ ] **Step 3: Replace raw errors and configure exact origins**

In `app/api/chat_routes.py`, replace the broad exception event with:

```python
        except Exception:
            yield 'event: error\ndata: {"code":"INTERNAL_ERROR","message":"内部服务异常，请稍后重试"}\n\n'
```

In `app/api/middleware.py`, add the new status code and avoid logging user-controlled business messages at warning level:

```python
        "FILE_SECURITY_REJECTED": 400,
        "SECURITY_ERROR": 403,
```

Log `code`, `path`, and `request_id` only. Keep traceback logging for unhandled errors, but configure production log collection as access-controlled in deployment documentation.

In `app/main.py`, replace wildcard CORS configuration:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=config["cors"]["allowed_origins"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Med-Rag-Admin-Key", "X-CSRF-Token"],
)
```

- [ ] **Step 4: Run security and route tests**

Run: `pytest tests/test_api/test_error_redaction.py tests/test_api/test_routes.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/middleware.py app/api/chat_routes.py app/main.py tests/test_api/test_error_redaction.py tests/test_api/test_routes.py
git commit -m "security: redact errors and restrict cors"
```

### Task 7: Verify the Emergency Release Gate

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-21-med-rag-input-security-design.md` only when observed behavior requires a factual clarification.

- [ ] **Step 1: Run static checks**

Run: `ruff check app tests`

Expected: exit code 0.

- [ ] **Step 2: Run the complete backend suite**

Run: `pytest tests/ -v`

Expected: all tests pass.

- [ ] **Step 3: Build the frontend**

Run: `cd frontend && npm run build`

Expected: Vite exits with code 0 and writes `frontend/dist`.

- [ ] **Step 4: Verify production configuration fails closed**

Run: `RAG_BOOTSTRAP_ADMIN_KEY=0123456789abcdef0123456789abcdef docker compose config`

Expected: configuration renders without syntax errors and requires `RAG_BOOTSTRAP_ADMIN_KEY` to be provided through the deployment environment.

- [ ] **Step 5: Document the temporary credential and migration boundary**

Add to `README.md`:

```markdown
### Temporary management authentication

Until the Phase 1 identity service is deployed, document, evaluation, and engine-management APIs require `X-Med-Rag-Admin-Key`. Set `RAG_BOOTSTRAP_ADMIN_KEY` to at least 32 random characters. Do not expose this value to browser users outside the trusted administration deployment. Phase 1 replaces this header with user authentication and department-scoped RBAC.
```

- [ ] **Step 6: Commit release verification documentation**

```bash
git add README.md
git commit -m "docs: document emergency management authentication"
```

## Completion Criteria

- Path-like filenames cannot escape the knowledge directory through upload, validate, sync, or delete routes.
- Uploads are streamed and rejected before exceeding configured limits.
- File extension and internal structure mismatches are rejected.
- Documents, evaluation, and engine metadata endpoints require the temporary management credential.
- Unknown CORS origins receive no allow-origin header.
- SSE and JSON errors never expose raw exception text.
- `ruff check app tests`, `pytest tests/ -v`, and `npm run build` all pass.
