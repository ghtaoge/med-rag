"""TXT 文件加载器。UTF-8 直接读取。"""

from __future__ import annotations

from pathlib import Path

from app.documents.loader.base import DocumentLoader


class TxtLoader(DocumentLoader):
    """TXT 文件加载器。"""

    def load(self, file_path: Path) -> str:
        return file_path.read_text(encoding="utf-8")
