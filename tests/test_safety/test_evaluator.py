from app.safety.evaluator import SafetyCase, evaluate_cases
from app.safety.models import (
    RiskCategory,
    RiskLevel,
    SafetyAssessment,
    SafetyDecision,
)


class PerfectGateway:
    def assess(self, text):
        if "secret" in text:
            return SafetyAssessment(
                RiskLevel.HIGH,
                (RiskCategory.SECRET,),
                (),
                "[REDACTED:SECRET]",
                "test",
                SafetyDecision.BLOCK,
            )
        return SafetyAssessment(
            RiskLevel.LOW, (), (), text, "test", SafetyDecision.ALLOW
        )


def test_evaluator_reports_required_metrics():
    cases = [
        SafetyCase("normal-1", "medical", "allow", (), "normal"),
        SafetyCase("secret-1", "secret", "block", ("secret",), "secret"),
    ]
    metrics = evaluate_cases(PerfectGateway(), cases)
    assert metrics.high_risk_block_rate == 1.0
    assert metrics.normal_false_block_rate == 0.0
    assert metrics.secret_redaction_rate == 1.0
