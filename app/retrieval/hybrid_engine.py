"""混合检索引擎 — 多路召回协调器。

协调 MilvusStore + KeywordStore → RRF融合 → Reranker重排序。
"""

from __future__ import annotations

from app.core.models import SearchResult, IntentCategory
from app.retrieval.engine import RetrievalEngine, get_strategy
from app.retrieval.milvus_store import MilvusStore
from app.retrieval.keyword_store import KeywordStore
from app.retrieval.hybrid import rrf_fusion
from app.retrieval.reranker import Reranker
from app.retrieval.metadata_filter import build_filter
from app.retrieval.access import (
    RetrievalAccess,
    assert_authorized_results,
    build_milvus_access_filter,
)
from app.core.exceptions import AuthorizationError


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
        access: RetrievalAccess | None = None,
    ) -> list[SearchResult]:
        """混合检索完整流程。"""

        strategy = get_strategy(intent)
        if access is None:
            raise AuthorizationError("检索必须提供授权范围")
        metadata_expr = build_filter(metadata_filter)
        access_expr = build_milvus_access_filter(access)
        filter_expr = (
            f"({access_expr}) && ({metadata_expr})" if metadata_expr else access_expr
        )

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
                    access=access,
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

        return assert_authorized_results(final, access)
