"""对话编排器 — RAG 全流程协调。

意图识别 → 检索 → LLM生成 → 正确性校验 → SSE流式输出。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from app.core.models import (
    QaSession,
    IntentResult,
    SearchResult,
    CorrectnessResult,
    IntentCategory,
)
from app.core.exceptions import RetrievalError, GenerationError
from app.core.logging import get_logger

from app.retrieval.hybrid_engine import HybridRetrievalEngine
from app.generation.engine import LlmEngine
from app.generation.prompt_builder import build_prompt
from app.generation.stream import SSEStreamer
from app.intent.classifier import IntentClassifier
from app.evaluation.correctness_check import CorrectnessChecker

logger = get_logger(__name__)


class ChatOrchestrator:
    """对话编排器。

    协调完整的 RAG 问答流程：
    1. 意图识别 → 选择检索策略
    2. 混合检索 → 多路召回 + RRF + Rerank
    3. Prompt 构建 → LLM 生成回答
    4. 正确性校验 → 置信度 + 幻觉检测
    5. 会话存储 → Redis 持久化
    """

    def __init__(
        self,
        retrieval_engine: HybridRetrievalEngine,
        llm_engine: LlmEngine,
        intent_classifier: IntentClassifier,
        correctness_checker: CorrectnessChecker,
        redis_client=None,
    ):
        self.retrieval_engine = retrieval_engine
        self.llm_engine = llm_engine
        self.intent_classifier = intent_classifier
        self.correctness_checker = correctness_checker
        self.redis_client = redis_client
        self.sse_streamer = SSEStreamer()

    async def chat(self, question: str) -> QaSession:
        """非流式问答完整流程。返回完整 QaSession。"""

        session_id = str(uuid.uuid4())

        # 1. 意图识别
        intent_result = self._classify_intent(question)

        # 2. 混合检索
        search_results = self._retrieve(question, intent_result.category)

        # 3. Prompt 构建 + LLM 生成
        system_prompt, user_prompt = build_prompt(
            question, search_results, intent_result.category
        )
        answer = await self._generate(user_prompt, system_prompt)

        # 4. 正确性校验
        correctness = self.correctness_checker.check(answer, search_results)

        # 5. 组装会话
        session = QaSession(
            session_id=session_id,
            question=question,
            answer=answer,
            sources=search_results,
            intent=intent_result,
            correctness=correctness,
            created_at=datetime.now(),
        )

        # 6. 存入 Redis
        self._save_session(session)

        logger.info(
            "chat_completed",
            session_id=session_id,
            intent=intent_result.category,
            confidence=correctness.confidence,
            source_count=correctness.source_count,
        )

        return session

    async def chat_stream(self, question: str) -> AsyncIterator[str]:
        """流式问答完整流程。逐步生成 SSE 事件。"""

        session_id = str(uuid.uuid4())

        # 1. 意图识别
        intent_result = self._classify_intent(question)
        yield self.sse_streamer.stream_intent(intent_result)

        # 2. 混合检索
        yield self.sse_streamer.stream_search_start(
            strategy=intent_result.category,
            sources=["milvus", "whoosh"],
        )

        search_results = self._retrieve(question, intent_result.category)

        yield self.sse_streamer.stream_search_result(
            chunks=len(search_results),
            top_score=search_results[0].score if search_results else 0.0,
        )

        # 3. Prompt 构建 + LLM 流式生成
        system_prompt, user_prompt = build_prompt(
            question, search_results, intent_result.category
        )

        yield self.sse_streamer.stream_generation_start(self.llm_engine.model_name)

        full_answer = ""
        try:
            token_stream = self.llm_engine.generate_stream(user_prompt, system_prompt)
            async for token in token_stream:
                full_answer += token
                yield self.sse_streamer.stream_token(token)
        except Exception as e:
            logger.error("llm_stream_error", error=str(e))
            raise GenerationError(f"LLM 流式生成失败: {e}")

        yield self.sse_streamer.stream_generation_end(full_answer, search_results)

        # 4. 正确性校验
        correctness = self.correctness_checker.check(full_answer, search_results)
        yield self.sse_streamer.stream_correctness(correctness)

        # 5. 存入 Redis
        session = QaSession(
            session_id=session_id,
            question=question,
            answer=full_answer,
            sources=search_results,
            intent=intent_result,
            correctness=correctness,
            created_at=datetime.now(),
        )
        self._save_session(session)

        # 6. 完成
        yield self.sse_streamer.stream_done(session_id)

        logger.info(
            "chat_stream_completed",
            session_id=session_id,
            intent=intent_result.category,
            confidence=correctness.confidence,
        )

    def _classify_intent(self, question: str) -> IntentResult:
        """意图识别。"""

        try:
            return self.intent_classifier.classify(question)
        except Exception as e:
            logger.warning("intent_classify_failed", error=str(e))
            return IntentResult(
                category=IntentCategory.QUERY,
                confidence=0.5,
                method="fallback",
            )

    def _retrieve(
        self, question: str, intent: IntentCategory, top_k: int = 5
    ) -> list[SearchResult]:
        """混合检索。"""

        try:
            return self.retrieval_engine.search(
                question=question, top_k=top_k, intent=intent
            )
        except Exception as e:
            logger.warning("retrieval_failed", error=str(e))
            raise RetrievalError(f"检索引擎异常: {e}")

    async def _generate(self, prompt: str, system_prompt: str) -> str:
        """非流式 LLM 生成。"""

        try:
            return await self.llm_engine.generate(prompt, system_prompt)
        except Exception as e:
            logger.error("llm_generate_error", error=str(e))
            raise GenerationError(f"LLM 生成失败: {e}")

    def _save_session(self, session: QaSession) -> None:
        """将问答会话存入 Redis。"""

        if self.redis_client is None:
            return

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        ttl = cfg["redis"]["session_ttl"]

        key = f"{prefix}{session.session_id}"

        session_data = {
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

        self.redis_client.setex(key, ttl, json.dumps(session_data, ensure_ascii=False))

    def get_session(self, session_id: str) -> dict | None:
        """从 Redis 获取问答会话。"""

        if self.redis_client is None:
            return None

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        key = f"{prefix}{session_id}"

        try:
            data = self.redis_client.get(key)
            if data is None:
                return None
            return json.loads(data)
        except Exception as e:
            logger.warning("get_session_redis_error", error=str(e))
            return None

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """列出最近的问答会话。"""

        if self.redis_client is None:
            return []

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]

        try:
            keys = self.redis_client.keys(f"{prefix}*")
            sessions = []
            for key in keys[:limit]:
                data = self.redis_client.get(key)
                if data:
                    sessions.append(json.loads(data))

            # 按时间倒序
            sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            return sessions
        except Exception as e:
            logger.warning("list_sessions_redis_error", error=str(e))
            return []

    def delete_session(self, session_id: str) -> bool:
        """删除问答会话。"""

        if self.redis_client is None:
            return False

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        key = f"{prefix}{session_id}"

        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.warning("delete_session_redis_error", error=str(e))
            return False
