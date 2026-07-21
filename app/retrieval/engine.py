"""检索引擎抽象接口 + 混合检索协调器。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.models import SearchResult, IntentCategory
from app.retrieval.access import RetrievalAccess


class RetrievalEngine(ABC):
    """检索引擎 ABC。"""

    @abstractmethod
    def search(
        self,
        question: str,
        top_k: int = 5,
        intent: IntentCategory | None = None,
        metadata_filter: dict | None = None,
        access: RetrievalAccess | None = None,
    ) -> list[SearchResult]:
        """检索最相关的知识片段。"""


@dataclass
class RetrievalStrategy:
    """检索策略配置。"""

    vector_top_k: int = 20
    keyword_top_k: int = 20
    rerank_top_k: int = 5
    use_vector: bool = True
    use_keyword: bool = True
    use_reranker: bool = True
    rrf_k: int = 60


# 意图 → 检索策略映射
INTENT_STRATEGIES: dict[IntentCategory, RetrievalStrategy] = {
    IntentCategory.QUERY: RetrievalStrategy(),  # 默认混合
    IntentCategory.DEFINITION: RetrievalStrategy(
        vector_top_k=10, keyword_top_k=30, use_vector=True, use_keyword=True
    ),  # 定义类 → 关键词更重要
    IntentCategory.COMPARISON: RetrievalStrategy(
        vector_top_k=30, keyword_top_k=30, rerank_top_k=8
    ),  # 对比类 → 扩大召回
    IntentCategory.PROCESS: RetrievalStrategy(
        vector_top_k=15, keyword_top_k=25, use_vector=True, use_keyword=True
    ),  # 流程类 → 混合
    IntentCategory.NEGATION: RetrievalStrategy(
        vector_top_k=25, keyword_top_k=25, rerank_top_k=8
    ),  # 否定类 → 扩大召回+多来源
}


def get_strategy(intent: IntentCategory | None) -> RetrievalStrategy:
    """根据意图获取检索策略。"""

    if intent is None:
        return RetrievalStrategy()
    return INTENT_STRATEGIES.get(intent, RetrievalStrategy())
