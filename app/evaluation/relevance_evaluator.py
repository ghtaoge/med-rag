"""相关性评估器 — 衡量检索结果与查询的相关程度。

指标：Top-K 相关度均值、得分分布、Reranker 效果对比。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.models import SearchResult, IntentCategory
from app.retrieval.hybrid_engine import HybridRetrievalEngine


@dataclass
class RelevanceMetrics:
    """相关性评估指标。"""

    query: str
    top_k_scores: list[float]  # 前 K 个结果的得分
    avg_score: float = 0.0     # 平均得分
    max_score: float = 0.0     # 最高得分
    min_score: float = 0.0     # 最低得分
    score_spread: float = 0.0  # 得分差异（max - min）
    result_count: int = 0      # 实际检索结果数


class RelevanceEvaluator:
    """相关性评估器。

    用法：
    1. 对评测集中的每条问题执行检索
    2. 记录得分分布
    3. 分析得分质量
    """

    def __init__(self, retrieval_engine: HybridRetrievalEngine):
        self.retrieval_engine = retrieval_engine

    def evaluate_single(
        self,
        question: str,
        top_k: int = 5,
        intent: IntentCategory | None = None,
    ) -> RelevanceMetrics:
        """评估单条查询的相关性。"""

        results = self.retrieval_engine.search(
            question=question, top_k=top_k, intent=intent
        )

        scores = [r.score for r in results]
        result_count = len(results)

        avg_score = sum(scores) / len(scores) if scores else 0.0
        max_score = max(scores) if scores else 0.0
        min_score = min(scores) if scores else 0.0
        score_spread = max_score - min_score

        return RelevanceMetrics(
            query=question,
            top_k_scores=scores,
            avg_score=round(avg_score, 4),
            max_score=round(max_score, 4),
            min_score=round(min_score, 4),
            score_spread=round(score_spread, 4),
            result_count=result_count,
        )

    def evaluate_batch(
        self,
        queries: list[str],
        top_k: int = 5,
    ) -> list[RelevanceMetrics]:
        """批量评估相关性。"""

        results = []
        for query in queries:
            metrics = self.evaluate_single(query, top_k)
            results.append(metrics)

        return results

    def summarize(self, metrics: list[RelevanceMetrics]) -> dict:
        """汇总相关性指标。"""

        n = len(metrics)
        if n == 0:
            return {"count": 0}

        avg_scores = [m.avg_score for m in metrics]
        max_scores = [m.max_score for m in metrics]
        result_counts = [m.result_count for m in metrics]

        return {
            "count": n,
            "avg_relevance": round(sum(avg_scores) / n, 4),
            "avg_max_score": round(sum(max_scores) / n, 4),
            "avg_result_count": round(sum(result_counts) / n, 1),
            "zero_result_queries": sum(1 for c in result_counts if c == 0),
            "high_relevance_queries": sum(1 for s in avg_scores if s >= 0.7),
        }
