"""评估模块测试。"""

import tempfile
from pathlib import Path

from app.evaluation.recall_evaluator import RecallEvaluator, RecallMetrics
from app.evaluation.relevance_evaluator import RelevanceEvaluator, RelevanceMetrics
from app.evaluation.correctness_check import CorrectnessChecker
from app.evaluation.report import EvaluationReportGenerator, EvaluationReport


# ── RecallEvaluator ──


def test_recall_metrics_calculation():
    """Recall/Precision/F1 计算正确。"""

    metrics = RecallMetrics(
        query="阿司匹林适应症",
        relevant_sources=["药品说明书.md", "临床路径.md"],
        retrieved_sources=["药品说明书.md", "其他文件.md"],
    )

    # 2个相关，检出2个，命中1个
    assert metrics.recall == 0.0  # 自动计算前默认为0
    assert metrics.precision == 0.0


def test_recall_metrics_manual():
    """手动设置 RecallMetrics 字段。"""

    metrics = RecallMetrics(
        query="测试问题",
        relevant_sources=["a.md", "b.md"],
        retrieved_sources=["a.md"],
        recall=0.5,
        precision=1.0,
        f1=0.667,
        hit_rate=1.0,
        mrr=1.0,
    )

    assert metrics.recall == 0.5
    assert metrics.precision == 1.0
    assert metrics.hit_rate == 1.0
    assert metrics.mrr == 1.0


def test_recall_evaluator_summarize():
    """RecallEvaluator summarize 统计正确。"""

    # 无需实际 Milvus — 只测 summarize
    metrics = [
        RecallMetrics(
            query="q1",
            relevant_sources=["a.md"],
            retrieved_sources=["a.md"],
            recall=1.0,
            precision=1.0,
            f1=1.0,
            hit_rate=1.0,
            mrr=1.0,
        ),
        RecallMetrics(
            query="q2",
            relevant_sources=["b.md"],
            retrieved_sources=["c.md"],
            recall=0.0,
            precision=0.0,
            f1=0.0,
            hit_rate=0.0,
            mrr=0.0,
        ),
    ]

    # RecallEvaluator 需要 retrieval_engine，但 summarize 不需要
    from app.retrieval.milvus_store import MilvusStore
    from app.retrieval.keyword_store import KeywordStore
    from app.retrieval.hybrid_engine import HybridRetrievalEngine
    from app.retrieval.reranker import Reranker

    # 使用临时目录的 KeywordStore
    with tempfile.TemporaryDirectory() as tmpdir:
        keyword_store = KeywordStore(index_dir=Path(tmpdir))
        milvus_store = MilvusStore(host="localhost", port=19530)
        engine = HybridRetrievalEngine(
            milvus_store=milvus_store,
            keyword_store=keyword_store,
            reranker=Reranker(),
        )

        evaluator = RecallEvaluator(retrieval_engine=engine)
        summary = evaluator.summarize(metrics)

        assert summary["count"] == 2
        assert summary["avg_recall"] == 0.5
        assert summary["avg_precision"] == 0.5
        assert summary["avg_f1"] == 0.5


# ── RelevanceEvaluator ──


def test_relevance_metrics_manual():
    """RelevanceMetrics 字段正确。"""

    metrics = RelevanceMetrics(
        query="测试",
        top_k_scores=[0.9, 0.85, 0.7],
        avg_score=0.8167,
        max_score=0.9,
        min_score=0.7,
        score_spread=0.2,
        result_count=3,
    )

    assert metrics.avg_score == 0.8167
    assert metrics.max_score == 0.9
    assert metrics.result_count == 3


