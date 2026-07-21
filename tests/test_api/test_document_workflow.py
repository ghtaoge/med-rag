from pathlib import Path
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import (
    get_config_dep,
    get_db_session,
    get_document_sync,
    get_document_storage,
    get_document_validator,
    get_parse_queue,
)
from app.main import app
from app.security.database import Base
from app.security.models import Department, DepartmentMembership, Role, User
from app.security.principal import (
    Principal,
    PrincipalMembership,
    get_current_principal,
    get_reauthenticated_principal,
)
from app.documents.job_repository import ParseJobRepository
from app.documents.jobs import ParseJobStatus
from app.documents.storage import DocumentStorage


class AcceptingValidator:
    def validate(self, _path):
        return SimpleNamespace(is_valid=True, errors=[], warnings=[])


class RecordingSync:
    def __init__(self):
        self.indexed = []
        self.removed = []

    def sync_managed_version(self, path, source, metadata):
        self.indexed.append((path, source, metadata))
        return 3

    def remove_source(self, source):
        self.removed.append(source)


class RecordingQueue:
    def __init__(self):
        self.job_ids = []

    def submit(self, job_id):
        self.job_ids.append(job_id)
        return "rq-1"


def _principal(user_id, username, department_id, role):
    return Principal(
        user_id=user_id,
        username=username,
        memberships=(PrincipalMembership(department_id, role),),
        session_id=f"session-{user_id}",
    )


def _setup(tmp_path: Path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    department_id = str(uuid.uuid4())
    editor_id = str(uuid.uuid4())
    reviewer_id = str(uuid.uuid4())
    session.add_all(
        [
            Department(id=department_id, name="药学部"),
            User(id=editor_id, username="editor", password_hash="hash"),
            User(id=reviewer_id, username="reviewer", password_hash="hash"),
            DepartmentMembership(
                user_id=editor_id,
                department_id=department_id,
                role=Role.KNOWLEDGE_EDITOR,
            ),
            DepartmentMembership(
                user_id=reviewer_id,
                department_id=department_id,
                role=Role.KNOWLEDGE_REVIEWER,
            ),
        ]
    )
    session.commit()
    sync = RecordingSync()
    config = {
        "knowledge_dir": str(tmp_path),
        "storage": {"root": str(tmp_path)},
        "security": {"max_upload_bytes": 1024 * 1024},
    }
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_config_dep] = lambda: config
    app.dependency_overrides[get_document_validator] = lambda: AcceptingValidator()
    app.dependency_overrides[get_document_sync] = lambda: sync
    app.dependency_overrides[get_document_storage] = lambda: DocumentStorage(tmp_path)
    queue = RecordingQueue()
    app.dependency_overrides[get_parse_queue] = lambda: queue
    editor = _principal(editor_id, "editor", department_id, Role.KNOWLEDGE_EDITOR)
    reviewer = _principal(
        reviewer_id, "reviewer", department_id, Role.KNOWLEDGE_REVIEWER
    )
    return session, sync, queue, editor, reviewer, department_id


def _cleanup(session):
    for dependency in (
        get_db_session,
        get_config_dep,
        get_document_validator,
        get_document_sync,
        get_document_storage,
        get_parse_queue,
        get_current_principal,
        get_reauthenticated_principal,
    ):
        app.dependency_overrides.pop(dependency, None)
    session.close()


