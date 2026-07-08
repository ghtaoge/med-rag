"""Markdown 加载器。

直接读取文本，结构信息由 chunker 的 chunk_markdown 处理。
"""

from __future__ import annotations

from pathlib import Path

from app.documents.loader.base import DocumentLoader


class MdLoader(DocumentLoader):
    """Markdown 文件加载器。"""

    def load(self, file_path: Path) -> str:
        return file_path.read_text(encoding="utf-8")
