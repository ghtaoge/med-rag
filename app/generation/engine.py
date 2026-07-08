"""LLM 引擎抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LlmEngine(ABC):
    """LLM 引擎 ABC。所有 Provider 继承此接口。"""

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        """非流式生成完整回答。"""

    @abstractmethod
    async def generate_stream(self, prompt: str, system_prompt: str = None) -> AsyncIterator[str]:
        """流式生成回答，逐 token 返回。"""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前模型名称。"""
