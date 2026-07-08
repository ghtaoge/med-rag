"""文档加载器抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class DocumentLoader(ABC):
    """文档加载器 ABC。每种格式一个子类。"""

    @abstractmethod
    def load(self, file_path: Path) -> str:
        """读取文件并返回纯文本内容。"""
