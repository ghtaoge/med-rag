"""正确性校验测试。"""

from app.evaluation.correctness_check import CorrectnessChecker
from app.core.models import DocumentChunk, SearchResult, ConfidenceLevel


def test_high_confidence_multiple_sources():
    """3 个独立来源 → 高置信度。"""

    checker = CorrectnessChecker()
    sources = [
        SearchResult(chunk=DocumentChunk(id="a:1", source="a.md", content="适应症包括解热镇痛"), score=0.9),
        SearchResult(chunk=DocumentChunk(id="b:1", source="b.md", content="适应症包括解热镇痛"), score=0.85),
        SearchResult(chunk=DocumentChunk(id="c:1", source="c.md", content="适应症包括解热镇痛"), score=0.8),
    ]
    result = checker.check("适应症包括解热镇痛", sources)
    assert result.confidence == ConfidenceLevel.HIGH
    assert result.source_count == 3
    assert result.warnings == []


def test_medium_confidence_two_sources():
    """2 个独立来源 → 中置信度。"""

    sources = [
        SearchResult(chunk=DocumentChunk(id="a:1", source="a.md", content="内容"), score=0.9),
        SearchResult(chunk=DocumentChunk(id="b:1", source="b.md", content="内容"), score=0.8),
    ]
    result = CorrectnessChecker().check("内容", sources)
    assert result.confidence == ConfidenceLevel.MEDIUM
    assert result.source_count == 2


def test_low_confidence_single_source():
    """仅单一来源 → 低置信度 + 警告。"""

    sources = [
        SearchResult(chunk=DocumentChunk(id="a:1", source="a.md", content="内容"), score=0.9),
    ]
    result = CorrectnessChecker().check("内容", sources)
    assert result.confidence == ConfidenceLevel.LOW
    assert any("仅单一来源" in w for w in result.warnings)
    assert result.source_count == 1


def test_no_sources():
    """无检索结果 → 极低置信度。"""

    result = CorrectnessChecker().check("回答内容", [])
    assert result.confidence == ConfidenceLevel.LOW
    assert result.score == 0.3


def test_medical_keyword_hallucination():
    """医疗关键信息无来源 → 降级置信度。"""

    sources = [
        SearchResult(chunk=DocumentChunk(id="a:1", source="a.md", content="药品名称"), score=0.9),
    ]
    answer = "阿司匹林剂量为每日300mg"
    result = CorrectnessChecker().check(answer, sources)
    # "剂量" 在回答中但不在来源内容中 → 幻觉标记
    assert result.confidence != ConfidenceLevel.HIGH
    assert len(result.hallucination_flags) > 0
