from __future__ import annotations

from app.documents.loader import load_document
from app.documents.parser_contract import ParseRequest, ParseResult


class CurrentLoaderParser:
    name = "current-loaders"
    version = "1"

    def parse(self, request: ParseRequest) -> ParseResult:
        if not request.local_path.is_file():
            raise ValueError("parser input is not a local file")
        text = load_document(request.local_path)
        if not text.strip():
            raise ValueError("parser returned empty output")
        return ParseResult(text, self.name, self.version)
