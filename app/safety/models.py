from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SafetyDecision(str, Enum):
    ALLOW = "allow"
    ALLOW_RESTRICTED = "allow_restricted"
    BLOCK = "block"


class RiskCategory(str, Enum):
    PII = "pii"
    SECRET = "secret"
    JAILBREAK = "jailbreak"
    DATA_EXFILTRATION = "data_exfiltration"
    BULK_ENUMERATION = "bulk_enumeration"
    COMMAND_INJECTION = "command_injection"
    MANAGEMENT_ACTION = "management_action"
    HARMFUL_CONTENT = "harmful_content"


@dataclass(frozen=True)
class SafetyAssessment:
    risk_level: RiskLevel
    categories: tuple[RiskCategory, ...]
    matched_signals: tuple[str, ...]
    redacted_input: str
    policy_version: str
    decision: SafetyDecision

    def public_summary(self) -> dict[str, str]:
        return {
            "risk_level": self.risk_level.value,
            "decision": self.decision.value,
            "policy_version": self.policy_version,
        }
