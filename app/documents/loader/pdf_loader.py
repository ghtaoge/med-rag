"""PDF 加载器。pypdf 文本提取 + PaddleOCR 扫描件支持。"""

from __future__ import annotations

from pathlib import Path

from app.documents.loader.base import DocumentLoader


class PdfLoader(DocumentLoader):
    """PDF 文件加载器。pypdf 逐页提取文本。扫描件用 PaddleOCR。"""

    def load(self, file_path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("PDF 加载需要 pypdf，请执行: pip install pypdf")

        reader = PdfReader(str(file_path))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text)

        total_text = "\n\n".join(pages_text)

        # 如果 pypdf 提取文本过少（可能是扫描件），尝试 PaddleOCR
        if len(total_text.strip()) < 50 and len(reader.pages) > 0:
            ocr_text = self._ocr_pdf(file_path)
            if ocr_text:
                return ocr_text

        return total_text

    def _ocr_pdf(self, file_path: Path) -> str:
        """PaddleOCR 扫描件识别。"""
        try:
            from paddleocr import PaddleOCR

            ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
            result = ocr.ocr(str(file_path), cls=True)
            if not result or not result[0]:
                return ""
            texts = [line[1][0] for line in result[0]]
            return "\n".join(texts)
        except ImportError:
            return ""
