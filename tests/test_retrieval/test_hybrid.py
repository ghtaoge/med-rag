"""RRF 融合测试。"""

from app.core.models import DocumentChunk, SearchResult
from app.retrieval.hybrid import rrf_fusion
from app.retrieval.engine import get_strategy, IntentCategory


def test_rrf_fusion_merges_results():
    """RRF 融合合并两路结果，同 ID 分数相加。"""

    c1 = DocumentChunk(id="a:1", source="a", content="text1")
    c2 = DocumentChunk(id="b:1", source="b", content="text2")

    vector = [SearchResult(chunk=c1, score=0.9), SearchResult(chunk=c2, score=0.7)]
    keyword = [SearchResult(chunk=c2, score=0.8), SearchResult(chunk=c1, score=0.6)]

    fused = rrf_fusion(vector, keyword, k=60)
    assert len(fused) == 2
    # c1 出现在两路 → 分数更高
    fused_ids = [r.chunk.id for r in fused]
    assert fused_ids[0] == "a:1"


def test_rrf_fusion_deduplicates():
    """RRF 融合去重（同 chunk ID 只出现一次）。"""

    c1 = DocumentChunk(id="x:1", source="x", content="text")
    results = [SearchResult(chunk=c1, score=0.9)]
    fused = rrf_fusion(results, results, k=60)
    assert len(fused) == 1
    # 两路都有 → 分数 = 1/(60+0) + 1/(60+0) = 2/61
    assert fused[0].score == 2.0 / 61


def test_rrf_fusion_empty_inputs():
    """RRF 融合处理空输入。"""

    fused = rrf_fusion([], [], k=60)
    assert len(fused) == 0


def test_rrf_fusion_single_source():
    """RRF 融合只有一路结果时正确工作。"""

    c1 = DocumentChunk(id="a:1", source="a", content="text")
    vector = [SearchResult(chunk=c1, score=0.9)]
    fused = rrf_fusion(vector, [], k=60)
    assert len(fused) == 1
    assert fused[0].chunk.id == "a:1"


def test_get_strategy_default():
    """get_strategy 无意图返回默认策略。"""

    strategy = get_strategy(None)
    assert strategy.use_vector is True
    assert strategy.use_keyword is True


def test_get_strategy_comparison():
    """对比意图策略扩大召回范围。"""

    strategy = get_strategy(IntentCategory.COMPARISON)
    assert strategy.vector_top_k == 30
    assert strategy.keyword_top_k == 30
    assert strategy.rerank_top_k == 8
