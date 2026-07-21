"""不保存敏感正文的操作审计。"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from sqlalchemy.orm import Session

from app.security.models import AuditEvent


class AuditAction(str, Enum):
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    TOKEN_REVOKED = "token_revoked"
    USER_CREATED = "user_created"
    USER_STATUS_CHANGED = "user_status_changed"
    DEPARTMENT_CREATED = "department_created"
    MEMBERSHIP_CHANGED = "membership_changed"
    MEMBERSHIP_REVOKED = "membership_revoked"
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_SUBMITTED = "document_submitted"
    DOCUMENT_APPROVED = "document_approved"
    DOCUMENT_REVOKED = "document_revoked"
    DOCUMENT_SYNCED = "document_synced"
    AUDIT_EVENTS_QUERIED = "audit_events_queried"


def state_hash(value: dict | None) -> str | None:
    if value is None:
        return None
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class AuditService:
    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        actor_user_id: str | None,
        action: AuditAction | str,
        resource_type: str,
        resource_id: str,
        result: str,
        reason: str,
        request_id: str,
        before_state: dict | None = None,
        after_state: dict | None = None,
    ) -> AuditEvent:
        if not reason.strip():
            raise ValueError("审计原因不能为空")
        event = AuditEvent(
            actor_user_id=actor_user_id,
            action=action.value if isinstance(action, AuditAction) else action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            reason=reason.strip(),
            request_id=request_id,
            before_state_hash=state_hash(before_state),
            after_state_hash=state_hash(after_state),
        )
        self.session.add(event)
        self.session.flush()
        return event
