"""召回评估器 — 衡量检索系统找回相关内容的能力。

指标：Recall, Precision, F1, MRR, Hit Rate。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.models import IntentCategory
from app.retrieval.hybrid_engine import HybridRetrievalEngine
from app.retrieval.access import RetrievalAccess


@dataclass
class RecallMetrics:
    """召回评估指标。"""

    query: str
    relevant_sources: list[str]  # 人工标注的相关文件名
    retrieved_sources: list[str]  # 实际检索到的文件名

    recall: float = 0.0      # Recall = 检出的相关 / 所有相关
    precision: float = 0.0   # Precision = 检出的相关 / 所有检出
    f1: float = 0.0          # F1 = 2 * P * R / (P + R)
    hit_rate: float = 0.0    # 至少检出1个相关的概率
    mrr: float = 0.0         # Mean Reciprocal Rank


class RecallEvaluator:
    """召回评估器。

    用法：
    1. 准备评测集（问题 + 人工标注的相关来源）
    2. 对每个问题运行检索
    3. 计算 Recall/Precision/F1/MRR
    """

    def __init__(self, retrieval_engine: HybridRetrievalEngine):
        self.retrieval_engine = retrieval_engine

    def evaluate_single(
        self,
        question: str,
        relevant_sources: list[str],
        top_k: int = 5,
        intent: IntentCategory | None = None,
        access: RetrievalAccess | None = None,
    ) -> RecallMetrics:
        """评估单条查询的召回指标。"""

        # 执行检索
        results = self.retrieval_engine.search(
            question=question, top_k=top_k, intent=intent, access=access
        )

        # 检索到的来源文件名
        retrieved_sources = [r.chunk.source for r in results]

        # 计算 Recall
        relevant_set = set(relevant_sources)
        retrieved_set = set(retrieved_sources)
        hit = relevant_set & retrieved_set

        recall = len(hit) / len(relevant_set) if relevant_set else 0.0
        precision = len(hit) / len(retrieved_set) if retrieved_set else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        hit_rate = 1.0 if len(hit) > 0 else 0.0

        # MRR — 第一个相关结果的位置倒数
        mrr = 0.0
        for i, source in enumerate(retrieved_sources):
            if source in relevant_set:
                mrr = 1.0 / (i + 1)
                break

        return RecallMetrics(
            query=question,
            relevant_sources=relevant_sources,
            retrieved_sources=retrieved_sources,
            recall=recall,
            precision=precision,
            f1=f1,
            hit_rate=hit_rate,
            mrr=mrr,
        )

    def evaluate_batch(
        self,
        eval_set: list[tuple[str, list[str]]],
        top_k: int = 5,
        access: RetrievalAccess | None = None,
    ) -> list[RecallMetrics]:
        """批量评估召回指标。"""

        results = []
        for question, relevant_sources in eval_set:
            metrics = self.evaluate_single(
                question, relevant_sources, top_k, access=access
            )
            results.append(metrics)

        return results

    def summarize(self, metrics: list[RecallMetrics]) -> dict:
        """汇总评估指标。"""

        n = len(metrics)
        if n == 0:
            return {"count": 0}

        avg_recall = sum(m.recall for m in metrics) / n
        avg_precision = sum(m.precision for m in metrics) / n
        avg_f1 = sum(m.f1 for m in metrics) / n
        avg_hit_rate = sum(m.hit_rate for m in metrics) / n
        avg_mrr = sum(m.mrr for m in metrics) / n

        return {
            "count": n,
            "avg_recall": round(avg_recall, 4),
            "avg_precision": round(avg_precision, 4),
            "avg_f1": round(avg_f1, 4),
            "avg_hit_rate": round(avg_hit_rate, 4),
            "avg_mrr": round(avg_mrr, 4),
        }
