"""评估报告生成器 — 整合召回 + 相关性 + 正确性，输出完整报告。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.models import IntentCategory, SearchResult
from app.evaluation.recall_evaluator import RecallEvaluator, RecallMetrics
from app.evaluation.relevance_evaluator import RelevanceEvaluator, RelevanceMetrics
from app.evaluation.correctness_check import CorrectnessChecker, CorrectnessResult


@dataclass
class EvaluationReport:
    """完整评估报告。"""

    report_id: str
    created_at: datetime = field(default_factory=datetime.now)

    # 评测集信息
    eval_set_name: str = ""
    eval_set_size: int = 0

    # 召回指标汇总
    recall_summary: dict = field(default_factory=dict)

    # 相关性指标汇总
    relevance_summary: dict = field(default_factory=dict)

    # 正确性指标汇总
    correctness_summary: dict = field(default_factory=dict)

    # 逐条详细结果
    details: list[dict] = field(default_factory=list)

    # 上线建议
    launch_recommendation: str = ""


class EvaluationReportGenerator:
    """评估报告生成器。

    整合三个评估维度，生成完整的评估报告：
    1. Recall — 检索系统能找回多少相关内容
    2. Relevance — 检索结果与查询的相关程度
    3. Correctness — LLM 回答的正确性
    """

    def __init__(
        self,
        recall_evaluator: RecallEvaluator,
        relevance_evaluator: RelevanceEvaluator,
        correctness_checker: CorrectnessChecker,
    ):
        self.recall_evaluator = recall_evaluator
        self.relevance_evaluator = relevance_evaluator
        self.correctness_checker = correctness_checker

    def generate_report(
        self,
        eval_set: list[tuple[str, list[str]]],
        eval_set_name: str = "default",
        top_k: int = 5,
    ) -> EvaluationReport:
        """生成完整评估报告。

        eval_set: [(问题, 人工标注的相关来源文件名列表)]
        """

        import uuid

        report_id = f"eval-{uuid.uuid4().hex[:8]}"
        eval_set_size = len(eval_set)

        # 1. 召回评估
        recall_metrics = self.recall_evaluator.evaluate_batch(eval_set, top_k)
        recall_summary = self.recall_evaluator.summarize(recall_metrics)

        # 2. 相关性评估
        queries = [q for q, _ in eval_set]
        relevance_metrics = self.relevance_evaluator.evaluate_batch(queries, top_k)
        relevance_summary = self.relevance_evaluator.summarize(relevance_metrics)

        # 3. 正确性评估（使用检索结果模拟）
        correctness_summaries = []
        for i, (question, relevant_sources) in enumerate(eval_set):
            results = self.recall_evaluator.retrieval_engine.search(
                question=question, top_k=top_k
            )
            # 模拟回答 — 使用检索片段内容
            simulated_answer = " ".join(r.chunk.content[:100] for r in results[:3])
            correctness = self.correctness_checker.check(simulated_answer, results)
            correctness_summaries.append({
                "confidence": correctness.confidence,
                "score": correctness.score,
                "source_count": correctness.source_count,
                "warnings": correctness.warnings,
                "hallucination_flags": correctness.hallucination_flags,
            })

        # 正确性汇总
        avg_confidence_score = sum(c["score"] for c in correctness_summaries) / len(correctness_summaries) if correctness_summaries else 0
        correctness_summary = {
            "avg_score": round(avg_confidence_score, 4),
            "high_confidence_count": sum(1 for c in correctness_summaries if c["confidence"] == "high"),
            "medium_confidence_count": sum(1 for c in correctness_summaries if c["confidence"] == "medium"),
            "low_confidence_count": sum(1 for c in correctness_summaries if c["confidence"] == "low"),
            "total_warnings": sum(len(c["warnings"]) for c in correctness_summaries),
        }

        # 4. 逐条详细结果
        details = []
        for i, (question, relevant_sources) in enumerate(eval_set):
            details.append({
                "query": question,
                "relevant_sources": relevant_sources,
                "recall": recall_metrics[i].recall,
                "precision": recall_metrics[i].precision,
                "f1": recall_metrics[i].f1,
                "avg_relevance_score": relevance_metrics[i].avg_score,
                "result_count": relevance_metrics[i].result_count,
                "correctness": correctness_summaries[i],
            })

        # 5. 上线建议
        launch_recommendation = self._generate_launch_recommendation(
            recall_summary, relevance_summary, correctness_summary
        )

        return EvaluationReport(
            report_id=report_id,
            created_at=datetime.now(),
            eval_set_name=eval_set_name,
            eval_set_size=eval_set_size,
            recall_summary=recall_summary,
            relevance_summary=relevance_summary,
            correctness_summary=correctness_summary,
            details=details,
            launch_recommendation=launch_recommendation,
        )

    def _generate_launch_recommendation(
        self,
        recall_summary: dict,
        relevance_summary: dict,
        correctness_summary: dict,
    ) -> str:
        """根据评估指标生成上线建议。"""

        avg_recall = recall_summary.get("avg_recall", 0)
        avg_precision = recall_summary.get("avg_precision", 0)
        avg_f1 = recall_summary.get("avg_f1", 0)
        avg_hit_rate = recall_summary.get("avg_hit_rate", 0)
        avg_relevance = relevance_summary.get("avg_relevance", 0)
        avg_correctness = correctness_summary.get("avg_score", 0)

        issues = []
        recommendations = []

        # 召回率检查
        if avg_recall < 0.6:
            issues.append("召回率过低 (< 60%)")
            recommendations.append("增加 top_k 或调整 RRF 参数以提升召回")
        if avg_hit_rate < 0.8:
            issues.append("命中率过低 (< 80%)")
            recommendations.append("检查索引完整性，确认所有知识文件已同步入库")

        # 相关性检查
        if avg_relevance < 0.5:
            issues.append("相关性得分过低 (< 0.5)")
            recommendations.append("检查 embedding 模型是否正确加载，调整 reranker 参数")

        # 正确性检查
        if avg_correctness < 0.6:
            issues.append("正确性置信度过低 (< 60%)")
            recommendations.append("增加知识库内容覆盖度，减少 LLM 幻觉风险")

        # F1 检查
        if avg_f1 < 0.5:
            issues.append("F1 综合指标过低 (< 50%)")
            recommendations.append("平衡召回率和精确率，调整检索策略参数")

        if not issues:
            return "✅ 所有指标达标，可以上线。建议持续监控运行指标。"

        result = f"⚠️ 发现 {len(issues)} 个问题:\n"
        for issue in issues:
            result += f"  - {issue}\n"
        result += "\n建议:\n"
        for rec in recommendations:
            result += f"  - {rec}\n"

        return result

    def export_report(self, report: EvaluationReport, output_path: Path) -> None:
        """导出评估报告为 JSON 文件。"""

        report_data = {
            "report_id": report.report_id,
            "created_at": report.created_at.isoformat(),
            "eval_set_name": report.eval_set_name,
            "eval_set_size": report.eval_set_size,
            "recall_summary": report.recall_summary,
            "relevance_summary": report.relevance_summary,
            "correctness_summary": report.correctness_summary,
            "details": report.details,
            "launch_recommendation": report.launch_recommendation,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
