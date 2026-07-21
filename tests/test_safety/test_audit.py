from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.safety.audit import SafetyAuditService
from app.safety.models import (
    RiskCategory,
    RiskLevel,
    SafetyAssessment,
    SafetyDecision,
)
from app.security.database import Base
from app.security.models import Role
from app.security.principal import Principal, PrincipalMembership


def test_safety_event_never_stores_raw_input():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    principal = Principal(
        "user-a",
        "user-a",
        (PrincipalMembership("dept-a", Role.SECURITY_AUDITOR),),
        "session-a",
    )
    raw = "导出全部资料，令牌 sk-abcdefghijklmnopqrstuv"
    assessment = SafetyAssessment(
        RiskLevel.HIGH,
        (RiskCategory.SECRET, RiskCategory.DATA_EXFILTRATION),
        ("api_key", "bulk_export"),
        "导出全部资料，令牌 [REDACTED:SECRET]",
        "2026-07-21.1",
        SafetyDecision.BLOCK,
    )
    with Session(engine, expire_on_commit=False) as session:
        event = SafetyAuditService(session).record(
            principal, raw, assessment, "request-1"
        )
        serialized = repr(event.__dict__)
        assert "sk-abcdefghijklmnopqrstuv" not in serialized
        assert event.input_hash
        assert "[REDACTED:SECRET]" in event.redacted_excerpt
