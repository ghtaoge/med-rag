"""文档加载器包。"""

from app.documents.loader.registry import load_document, supported_extensions

__all__ = ["load_document", "supported_extensions"]