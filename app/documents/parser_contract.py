from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ParseRequest:
    job_id: str
    document_version_id: str
    local_path: Path
    detected_format: str


@dataclass(frozen=True)
class ParseResult:
    text: str
    parser_name: str
    parser_version: str
    warnings: tuple[str, ...] = ()


class DocumentParser(Protocol):
    def parse(self, request: ParseRequest) -> ParseResult:
        raise NotImplementedError
