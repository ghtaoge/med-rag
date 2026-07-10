"""问答路由 — SSE 流式 + 非流式问答。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_chat_orchestrator
from app.core.exceptions import MedRagError

router = APIRouter(prefix="/api/v1/chat", tags=["问答"])


@router.api_route("/stream", methods=["GET", "POST"])
async def chat_stream(
    question: str = Query(..., description="用户问题"),
):
    """流式问答 — SSE 事件流。

    事件序列：intent → search_start → search_result → generation_start → token* → generation_end → correctness → done
    """

    async def event_generator():
        yield ": connected\n\n"
        await asyncio.sleep(0)
        try:
            orchestrator = get_chat_orchestrator()
            stream = orchestrator.chat_stream(question)
            async for event in stream:
                yield event
        except MedRagError as e:
            # 业务异常 → SSE error 事件
            yield f"event: error\ndata: {{\"code\": \"{e.code}\", \"message\": \"{e.message}\"}}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {{\"code\": \"INTERNAL_ERROR\", \"message\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/complete")
async def chat_complete(
    question: str = Query(..., description="用户问题"),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """非流式问答 — 返回完整 JSON 响应。"""

    session = await orchestrator.chat(question)

    return {
        "session_id": session.session_id,
        "question": session.question,
        "answer": session.answer,
        "intent": {
            "category": session.intent.category,
            "confidence": session.intent.confidence,
            "method": session.intent.method,
        },
        "correctness": {
            "confidence": session.correctness.confidence,
            "score": session.correctness.score,
            "source_count": session.correctness.source_count,
            "warnings": session.correctness.warnings,
            "hallucination_flags": session.correctness.hallucination_flags,
        },
        "sources": [
            {
                "id": s.chunk.id,
                "source": s.chunk.source,
                "score": s.score,
                "content_preview": s.chunk.content[:200],
            }
            for s in session.sources
        ],
        "created_at": session.created_at.isoformat(),
    }


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """列出最近的问答会话。"""

    return {"sessions": orchestrator.list_sessions(limit)}


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """获取指定问答会话详情。"""

    session = orchestrator.get_session(session_id)
    if session is None:
        from app.core.exceptions import ValidationError

        raise ValidationError(f"会话不存在: {session_id}")

    return session


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """删除问答会话。"""

    success = orchestrator.delete_session(session_id)
    return {"deleted": success, "session_id": session_id}
