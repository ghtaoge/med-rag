"""对话编排器 — RAG 全流程协调。

意图识别 → 检索 → LLM生成 → 正确性校验 → SSE流式输出。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.models import (
    QaSession,
    IntentResult,
    SearchResult,
    CorrectnessResult,
    IntentCategory,
)
from app.core.exceptions import GenerationError, MedRagError, RetrievalError
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
from app.retrieval.access import RetrievalAccess

if TYPE_CHECKING:
    from app.security.principal import Principal

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

    async def chat(self, question: str, principal: Principal) -> QaSession:
        """非流式问答完整流程。返回完整 QaSession。"""

        session_id = str(uuid.uuid4())

        # 1. 意图识别
        intent_result = self._classify_intent(question)

        # 2. 混合检索
        search_results = self._retrieve(question, intent_result.category, principal)

        # 3. Prompt 构建 + LLM 生成
        # 检索为空时可以按配置走 LLM 通用知识兜底。
        # 如果兜底关闭，则跳过 LLM，直接返回“知识库无结果”的固定提示。
        use_llm_fallback = self._should_use_llm_fallback(search_results)
        skip_llm_generation = not use_llm_fallback and not search_results

        if use_llm_fallback:
            # 兜底 prompt 不拼接知识库来源，避免模型伪造“来自文档”的引用。
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
                # 非流式接口需要把提示写入最终答案本身，
                # 这样历史记录、复制答案、接口调用方都能看到来源标识。
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
            user_id=principal.user_id,
            department_ids=principal.department_ids,
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

    async def chat_stream(
        self, question: str, principal: Principal
    ) -> AsyncIterator[str]:
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

        search_results = self._retrieve(question, intent_result.category, principal)

        yield self.sse_streamer.stream_search_result(
            chunks=len(search_results),
            top_score=search_results[0].score if search_results else 0.0,
        )

        # 3. 判断是否兜底
        # 流式接口会额外发送 llm_fallback 事件，前端可立即展示“来源于模型”的提示条。
        # 最终答案仍会在 generation_end 中带上完整文本，便于历史记录复用同一套结构。
        use_llm_fallback = self._should_use_llm_fallback(search_results)

        # 兜底关闭且无结果 → 固定提示语，跳过 LLM 生成
        skip_llm_generation = not use_llm_fallback and not search_results

        if use_llm_fallback:
            yield self.sse_streamer.stream_llm_fallback()
            # 兜底回答只基于模型通用知识，不附带知识库片段，
            # 系统提示会要求模型不要编造来源、页码或文档名。
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
                # token 已经逐步发送给前端；这里再标记 full_answer，
                # 用于 generation_end、正确性校验和会话持久化。
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
            user_id=principal.user_id,
            department_ids=principal.department_ids,
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
        self,
        question: str,
        intent: IntentCategory,
        principal: Principal,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """混合检索。"""

        try:
            return self.retrieval_engine.search(
                question=question,
                top_k=top_k,
                intent=intent,
                access=RetrievalAccess(principal.user_id, principal.department_ids),
            )
        except MedRagError:
            raise
        except Exception as e:
            logger.warning("retrieval_failed", error=str(e))
            raise RetrievalError(f"检索引擎异常: {e}")

    def _should_use_llm_fallback(self, results: list[SearchResult]) -> bool:
        """判断是否应使用 LLM 兜底回答。

        条件：
        1. llm_fallback_enabled 配置为 False → 不兜底
        2. 检索结果为空 → 兜底
        3. 否则 → 正常 RAG 回答

        注意：不根据 score 阈值判断，因为 RRF 融合分数是排名分数（约 0.01-0.03），
        不反映绝对相关性。检索引擎返回结果即代表有匹配。
        """

        from app.core.config import get_config

        cfg = get_config()
        if not cfg["retrieval"]["llm_fallback_enabled"]:
            return False

        # 当前混合检索采用 RRF 分数，分值代表排名融合结果，不是语义相似度绝对值。
        # 因此暂时只在“完全没有结果”时兜底，避免把有效但低分的知识库命中误判掉。
        if not results:
            return True

        return False

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
            if self._local_fallback_enabled():
                self._save_local_session(session_data)
            return

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        ttl = cfg["redis"]["session_ttl"]

        key = self._session_key(session.user_id, session.session_id, prefix)

        try:
            self.redis_client.setex(key, ttl, json.dumps(session_data, ensure_ascii=False))
        except Exception as e:
            # Redis 不可用时降级到本地文件，保证历史记录页面仍然有数据可读。
            logger.warning("save_session_redis_error", error=str(e))
            if self._local_fallback_enabled():
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
            "user_id": session.user_id,
            "department_ids": session.department_ids,
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
                    "document_id": s.chunk.metadata.document_id,
                    "document_version_id": s.chunk.metadata.document_version_id,
                }
                for s in session.sources
            ],
            "source_type": session.source_type,
            "created_at": session.created_at.isoformat(),
        }

    def _get_local_session_store_path(self) -> Path:
        if self.session_store_path is not None:
            return self.session_store_path

        from app.core.config import get_config

        # 本地历史记录跟随 knowledge_dir 存放，并已在 .gitignore 中忽略，
        # 避免把用户问答内容误提交到仓库。
        return Path(get_config()["knowledge_dir"]) / ".med-rag-sessions.json"

    def _local_fallback_enabled(self) -> bool:
        if self.session_store_path is not None:
            return True
        from app.core.config import get_config

        return get_config().get("app", {}).get("environment") == "test"

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
        # 先写临时文件再原子替换，降低进程中断时写出半截 JSON 的概率。
        tmp_path.replace(path)

    def _save_local_session(self, session_data: dict) -> None:
        try:
            sessions = self._load_local_sessions()
            key = self._session_key(
                session_data["user_id"], session_data["session_id"], ""
            )
            sessions[key] = session_data
            ordered = sorted(
                sessions.values(),
                key=lambda s: s.get("created_at", ""),
                reverse=True,
            )[:100]
            # 本地兜底存储只保留最近 100 条，避免开发环境长期使用后文件过大。
            self._write_local_sessions(
                {
                    self._session_key(s["user_id"], s["session_id"], ""): s
                    for s in ordered
                }
            )
        except Exception as e:
            logger.warning("save_local_session_error", error=str(e))

    @staticmethod
    def _session_key(user_id: str, session_id: str, prefix: str = "") -> str:
        return f"{prefix}{user_id}:{session_id}"

    def _local_sessions_for(self, principal: Principal) -> dict[str, dict]:
        return {
            key: value
            for key, value in self._load_local_sessions().items()
            if value.get("user_id") == principal.user_id
        }

    def get_session(self, session_id: str, principal: Principal) -> dict | None:
        """从 Redis 获取问答会话。"""

        if self.redis_client is None:
            if not self._local_fallback_enabled():
                return None
            return self._local_sessions_for(principal).get(
                self._session_key(principal.user_id, session_id)
            )

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        key = self._session_key(principal.user_id, session_id, prefix)

        try:
            data = self.redis_client.get(key)
            if data is None:
                if not self._local_fallback_enabled():
                    return None
                return self._local_sessions_for(principal).get(
                    self._session_key(principal.user_id, session_id)
                )
            return json.loads(data)
        except Exception as e:
            logger.warning("get_session_redis_error", error=str(e))
            if not self._local_fallback_enabled():
                return None
            return self._local_sessions_for(principal).get(
                self._session_key(principal.user_id, session_id)
            )

    def list_sessions(self, principal: Principal, limit: int = 20) -> list[dict]:
        """列出最近的问答会话。"""

        if self.redis_client is None:
            if not self._local_fallback_enabled():
                return []
            sessions = list(self._local_sessions_for(principal).values())
            sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            return sessions[:limit]

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]

        try:
            keys = self.redis_client.keys(f"{prefix}{principal.user_id}:*")
            sessions = []
            for key in keys[:limit]:
                data = self.redis_client.get(key)
                if data:
                    sessions.append(json.loads(data))

            # 按时间倒序
            sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            if sessions:
                return sessions[:limit]
            if not self._local_fallback_enabled():
                return []
            local_sessions = list(self._local_sessions_for(principal).values())
            local_sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            return local_sessions[:limit]
        except Exception as e:
            logger.warning("list_sessions_redis_error", error=str(e))
            if not self._local_fallback_enabled():
                return []
            sessions = list(self._local_sessions_for(principal).values())
            sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            return sessions[:limit]

    def delete_session(self, session_id: str, principal: Principal) -> bool:
        """删除问答会话。"""

        if self.redis_client is None:
            if not self._local_fallback_enabled():
                return False
            sessions = self._load_local_sessions()
            local_key = self._session_key(principal.user_id, session_id)
            deleted = sessions.pop(local_key, None) is not None
            if deleted:
                self._write_local_sessions(sessions)
            return deleted

        from app.core.config import get_config

        cfg = get_config()
        prefix = cfg["redis"]["session_prefix"]
        key = self._session_key(principal.user_id, session_id, prefix)

        try:
            deleted = bool(self.redis_client.delete(key))
            sessions = self._load_local_sessions()
            local_key = self._session_key(principal.user_id, session_id)
            local_deleted = sessions.pop(local_key, None) is not None
            if local_deleted:
                self._write_local_sessions(sessions)
            return deleted or local_deleted
        except Exception as e:
            logger.warning("delete_session_redis_error", error=str(e))
            if not self._local_fallback_enabled():
                return False
            sessions = self._load_local_sessions()
            local_key = self._session_key(principal.user_id, session_id)
            deleted = sessions.pop(local_key, None) is not None
            if deleted:
                self._write_local_sessions(sessions)
            return deleted
