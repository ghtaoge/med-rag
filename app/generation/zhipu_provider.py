"""智谱 Provider。

智谱 API 兼容 OpenAI 格式。
"""

from __future__ import annotations

from app.generation.openai_provider import OpenAICompatibleProvider


class ZhipuProvider(OpenAICompatibleProvider):
    """智谱 API Provider。"""

    def __init__(
        self,
        api_key: str = "",
        model: str = "glm-4-plus",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        super().__init__(
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
