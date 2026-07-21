"""Authenticated chat, streaming, and user-scoped session routes."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.chat import ChatOrchestrator
from app.core.dependencies import get_chat_orchestrator
from app.core.exceptions import MedRagError, NotFoundError
from app.security.permissions import Permission, permission_dependency
from app.security.principal import Principal, get_current_principal

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["问答"],
    dependencies=[Depends(permission_dependency(Permission.CHAT))],
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)


def _stream_response(
    question: str,
    principal: Principal,
    orchestrator: ChatOrchestrator,
    request_id: str,
) -> StreamingResponse:
    async def event_generator():
        yield ": connected\n\n"
        await asyncio.sleep(0)
        try:
            async for event in orchestrator.chat_stream(
                question, principal, request_id
            ):
                yield event
        except MedRagError as exc:
            yield (
                f'event: error\ndata: {{"code": "{exc.code}", '
                f'"message": "{exc.message}"}}\n\n'
            )
        except Exception:
            yield (
                'event: error\ndata: {"code":"INTERNAL_ERROR",'
                '"message":"内部服务异常，请稍后重试"}\n\n'
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/stream", deprecated=True)
async def chat_stream_legacy(
    request: Request,
    question: str = Query(..., description="用户问题"),
    principal: Principal = Depends(get_current_principal),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    return _stream_response(question, principal, orchestrator, request_id)


@router.post("/stream")
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    principal: Principal = Depends(get_current_principal),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    return _stream_response(payload.question, principal, orchestrator, request_id)


@router.post("/complete")
async def chat_complete(
    request: Request,
    question: str = Query(..., description="用户问题"),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
    principal: Principal = Depends(get_current_principal),
):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    session = await orchestrator.chat(question, principal, request_id)
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
                "id": result.chunk.id,
                "source": result.chunk.source,
                "score": result.score,
                "content_preview": result.chunk.content[:200],
                "document_id": result.chunk.metadata.document_id,
                "document_version_id": result.chunk.metadata.document_version_id,
            }
            for result in session.sources
        ],
        "created_at": session.created_at.isoformat(),
        "safety": session.safety,
        "request_id": session.request_id,
    }


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
    principal: Principal = Depends(get_current_principal),
):
    return {"sessions": orchestrator.list_sessions(principal, limit)}


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
    principal: Principal = Depends(get_current_principal),
):
    session = orchestrator.get_session(session_id, principal)
    if session is None:
        raise NotFoundError("会话不存在")
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
    principal: Principal = Depends(get_current_principal),
):
    if not orchestrator.delete_session(session_id, principal):
        raise NotFoundError("会话不存在")
    return {"deleted": True, "session_id": session_id}
