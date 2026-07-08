"""通义千问 Provider。

阿里云 DashScope 兼容模式，使用 OpenAI 格式 API。
"""

from __future__ import annotations

from app.generation.openai_provider import OpenAICompatibleProvider


class QwenProvider(OpenAICompatibleProvider):
    """通义千问 API Provider。"""

    def __init__(
        self,
        api_key: str = "",
        model: str = "qwen-plus",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        super().__init__(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
