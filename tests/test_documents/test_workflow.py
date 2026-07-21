import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError
from app.documents.models import DocumentVisibility, ReviewStatus
from app.documents.service import DocumentWorkflowService
from app.security.database import Base
from app.security.models import Department, DepartmentMembership, Role, User
from app.security.principal import Principal, PrincipalMembership


def _principal(user_id: str, department_id: str, role: Role) -> Principal:
    return Principal(
        user_id=user_id,
        username=user_id,
        memberships=(PrincipalMembership(department_id, role),),
        session_id=f"session-{user_id}",
    )


def _workflow_fixture():
    engine = create_engine("sqlite://")
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
    return (
        session,
        DocumentWorkflowService(session),
        _principal(editor_id, department_id, Role.KNOWLEDGE_EDITOR),
        _principal(reviewer_id, department_id, Role.KNOWLEDGE_REVIEWER),
        department_id,
    )


def _draft(service, editor, department_id):
    document_id = str(uuid.uuid4())
    return service.create_draft(
        editor,
        document_id,
        str(uuid.uuid4()),
        department_id,
        DocumentVisibility.DEPARTMENT_ONLY,
        (),
        "manual.txt",
        f"{document_id}/version.txt",
        "a" * 64,
        ".txt",
        10,
        None,
        "request-1",
    )


def test_uploaded_document_starts_as_draft():
    session, service, editor, _, department_id = _workflow_fixture()
    try:
        _, version = _draft(service, editor, department_id)
        assert version.status == ReviewStatus.DRAFT
    finally:
        session.close()


def test_editor_cannot_approve_own_version():
    session, service, editor, _, department_id = _workflow_fixture()
    try:
        document, _ = _draft(service, editor, department_id)
        service.submit_review(editor, document.id, "ready", "request-2")
        elevated_editor = _principal(
            editor.user_id, department_id, Role.KNOWLEDGE_REVIEWER
        )
        with pytest.raises(AuthorizationError):
            service.approve(elevated_editor, document.id, "self", "request-3")
    finally:
        session.close()


def test_reviewer_can_approve_then_revoke():
    session, service, editor, reviewer, department_id = _workflow_fixture()
    try:
        document, _ = _draft(service, editor, department_id)
        service.submit_review(editor, document.id, "ready", "request-2")
        approved = service.approve(reviewer, document.id, "verified", "request-3")
        assert approved.status == ReviewStatus.APPROVED
        revoked = service.revoke(reviewer, document.id, "superseded", "request-4")
        assert revoked.status == ReviewStatus.REVOKED
    finally:
        session.close()
