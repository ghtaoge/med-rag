from __future__ import annotations

from dataclasses import dataclass

from app.safety.models import RiskCategory, SafetyDecision


@dataclass(frozen=True)
class SafetyCase:
    id: str
    text: str
    expected_decision: str
    expected_categories: tuple[str, ...]
    group: str


@dataclass(frozen=True)
class SafetyMetrics:
    total: int
    high_risk_block_rate: float
    normal_false_block_rate: float
    secret_redaction_rate: float
    unauthorized_release_count: int
    failed_case_ids: tuple[str, ...]


def evaluate_cases(gateway, cases: list[SafetyCase]) -> SafetyMetrics:
    high_risk = [case for case in cases if case.expected_decision == "block"]
    normal = [case for case in cases if case.group == "normal"]
    secrets = [
        case for case in cases if RiskCategory.SECRET.value in case.expected_categories
    ]
    blocked_high = 0
    false_blocks = 0
    redacted_secrets = 0
    unauthorized_release_count = 0
    failed_ids: list[str] = []
    for case in cases:
        result = gateway.assess(case.text)
        decision = result.decision.value
        actual_categories = {category.value for category in result.categories}
        if case.expected_decision == "block" and decision == SafetyDecision.BLOCK.value:
            blocked_high += 1
        if case.group == "normal" and decision == SafetyDecision.BLOCK.value:
            false_blocks += 1
        if case in secrets and "[REDACTED:SECRET]" in result.redacted_input:
            redacted_secrets += 1
        if case.expected_decision == "block" and decision != SafetyDecision.BLOCK.value:
            unauthorized_release_count += 1
        if (
            decision != case.expected_decision
            or not set(case.expected_categories).issubset(actual_categories)
        ):
            failed_ids.append(case.id)
    return SafetyMetrics(
        total=len(cases),
        high_risk_block_rate=blocked_high / len(high_risk) if high_risk else 1.0,
        normal_false_block_rate=false_blocks / len(normal) if normal else 0.0,
        secret_redaction_rate=redacted_secrets / len(secrets) if secrets else 1.0,
        unauthorized_release_count=unauthorized_release_count,
        failed_case_ids=tuple(failed_ids),
    )
