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
    get_document_validator,
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
        "security": {"max_upload_bytes": 1024 * 1024},
    }
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_config_dep] = lambda: config
    app.dependency_overrides[get_document_validator] = lambda: AcceptingValidator()
    app.dependency_overrides[get_document_sync] = lambda: sync
    editor = _principal(editor_id, "editor", department_id, Role.KNOWLEDGE_EDITOR)
    reviewer = _principal(
        reviewer_id, "reviewer", department_id, Role.KNOWLEDGE_REVIEWER
    )
    return session, sync, editor, reviewer, department_id


def _cleanup(session):
    for dependency in (
        get_db_session,
        get_config_dep,
        get_document_validator,
        get_document_sync,
        get_current_principal,
        get_reauthenticated_principal,
    ):
        app.dependency_overrides.pop(dependency, None)
    session.close()


def test_uuid_document_review_and_index_flow(tmp_path):
    session, sync, editor, reviewer, department_id = _setup(tmp_path)
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
        assert uploaded.status_code == 201, uploaded.text
        document_id = uploaded.json()["document_id"]
        assert uploaded.json()["status"] == "draft"
        assert sync.indexed == []

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
    session, _, editor, _, _ = _setup(tmp_path)
    try:
        app.dependency_overrides[get_current_principal] = lambda: editor
        response = TestClient(app).get(
            f"/api/v1/documents/{uuid.uuid4()}"
        )
        assert response.status_code == 404
    finally:
        _cleanup(session)
