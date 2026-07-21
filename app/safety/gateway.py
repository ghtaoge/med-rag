from __future__ import annotations

from app.safety.classifier import (
    ClassifierUnavailable,
    QwenGuardClassifier,
    rule_signals,
)
from app.safety.dlp import DlpDetector
from app.safety.models import (
    RiskLevel,
    SafetyAssessment,
    SafetyDecision,
)
from app.safety.normalizer import InputShapeError, normalize_input
from app.safety.policy import HIGH_RISK, decide


class SafetyGateway:
    def __init__(self, classifier: QwenGuardClassifier, config: dict):
        self.classifier = classifier
        self.config = config
        self.detector = DlpDetector()

    def assess(self, value: str) -> SafetyAssessment:
        settings = self.config["safety"]
        try:
            normalized = normalize_input(value, settings["normal_max_chars"])
        except InputShapeError:
            return self._blocked("")
        dlp = self.detector.scan(normalized)
        rules = rule_signals(dlp.redacted_text)
        categories = list(dlp.categories) + list(rules.categories)
        semantic_label = "safe"
        classifier_available = True
        try:
            semantic = self.classifier.classify(dlp.redacted_text)
            semantic_label = semantic.label
            categories.extend(semantic.categories)
        except ClassifierUnavailable:
            classifier_available = False
            if (
                len(normalized) > settings["degraded_max_chars"]
                or set(rules.categories) & HIGH_RISK
            ):
                return self._blocked(dlp.redacted_text, categories, rules.signals)
        unique_categories = tuple(dict.fromkeys(categories))
        risk_level, decision = decide(
            unique_categories, semantic_label, classifier_available
        )
        return SafetyAssessment(
            risk_level,
            unique_categories,
            tuple(dict.fromkeys(
                [item.signal for item in dlp.findings] + list(rules.signals)
            )),
            dlp.redacted_text,
            settings["policy_version"],
            decision,
        )

    def _blocked(
        self,
        redacted_input: str,
        categories=(),
        signals=(),
    ) -> SafetyAssessment:
        return SafetyAssessment(
            RiskLevel.HIGH,
            tuple(dict.fromkeys(categories)),
            tuple(dict.fromkeys(signals)),
            redacted_input,
            self.config["safety"]["policy_version"],
            SafetyDecision.BLOCK,
        )
