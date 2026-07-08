"""图片 OCR 加载器。PaddleOCR 中文医疗表格/手写处方识别。"""

from __future__ import annotations

from pathlib import Path

from app.documents.loader.base import DocumentLoader


class ImageLoader(DocumentLoader):
    """图片文件加载器。使用 PaddleOCR 进行文字识别。"""

    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}

    def load(self, file_path: Path) -> str:
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            raise ImportError(
                "图片 OCR 需要 PaddleOCR，请执行: pip install paddleocr paddlepaddle"
            )

        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        result = ocr.ocr(str(file_path), cls=True)

        if not result or not result[0]:
            return ""

        texts = [line[1][0] for line in result[0]]
        return "\n".join(texts)