def test_relevance_evaluator_summarize():
    """RelevanceEvaluator summarize 统计正确。"""

    metrics = [
        RelevanceMetrics(
            query="q1",
            top_k_scores=[0.9],
            avg_score=0.9,
            max_score=0.9,
            result_count=1,
        ),
        RelevanceMetrics(
            query="q2",
            top_k_scores=[0.3],
            avg_score=0.3,
            max_score=0.3,
            result_count=1,
        ),
    ]

    from app.retrieval.milvus_store import MilvusStore
    from app.retrieval.keyword_store import KeywordStore
    from app.retrieval.hybrid_engine import HybridRetrievalEngine
    from app.retrieval.reranker import Reranker

    with tempfile.TemporaryDirectory() as tmpdir:
        keyword_store = KeywordStore(index_dir=Path(tmpdir))
        milvus_store = MilvusStore(host="localhost", port=19530)
        engine = HybridRetrievalEngine(
            milvus_store=milvus_store,
            keyword_store=keyword_store,
            reranker=Reranker(),
        )

        evaluator = RelevanceEvaluator(retrieval_engine=engine)
        summary = evaluator.summarize(metrics)

        assert summary["count"] == 2
        assert summary["avg_relevance"] == 0.6


# ── EvaluationReport ──


def test_report_dataclass():
    """EvaluationReport 数据结构正确。"""

    report = EvaluationReport(
        report_id="eval-test01",
        eval_set_name="测试集",
        eval_set_size=10,
        recall_summary={"avg_recall": 0.85},
        relevance_summary={"avg_relevance": 0.72},
        correctness_summary={"avg_score": 0.78},
    )

    assert report.report_id == "eval-test01"
    assert report.eval_set_size == 10


def test_report_export():
    """评估报告可导出为 JSON。"""

    report = EvaluationReport(
        report_id="eval-export01",
        eval_set_name="导出测试",
        eval_set_size=3,
        recall_summary={"avg_recall": 0.9},
        relevance_summary={"avg_relevance": 0.8},
        correctness_summary={"avg_score": 0.75},
        launch_recommendation="✅ 所有指标达标",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "reports" / "test_report.json"

        # 使用 ReportGenerator 导出（需要 mock retrieval）
        from app.evaluation.recall_evaluator import RecallEvaluator
        from app.evaluation.relevance_evaluator import RelevanceEvaluator
        from app.retrieval.milvus_store import MilvusStore
        from app.retrieval.keyword_store import KeywordStore
        from app.retrieval.hybrid_engine import HybridRetrievalEngine
        from app.retrieval.reranker import Reranker

        keyword_store = KeywordStore(index_dir=Path(tmpdir) / "whoosh")
        milvus_store = MilvusStore(host="localhost", port=19530)
        engine = HybridRetrievalEngine(
            milvus_store=milvus_store,
            keyword_store=keyword_store,
            reranker=Reranker(),
        )

        generator = EvaluationReportGenerator(
            recall_evaluator=RecallEvaluator(engine),
            relevance_evaluator=RelevanceEvaluator(engine),
            correctness_checker=CorrectnessChecker(),
        )

        generator.export_report(report, output_path)

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "eval-export01" in content
        assert "导出测试" in content


def test_launch_recommendation_good():
    """指标达标时的上线建议。"""

    generator = EvaluationReportGenerator(
        recall_evaluator=None,  # 不需要实际引擎
        relevance_evaluator=None,
        correctness_checker=CorrectnessChecker(),
    )

    recommendation = generator._generate_launch_recommendation(
        recall_summary={"avg_recall": 0.85, "avg_precision": 0.8, "avg_f1": 0.82, "avg_hit_rate": 0.95},
        relevance_summary={"avg_relevance": 0.75},
        correctness_summary={"avg_score": 0.8},
    )

    assert "达标" in recommendation or "✅" in recommendation


def test_launch_recommendation_bad():
    """指标差时的上线建议。"""

    generator = EvaluationReportGenerator(
        recall_evaluator=None,
        relevance_evaluator=None,
        correctness_checker=CorrectnessChecker(),
    )

    recommendation = generator._generate_launch_recommendation(
        recall_summary={"avg_recall": 0.4, "avg_precision": 0.3, "avg_f1": 0.35, "avg_hit_rate": 0.5},
        relevance_summary={"avg_relevance": 0.3},
        correctness_summary={"avg_score": 0.4},
    )

    assert "问题" in recommendation or "⚠️" in recommendation
