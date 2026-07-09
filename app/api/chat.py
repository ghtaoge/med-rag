"""对话编排器 — RAG 全流程协调。

意图识别 → 检索 → LLM生成 → 正确性校验 → SSE流式输出。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

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
from app.generation.prompt_builder import (
    LLM_FALLBACK_NOTICE,
    build_llm_fallback_prompt,
    build_prompt,
)
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
        session_store_path: Path | None = None,
    ):
        self.retrieval_engine = retrieval_engine
        self.llm_engine = llm_engine
        self.intent_classifier = intent_classifier
        self.correctness_checker = correctness_checker
        self.redis_client = redis_client
        self.sse_streamer = SSEStreamer()
        self.session_store_path = session_store_path

    async def chat(self, question: str) -> QaSession:
        """非流式问答完整流程。返回完整 QaSession。"""

        session_id = str(uuid.uuid4())

        # 1. 意图识别
        intent_result = self._classify_intent(question)

        # 2. 混合检索
        search_results = self._retrieve(question, intent_result.category)

        # 3. Prompt 构建 + LLM 生成
        use_llm_fallback = self._should_use_llm_fallback(search_results)
        skip_llm_generation = not use_llm_fallback and not search_results

        if use_llm_fallback:
            system_prompt, user_prompt = build_llm_fallback_prompt(question)
        elif skip_llm_generation:
            # 兜底关闭且检索为空 → 返回固定提示语
            answer = "当前知识库中没有检索到相关内容，请尝试其他问题或联系管理员。"
        else:
            system_prompt, user_prompt = build_prompt(
                question, search_results, intent_result.category
            )

        if not skip_llm_generation:
            answer = await self._generate(user_prompt, system_prompt)
            if use_llm_fallback:
                answer = self._mark_llm_fallback_answer(answer)

        # 确定 source_type
        source_type = (
            "llm_fallback" if use_llm_fallback
            else ("no_result" if skip_llm_generation else "knowledge_base")
        )

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
            source_type=source_type,
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

        # 3. 判断是否兜底
        use_llm_fallback = self._should_use_llm_fallback(search_results)

        # 兜底关闭且无结果 → 固定提示语，跳过 LLM 生成
        skip_llm_generation = not use_llm_fallback and not search_results

        if use_llm_fallback:
            yield self.sse_streamer.stream_llm_fallback()
            system_prompt, user_prompt = build_llm_fallback_prompt(question)
        elif skip_llm_generation:
            full_answer = "当前知识库中没有检索到相关内容，请尝试其他问题或联系管理员。"
        else:
            system_prompt, user_prompt = build_prompt(
                question, search_results, intent_result.category
            )

        # LLM 流式生成（仅在非 skip 时执行）
        if not skip_llm_generation:
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

            if use_llm_fallback:
                full_answer = self._mark_llm_fallback_answer(full_answer)

        yield self.sse_streamer.stream_generation_end(full_answer, search_results)

        # 确定 source_type
        source_type = (
            "llm_fallback" if use_llm_fallback
            else ("no_result" if skip_llm_generation else "knowledge_base")
        )

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
            source_type=source_type,
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
            source_type=source_type,
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

    def _should_use_llm_fallback(self, results: list[SearchResult]) -> bool:
        """判断是否应使用 LLM 兜底回答。

        条件：
        1. llm_fallback_enabled 配置为 False → 不兜底
        2. 检索结果为空 → 兜底
        3. 最高 score < min_relevance_score → 兜底
        4. 否则 → 正常 RAG 回答
        """

        from app.core.config import get_config

        cfg = get_config()
        if not cfg["retrieval"]["llm_fallback_enabled"]:
            return False

        if not results:
            return True

        max_score = max(r.score for r in results)
        min_threshold = cfg["retrieval"]["min_relevance_score"]

        return max_score < min_threshold

    def _mark_llm_fallback_answer(self, answer: str) -> str:
        """在回答前插入 LLM 兜底标识。"""

        return f"> ⚠️ {LLM_FALLBACK_NOTICE}仅供参考。\n\n{answer}"

    async def _generate(self, prompt: str, system_prompt: str) -> str:
        """非流式 LLM 生成。"""

        try:
            return await self.llm_engine.generate(prompt, system_prompt)
        except Exception as e:
            logger.error("llm_generate_error", error=str(e))
            raise GenerationError(f"LLM 生成失败: {e}")

    def _save_session(self, session: QaSession) -> None:
        """将问答会话存入 Redis。"""

        session_data = self._serialize_session(session)

        if self.redis_client is None:
            self._save_local_session(session_data)
            return

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        ttl = cfg["redis"]["session_ttl"]

        key = f"{prefix}{session.session_id}"

        try:
            self.redis_client.setex(key, ttl, json.dumps(session_data, ensure_ascii=False))
        except Exception as e:
            logger.warning("save_session_redis_error", error=str(e))
            self._save_local_session(session_data)

    def _serialize_session(self, session: QaSession) -> dict:
        """Convert a QaSession into the API history payload."""

        intent = session.intent or IntentResult(
            category=IntentCategory.QUERY,
            confidence=0,
            method="unknown",
        )
        correctness = session.correctness or CorrectnessResult(
            confidence="low",
            score=0,
            source_count=0,
        )

        return {
            "session_id": session.session_id,
            "question": session.question,
            "answer": session.answer,
            "intent": {
                "category": intent.category,
                "confidence": intent.confidence,
                "method": intent.method,
            },
            "correctness": {
                "confidence": correctness.confidence,
                "score": correctness.score,
                "source_count": correctness.source_count,
                "warnings": correctness.warnings,
                "hallucination_flags": correctness.hallucination_flags,
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

    def _get_local_session_store_path(self) -> Path:
        if self.session_store_path is not None:
            return self.session_store_path

        from app.core.config import get_config

        return Path(get_config()["knowledge_dir"]) / ".med-rag-sessions.json"

    def _load_local_sessions(self) -> dict[str, dict]:
        path = self._get_local_session_store_path()
        if not path.exists():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("load_local_sessions_error", path=str(path), error=str(e))
            return {}

        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}

        if isinstance(data, list):
            return {
                item["session_id"]: item
                for item in data
                if isinstance(item, dict) and item.get("session_id")
            }

        return {}

    def _write_local_sessions(self, sessions: dict[str, dict]) -> None:
        path = self._get_local_session_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(sessions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _save_local_session(self, session_data: dict) -> None:
        try:
            sessions = self._load_local_sessions()
            sessions[session_data["session_id"]] = session_data
            ordered = sorted(
                sessions.values(),
                key=lambda s: s.get("created_at", ""),
                reverse=True,
            )[:100]
            self._write_local_sessions({s["session_id"]: s for s in ordered})
        except Exception as e:
            logger.warning("save_local_session_error", error=str(e))

    def get_session(self, session_id: str) -> dict | None:
        """从 Redis 获取问答会话。"""

        if self.redis_client is None:
            return self._load_local_sessions().get(session_id)

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        key = f"{prefix}{session_id}"

        try:
            data = self.redis_client.get(key)
            if data is None:
                return self._load_local_sessions().get(session_id)
            return json.loads(data)
        except Exception as e:
            logger.warning("get_session_redis_error", error=str(e))
            return self._load_local_sessions().get(session_id)

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """列出最近的问答会话。"""

        if self.redis_client is None:
            sessions = list(self._load_local_sessions().values())
            sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            return sessions[:limit]

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
            if sessions:
                return sessions[:limit]
            local_sessions = list(self._load_local_sessions().values())
            local_sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            return local_sessions[:limit]
        except Exception as e:
            logger.warning("list_sessions_redis_error", error=str(e))
            sessions = list(self._load_local_sessions().values())
            sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            return sessions[:limit]

    def delete_session(self, session_id: str) -> bool:
        """删除问答会话。"""

        if self.redis_client is None:
            sessions = self._load_local_sessions()
            deleted = sessions.pop(session_id, None) is not None
            if deleted:
                self._write_local_sessions(sessions)
            return deleted

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        key = f"{prefix}{session_id}"

        try:
            deleted = bool(self.redis_client.delete(key))
            sessions = self._load_local_sessions()
            local_deleted = sessions.pop(session_id, None) is not None
            if local_deleted:
                self._write_local_sessions(sessions)
            return deleted or local_deleted
        except Exception as e:
            logger.warning("delete_session_redis_error", error=str(e))
            sessions = self._load_local_sessions()
            deleted = sessions.pop(session_id, None) is not None
            if deleted:
                self._write_local_sessions(sessions)
            return deleted
