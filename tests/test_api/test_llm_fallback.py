"""LLM 兜底逻辑测试。"""

from app.api.chat import ChatOrchestrator
from app.core.models import DocumentChunk, SearchResult, ChunkMetadata


def _make_result(score: float) -> SearchResult:
    """构造一个指定分数的 SearchResult。"""

    return SearchResult(
        chunk=DocumentChunk(
            id="test-chunk",
            source="test.pdf",
            content="测试内容",
        ),
        score=score,
    )


def test_should_use_llm_fallback_empty_results():
    """检索结果为空 → 应兜底。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    assert orchestrator._should_use_llm_fallback([]) is True


def test_should_use_llm_fallback_low_score():
    """RRF 分数虽低但有结果 → 不兜底（RRF 分数是排名分数，不代表相关性低）。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    results = [_make_result(0.03), _make_result(0.02)]
    assert orchestrator._should_use_llm_fallback(results) is False


def test_should_use_llm_fallback_high_score():
    """有检索结果 → 不兜底。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    results = [_make_result(0.08), _make_result(0.06)]
    assert orchestrator._should_use_llm_fallback(results) is False


def test_should_use_llm_fallback_disabled_config(monkeypatch):
    """llm_fallback_enabled=False → 不兜底（即使空结果）。"""

    from app.core import config as cfg_module

    # 清除缓存以便重新加载配置
    if hasattr(cfg_module.get_config, "_cache"):
        del cfg_module.get_config._cache

    monkeypatch.setenv("RAG_LLM_FALLBACK_ENABLED", "false")

    orchestrator = ChatOrchestrator(None, None, None, None)
    assert orchestrator._should_use_llm_fallback([]) is False

    monkeypatch.delenv("RAG_LLM_FALLBACK_ENABLED", raising=False)
    # 清除缓存恢复原配置
    if hasattr(cfg_module.get_config, "_cache"):
        del cfg_module.get_config._cache


def test_mark_llm_fallback_answer():
    """兜底回答应带 LLM_FALLBACK_NOTICE 前缀。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    raw = "阿司匹林是一种解热镇痛药。"
    marked = orchestrator._mark_llm_fallback_answer(raw)
    from app.generation.prompt_builder import LLM_FALLBACK_NOTICE
    assert LLM_FALLBACK_NOTICE in marked
    assert raw in marked


def test_mark_llm_fallback_answer_format():
    """兜底回答应包含 blockquote 格式和 ⚠️ 标记。"""

    orchestrator = ChatOrchestrator(None, None, None, None)
    raw = "阿司匹林是一种解热镇痛药。"
    marked = orchestrator._mark_llm_fallback_answer(raw)
    assert "⚠️" in marked
    assert marked.startswith("> ")
