from __future__ import annotations

import re
from dataclasses import dataclass

from app.safety.models import RiskCategory


@dataclass(frozen=True)
class DlpFinding:
    start: int
    end: int
    signal: str
    category: RiskCategory
    replacement: str


@dataclass(frozen=True)
class DlpResult:
    redacted_text: str
    findings: tuple[DlpFinding, ...]

    @property
    def categories(self) -> tuple[RiskCategory, ...]:
        return tuple(dict.fromkeys(item.category for item in self.findings))


class DlpDetector:
    max_pattern_chars = 512
    _PATTERNS = (
        (
            "bearer_token",
            RiskCategory.SECRET,
            "[REDACTED:SECRET]",
            re.compile(r"(?i)\b(?:authorization\s*:\s*)?bearer\s+[a-z0-9._~+/=-]{20,}"),
        ),
        (
            "jwt",
            RiskCategory.SECRET,
            "[REDACTED:SECRET]",
            re.compile(r"\beyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\b"),
        ),
        (
            "api_key",
            RiskCategory.SECRET,
            "[REDACTED:SECRET]",
            re.compile(r"(?i)\b(?:sk|pk|api)[-_][a-z0-9_-]{20,}\b"),
        ),
        (
            "cn_id",
            RiskCategory.PII,
            "[REDACTED:CN_ID]",
            re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
        ),
        (
            "cn_phone",
            RiskCategory.PII,
            "[REDACTED:PHONE]",
            re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        ),
        (
            "email",
            RiskCategory.PII,
            "[REDACTED:EMAIL]",
            re.compile(r"(?i)\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+\b"),
        ),
    )

    def scan(self, text: str) -> DlpResult:
        findings = self._find(text)
        output = text
        for finding in reversed(findings):
            output = (
                output[: finding.start]
                + finding.replacement
                + output[finding.end :]
            )
        return DlpResult(output, tuple(findings))

    def _find(self, text: str) -> list[DlpFinding]:
        candidates: list[DlpFinding] = []
        for signal, category, replacement, pattern in self._PATTERNS:
            for match in pattern.finditer(text):
                candidates.append(
                    DlpFinding(
                        match.start(), match.end(), signal, category, replacement
                    )
                )
        candidates.sort(key=lambda item: (item.start, -(item.end - item.start)))
        accepted: list[DlpFinding] = []
        cursor = -1
        for finding in candidates:
            if finding.start < cursor:
                continue
            accepted.append(finding)
            cursor = finding.end
        return accepted
