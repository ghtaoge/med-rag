"""意图路由 → 不同检索/生成策略。"""

from __future__ import annotations

from app.core.models import IntentCategory
from app.retrieval.engine import get_strategy


class IntentRouter:
    """意图路由器。

    根据意图类别映射到检索策略和 Prompt 策略。
    """

    @staticmethod
    def get_retrieval_strategy(intent: IntentCategory | None) -> dict:
        """获取检索策略参数。"""

        strategy = get_strategy(intent)
        return {
            "vector_top_k": strategy.vector_top_k,
            "keyword_top_k": strategy.keyword_top_k,
            "rerank_top_k": strategy.rerank_top_k,
            "use_vector": strategy.use_vector,
            "use_keyword": strategy.use_keyword,
            "use_reranker": strategy.use_reranker,
            "rrf_k": strategy.rrf_k,
        }

    @staticmethod
    def get_prompt_suffix(intent: IntentCategory | None) -> str:
        """获取 Prompt 引导语后缀。"""

        from app.generation.prompt_builder import INTENT_PROMPTS

        intent = intent or IntentCategory.QUERY
        return INTENT_PROMPTS.get(intent, INTENT_PROMPTS[IntentCategory.QUERY])
