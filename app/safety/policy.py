from __future__ import annotations

from app.safety.models import RiskCategory, RiskLevel, SafetyDecision

HIGH_RISK = {
    RiskCategory.SECRET,
    RiskCategory.JAILBREAK,
    RiskCategory.DATA_EXFILTRATION,
    RiskCategory.BULK_ENUMERATION,
    RiskCategory.COMMAND_INJECTION,
    RiskCategory.MANAGEMENT_ACTION,
}


def decide(
    categories: tuple[RiskCategory, ...],
    semantic_label: str,
    classifier_available: bool,
) -> tuple[RiskLevel, SafetyDecision]:
    category_set = set(categories)
    if category_set & HIGH_RISK or semantic_label == "unsafe":
        return RiskLevel.HIGH, SafetyDecision.BLOCK
    if category_set or semantic_label == "controversial" or not classifier_available:
        return RiskLevel.MEDIUM, SafetyDecision.ALLOW_RESTRICTED
    return RiskLevel.LOW, SafetyDecision.ALLOW
