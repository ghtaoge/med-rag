"""SSE 流式输出。

将 RAG 流程包装为 SSE 事件序列，供前端实时渲染。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from app.core.models import (
    SearchResult,
    IntentResult,
    CorrectnessResult,
    ConfidenceLevel,
)


class SSEStreamer:
    """SSE 事件流生成器。

    事件类型：
    - intent: 意图识别结果
    - search_start: 检索开始
    - search_result: 检索完成（片段数量）
    - generation_start: LLM 生成开始
    - token: 流式 token
    - generation_end: 生成完成
    - correctness: 正确性校验结果
    - done: 流程结束
    """

    def stream_intent(self, intent_result: IntentResult) -> str:
        """生成 intent SSE 事件。"""

        data = {
            "type": intent_result.category,
            "confidence": intent_result.confidence,
            "method": intent_result.method,
        }
        return f"event: intent\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream_search_start(self, strategy: str, sources: list[str]) -> str:
        """生成 search_start SSE 事件。"""

        data = {"strategy": strategy, "sources": sources}
        return f"event: search_start\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream_search_result(self, chunks: int, top_score: float) -> str:
        """生成 search_result SSE 事件。"""

        data = {"chunks": chunks, "top_score": top_score}
        return f"event: search_result\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream_generation_start(self, model: str) -> str:
        """生成 generation_start SSE 事件。"""

        data = {"model": model}
        return f"event: generation_start\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream_token(self, content: str) -> str:
        """生成 token SSE 事件。"""

        data = {"content": content}
        return f"event: token\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream_generation_end(
        self, full_answer: str, sources: list[SearchResult]
    ) -> str:
        """生成 generation_end SSE 事件。"""

        source_data = [
            {
                "id": s.chunk.id,
                "source": s.chunk.source,
                "score": s.score,
                "content": s.chunk.content[:200],  # 截取前 200 字作为预览
            }
            for s in sources
        ]
        data = {"full_answer": full_answer, "sources": source_data}
        return f"event: generation_end\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream_correctness(self, result: CorrectnessResult) -> str:
        """生成 correctness SSE 事件。"""

        data = {
            "confidence": result.confidence,
            "score": result.score,
            "source_count": result.source_count,
            "warnings": result.warnings,
            "hallucination_flags": result.hallucination_flags,
        }
        return f"event: correctness\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream_done(self, session_id: str) -> str:
        """生成 done SSE 事件。"""

        data = {"session_id": session_id}
        return f"event: done\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
