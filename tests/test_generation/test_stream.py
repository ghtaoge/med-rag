"""SSE 流式输出测试。"""

import json

from app.generation.stream import SSEStreamer
from app.core.models import (
    IntentResult,
    CorrectnessResult,
    IntentCategory,
    ConfidenceLevel,
)


def test_stream_intent():
    """intent 事件格式正确。"""

    streamer = SSEStreamer()
    intent = IntentResult(category=IntentCategory.QUERY, confidence=0.92, method="rule")
    event = streamer.stream_intent(intent)
    assert event.startswith("event: intent\n")
    assert "data: " in event
    data = json.loads(event.split("data: ")[1].strip())
    assert data["type"] == "query"
    assert data["confidence"] == 0.92


def test_stream_search_start():
    """search_start 事件格式正确。"""

    streamer = SSEStreamer()
    event = streamer.stream_search_start("hybrid", ["vector", "keyword"])
    data = json.loads(event.split("data: ")[1].strip())
    assert data["strategy"] == "hybrid"
    assert data["sources"] == ["vector", "keyword"]


def test_stream_token():
    """token 事件格式正确。"""

    streamer = SSEStreamer()
    event = streamer.stream_token("根据")
    data = json.loads(event.split("data: ")[1].strip())
    assert data["content"] == "根据"


def test_stream_correctness():
    """correctness 事件格式正确。"""

    streamer = SSEStreamer()
    result = CorrectnessResult(
        confidence=ConfidenceLevel.HIGH, score=0.85, source_count=3, warnings=[]
    )
    event = streamer.stream_correctness(result)
    data = json.loads(event.split("data: ")[1].strip())
    assert data["confidence"] == "high"
    assert data["score"] == 0.85
    assert data["source_count"] == 3


def test_stream_done():
    """done 事件格式正确。"""

    streamer = SSEStreamer()
    event = streamer.stream_done("abc123")
    data = json.loads(event.split("data: ")[1].strip())
    assert data["session_id"] == "abc123"


def test_stream_llm_fallback():
    """llm_fallback 事件格式正确。"""

    streamer = SSEStreamer()
    event = streamer.stream_llm_fallback()
    assert event.startswith("event: llm_fallback\n")
    data = json.loads(event.split("data: ")[1].strip())
    assert "notice" in data
    assert "知识库" in data["notice"]