def test_uuid_document_review_and_index_flow(tmp_path):
    session, sync, queue, editor, reviewer, department_id = _setup(tmp_path)
    client = TestClient(app)
    try:
        app.dependency_overrides[get_current_principal] = lambda: editor
        uploaded = client.post(
            "/api/v1/documents",
            data={
                "owner_department_id": department_id,
                "visibility": "department_only",
            },
            files={"file": ("manual.txt", b"safe medical content", "text/plain")},
        )
        assert uploaded.status_code == 202, uploaded.text
        document_id = uploaded.json()["document_id"]
        version_id = uploaded.json()["version_id"]
        job_id = uploaded.json()["parse_job_id"]
        assert uploaded.json()["status"] == "draft"
        assert uploaded.json()["processing_status"] == "quarantined"
        assert queue.job_ids == [job_id]
        assert sync.indexed == []

        parsed_key = f"parsed/{document_id}/{version_id}.txt"
        parsed_path = DocumentStorage(tmp_path).resolve(parsed_key)
        parsed_path.parent.mkdir(parents=True, exist_ok=True)
        parsed_path.write_text("safe parsed medical content", encoding="utf-8")
        job = ParseJobRepository(session).get(job_id)
        job.status = ParseJobStatus.READY_FOR_REVIEW
        job.parsed_storage_key = parsed_key
        session.commit()

        submitted = client.post(
            f"/api/v1/documents/{document_id}/submit-review",
            json={"reason": "ready for review"},
        )
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "in_review"

        app.dependency_overrides[get_current_principal] = lambda: reviewer
        app.dependency_overrides[get_reauthenticated_principal] = lambda: reviewer
        approved = client.post(
            f"/api/v1/documents/{document_id}/approve",
            json={"reason": "verified"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert approved.json()["chunk_count"] == 3
        assert sync.indexed[0][2].visible_department_ids == (department_id,)
        assert sync.indexed[0][2].review_status == "approved"

        revoked = client.post(
            f"/api/v1/documents/{document_id}/revoke",
            json={"reason": "superseded"},
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        assert len(sync.removed) == 1
    finally:
        _cleanup(session)


def test_unknown_document_returns_404(tmp_path):
    session, _, _, editor, _, _ = _setup(tmp_path)
    try:
        app.dependency_overrides[get_current_principal] = lambda: editor
        response = TestClient(app).get(
            f"/api/v1/documents/{uuid.uuid4()}"
        )
        assert response.status_code == 404
    finally:
        _cleanup(session)


def test_quarantined_document_cannot_enter_review(tmp_path):
    session, _, _, editor, _, department_id = _setup(tmp_path)
    client = TestClient(app)
    try:
        app.dependency_overrides[get_current_principal] = lambda: editor
        uploaded = client.post(
            "/api/v1/documents",
            data={"owner_department_id": department_id},
            files={"file": ("manual.txt", b"safe medical content", "text/plain")},
        )
        assert uploaded.status_code == 202
        document_id = uploaded.json()["document_id"]
        response = client.post(
            f"/api/v1/documents/{document_id}/submit-review",
            json={"reason": "ready"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "DOCUMENT_NOT_PARSED"
    finally:
        _cleanup(session)


def test_infected_job_response_never_exposes_signature(tmp_path):
    session, _, _, editor, _, department_id = _setup(tmp_path)
    client = TestClient(app)
    try:
        app.dependency_overrides[get_current_principal] = lambda: editor
        uploaded = client.post(
            "/api/v1/documents",
            data={"owner_department_id": department_id},
            files={"file": ("manual.txt", b"safe medical content", "text/plain")},
        )
        job_id = uploaded.json()["parse_job_id"]
        job = ParseJobRepository(session).get(job_id)
        job.status = ParseJobStatus.INFECTED
        job.error_code = "MALWARE_DETECTED"
        session.commit()
        response = client.get(f"/api/v1/documents/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "infected"
        assert "Eicar" not in response.text
    finally:
        _cleanup(session)


def test_async_upload_rejects_fake_extension_before_queue(tmp_path):
    session, _, queue, editor, _, department_id = _setup(tmp_path)
    try:
        app.dependency_overrides[get_current_principal] = lambda: editor
        response = TestClient(app).post(
            "/api/v1/documents",
            data={"owner_department_id": department_id},
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "FILE_SECURITY_REJECTED"
        assert queue.job_ids == []
    finally:
        _cleanup(session)
