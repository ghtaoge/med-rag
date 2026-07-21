from __future__ import annotations

from app.documents.current_parser import CurrentLoaderParser
from app.documents.parser_contract import ParseRequest, ParseResult


class HighFidelityParser:
    """Use local MarkItDown converters for structured formats, then safe loaders."""

    _MARKITDOWN_FORMATS = {"pdf", "docx", "pptx", "xlsx"}

    def __init__(self, converter=None, fallback=None):
        if converter is None:
            from markitdown import MarkItDown

            converter = MarkItDown(enable_plugins=False)
        self.converter = converter
        self.fallback = fallback or CurrentLoaderParser()

    def parse(self, request: ParseRequest) -> ParseResult:
        if request.detected_format in self._MARKITDOWN_FORMATS:
            try:
                result = self.converter.convert(request.local_path)
                text = result.markdown
                if text and text.strip():
                    return ParseResult(text, "markitdown", "0.1.6")
            except Exception:
                pass
        fallback = self.fallback.parse(request)
        return ParseResult(
            fallback.text,
            fallback.parser_name,
            fallback.parser_version,
            fallback.warnings + ("high_fidelity_fallback",),
        )
