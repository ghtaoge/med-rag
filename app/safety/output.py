from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.core.models import SearchResult
from app.safety.dlp import DlpDetector
from app.safety.models import RiskCategory

if TYPE_CHECKING:
    from app.security.principal import Principal


class OutputBlocked(RuntimeError):
    pass


_INTERNAL_PATTERN = re.compile(
    r"(?i)(system\s+prompt|developer\s+message|系统提示词|"
    r"postgresql://|redis://|(?:[a-z]:\\(?:windows|users|app)\\)|"
    r"/(?:etc|app|root)/)"
)


def _scan_text(text: str, detector: DlpDetector) -> str:
    if _INTERNAL_PATTERN.search(text):
        raise OutputBlocked("输出包含内部系统信息")
    result = detector.scan(text)
    if RiskCategory.SECRET in result.categories:
        raise OutputBlocked("输出包含敏感凭据")
    return result.redacted_text


def validate_output_sources(
    principal: Principal,
    sources: list[SearchResult],
) -> None:
    allowed = set(principal.department_ids)
    now = int(datetime.now(timezone.utc).timestamp())
    for result in sources:
        metadata = result.chunk.metadata
        if (
            metadata.review_status != "approved"
            or not allowed.intersection(metadata.visible_department_ids)
            or (metadata.expires_at_epoch and metadata.expires_at_epoch <= now)
        ):
            raise OutputBlocked("输出来源未通过授权校验")


def sanitize_complete_output(
    answer: str,
    sources: list[SearchResult],
    principal: Principal,
) -> tuple[str, list[SearchResult]]:
    detector = DlpDetector()
    validate_output_sources(principal, sources)
    safe_sources: list[SearchResult] = []
    for result in sources:
        safe_content = _scan_text(result.chunk.content, detector)
        safe_sources.append(
            replace(
                result,
                chunk=replace(result.chunk, content=safe_content),
            )
        )
    return _scan_text(answer, detector), safe_sources


class SafeStreamBuffer:
    def __init__(self, buffer_chars: int = 512, detector: DlpDetector | None = None):
        self.detector = detector or DlpDetector()
        self.holdback = max(buffer_chars, self.detector.max_pattern_chars)
        self.buffer = ""

    def feed(self, text: str) -> str:
        self.buffer += text
        self._assert_not_blocked(self.buffer)
        if len(self.buffer) <= self.holdback:
            return ""
        split_at = len(self.buffer) - self.holdback
        findings = self.detector.scan(self.buffer).findings
        for finding in findings:
            if finding.start < split_at < finding.end:
                split_at = finding.start
        prefix = self.buffer[:split_at]
        self.buffer = self.buffer[split_at:]
        return _scan_text(prefix, self.detector)

    def finalize(self) -> str:
        self._assert_not_blocked(self.buffer)
        output = _scan_text(self.buffer, self.detector)
        self.buffer = ""
        return output

    def _assert_not_blocked(self, text: str) -> None:
        _scan_text(text, self.detector)
