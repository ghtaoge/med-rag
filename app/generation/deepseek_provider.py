"""DeepSeek Provider。

继承 OpenAICompatibleProvider，覆盖 base_url 和 model。
"""

from __future__ import annotations

from app.generation.openai_provider import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek API Provider。"""

    def __init__(
        self,
        api_key: str = "",
        model: str = "deepseek-chat",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        super().__init__(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
