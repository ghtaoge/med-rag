from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.dependencies import get_db_session
from app.safety.audit import SafetyAuditService
from app.security.audit import AuditAction, AuditService
from app.security.permissions import Permission, permission_dependency
from app.security.principal import Principal

router = APIRouter(
    prefix="/api/v1/safety",
    tags=["安全审计"],
    dependencies=[Depends(permission_dependency(Permission.SECURITY_AUDIT))],
)


@router.get("/events")
def list_safety_events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    risk_level: str | None = None,
    category: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    principal: Principal = Depends(
        permission_dependency(Permission.SECURITY_AUDIT)
    ),
    session: Session = Depends(get_db_session),
):
    events = SafetyAuditService(session).list_events(
        limit, cursor, risk_level, category, created_after, created_before
    )
    AuditService(session).record(
        principal.user_id,
        AuditAction.AUDIT_EVENTS_QUERIED,
        "safety_event",
        events[-1].id if events else "none",
        "success",
        "safety events queried",
        request.headers.get("X-Request-ID", uuid.uuid4().hex),
    )
    session.commit()
    return {
        "events": [
            {
                "id": event.id,
                "user_id": event.user_id,
                "department_ids": json.loads(event.department_ids_json),
                "request_id": event.request_id,
                "input_hash": event.input_hash,
                "redacted_excerpt": event.redacted_excerpt,
                "risk_level": event.risk_level,
                "categories": json.loads(event.categories_json),
                "decision": event.decision,
                "policy_version": event.policy_version,
                "created_at": event.created_at,
            }
            for event in events
        ],
        "next_cursor": events[-1].id if len(events) == limit else None,
    }
