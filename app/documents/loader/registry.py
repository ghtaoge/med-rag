"""文档加载器注册表。按扩展名分发。"""

from __future__ import annotations

from pathlib import Path

from app.documents.loader.base import DocumentLoader
from app.documents.loader.txt_loader import TxtLoader
from app.documents.loader.md_loader import MdLoader
from app.documents.loader.pdf_loader import PdfLoader
from app.documents.loader.word_loader import WordLoader
from app.documents.loader.image_loader import ImageLoader
from app.documents.loader.excel_loader import ExcelLoader
from app.documents.loader.csv_loader import CsvLoader
from app.documents.loader.ppt_loader import PptLoader

_LOADERS: dict[str, DocumentLoader] = {
    ".txt": TxtLoader(),
    ".md": MdLoader(),
    ".pdf": PdfLoader(),
    ".docx": WordLoader(),
    ".png": ImageLoader(),
    ".jpg": ImageLoader(),
    ".jpeg": ImageLoader(),
    ".tiff": ImageLoader(),
    ".xlsx": ExcelLoader(),
    ".csv": CsvLoader(),
    ".pptx": PptLoader(),
}


def supported_extensions() -> list[str]:
    """返回当前支持的所有文件扩展名。"""

    return sorted(_LOADERS.keys())


def load_document(file_path: Path) -> str:
    """根据文件扩展名选择加载器并读取文本。"""

    suffix = file_path.suffix.lower()
    loader = _LOADERS.get(suffix)
    if loader is None:
        raise ValueError(
            f"不支持的文件格式: {suffix}，"
            f"当前支持: {', '.join(supported_extensions())}"
        )
    return loader.load(file_path)
