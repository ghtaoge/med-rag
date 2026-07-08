"""混合检索引擎 — 多路召回协调器。

协调 MilvusStore + KeywordStore → RRF融合 → Reranker重排序。
"""

from __future__ import annotations

from app.core.models import SearchResult, IntentCategory
from app.retrieval.engine import RetrievalEngine, RetrievalStrategy, get_strategy
from app.retrieval.milvus_store import MilvusStore
from app.retrieval.keyword_store import KeywordStore
from app.retrieval.hybrid import rrf_fusion
from app.retrieval.reranker import Reranker
from app.retrieval.metadata_filter import build_filter


class HybridRetrievalEngine(RetrievalEngine):
    """混合检索引擎。

    流程：意图识别 → 选择策略 → 多路并发召回 → RRF融合 → Reranker重排序
    """

    def __init__(
        self,
        milvus_store: MilvusStore,
        keyword_store: KeywordStore,
        reranker: Reranker | None = None,
    ):
        self.milvus_store = milvus_store
        self.keyword_store = keyword_store
        self.reranker = reranker or Reranker()

    def search(
        self,
        question: str,
        top_k: int = 5,
        intent: IntentCategory | None = None,
        metadata_filter: dict | None = None,
    ) -> list[SearchResult]:
        """混合检索完整流程。"""

        strategy = get_strategy(intent)
        filter_expr = build_filter(metadata_filter)

        # 多路召回
        vector_results: list[SearchResult] = []
        keyword_results: list[SearchResult] = []

        if strategy.use_vector:
            try:
                vector_results = self.milvus_store.search(
                    query=question,
                    top_k=strategy.vector_top_k,
                    filter_expr=filter_expr,
                )
            except Exception:
                # Milvus 不可用时降级到纯关键词检索
                vector_results = []

        if strategy.use_keyword:
            try:
                keyword_results = self.keyword_store.search(
                    query=question,
                    top_k=strategy.keyword_top_k,
                )
            except Exception:
                keyword_results = []

        # RRF 融合
        fused = rrf_fusion(
            vector_results, keyword_results, k=strategy.rrf_k
        )

        # Reranker 重排序
        if strategy.use_reranker and len(fused) > top_k:
            try:
                final = self.reranker.rerank(
                    query=question, results=fused, top_k=strategy.rerank_top_k
                )
            except Exception:
                # Reranker 不可用时直接返回融合结果
                final = fused[:top_k]
        else:
            final = fused[:top_k]

        return final
