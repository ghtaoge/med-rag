from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import SafetyAuditUnavailable
from app.safety.dlp import DlpDetector
from app.safety.models import SafetyAssessment
from app.security.models import SafetyEvent

if TYPE_CHECKING:
    from app.security.principal import Principal


class SafetyAuditService:
    def __init__(self, session: Session):
        self.session = session
        self.detector = DlpDetector()

    def record(
        self,
        principal: Principal,
        raw_input: str,
        assessment: SafetyAssessment,
        request_id: str,
    ) -> SafetyEvent:
        event = SafetyEvent(
            user_id=principal.user_id,
            department_ids_json=json.dumps(principal.department_ids),
            request_id=request_id,
            input_hash=hashlib.sha256(raw_input.encode("utf-8")).hexdigest(),
            redacted_excerpt=self.detector.scan(raw_input).redacted_text[:300],
            risk_level=assessment.risk_level.value,
            categories_json=json.dumps(
                [category.value for category in assessment.categories]
            ),
            decision=assessment.decision.value,
            policy_version=assessment.policy_version,
        )
        try:
            self.session.add(event)
            self.session.commit()
            return event
        except Exception as exc:
            self.session.rollback()
            raise SafetyAuditUnavailable() from exc

    def list_events(
        self,
        limit: int,
        cursor: str | None = None,
        risk_level: str | None = None,
        category: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[SafetyEvent]:
        statement = select(SafetyEvent)
        if cursor:
            statement = statement.where(SafetyEvent.id < cursor)
        if risk_level:
            statement = statement.where(SafetyEvent.risk_level == risk_level)
        if category:
            statement = statement.where(
                SafetyEvent.categories_json.like(f'%"{category}"%')
            )
        if created_after:
            statement = statement.where(SafetyEvent.created_at >= created_after)
        if created_before:
            statement = statement.where(SafetyEvent.created_at <= created_before)
        statement = statement.order_by(
            SafetyEvent.created_at.desc(), SafetyEvent.id.desc()
        ).limit(limit)
        return list(self.session.scalars(statement))
