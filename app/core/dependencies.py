"""Med-Rag FastAPI 依赖注入。

所有 get_* 函数作为 FastAPI Depends 使用。
管理模块实例的生命周期。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import redis
from fastapi import Depends

from app.core.config import get_config
from app.core.logging import get_logger

from app.retrieval.milvus_store import MilvusStore
from app.retrieval.keyword_store import KeywordStore
from app.retrieval.hybrid_engine import HybridRetrievalEngine
from app.retrieval.reranker import Reranker

from app.generation.engine import LlmEngine
from app.generation.deepseek_provider import DeepSeekProvider
from app.generation.qwen_provider import QwenProvider
from app.generation.zhipu_provider import ZhipuProvider

from app.intent.classifier import IntentClassifier
from app.evaluation.correctness_check import CorrectnessChecker
from app.documents.sync import DocumentSync
from app.documents.validator import DocumentValidator

from app.api.chat import ChatOrchestrator
from app.security.auth_service import AuthService
from app.security.database import build_engine, build_session_factory
from app.security.identity_provider import LocalIdentityProvider
from app.security.repository import SecurityRepository

logger = get_logger(__name__)


@lru_cache
def get_config_dep() -> dict:
    """获取配置（FastAPI Depends）。"""

    return get_config()


@lru_cache
def get_security_session_factory():
    """获取关系数据库 Session 工厂。"""

    cfg = get_config()
    engine = build_engine(cfg["database"]["url"])
    return build_session_factory(engine)


def get_db_session():
    """提供请求级数据库事务边界。"""

    factory = get_security_session_factory()
    with factory() as session:
        yield session


def get_auth_service(
    session=Depends(get_db_session),
    config: dict = Depends(get_config_dep),
) -> AuthService:
    repository = SecurityRepository(session)
    provider = LocalIdentityProvider(repository)
    return AuthService(session, repository, provider, config)

@lru_cache
def get_redis_client() -> redis.Redis | None:
    """获取 Redis 客户端。Redis 不可用时返回 None，各模块需自行降级。"""

    cfg = get_config()
    try:
        client = redis.Redis(
            host=cfg["redis"]["host"],
            port=cfg["redis"]["port"],
            db=cfg["redis"]["db"],
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()  # 验证连接
        logger.info("redis_connected", host=cfg["redis"]["host"], port=cfg["redis"]["port"])
        return client
    except Exception as e:
        logger.warning("redis_not_available", error=str(e))
        return None


@lru_cache
def get_milvus_store() -> MilvusStore | None:
    """获取延迟连接的 Milvus 存储实例。"""

    cfg = get_config()
    store = MilvusStore(
        host=cfg["milvus"]["host"],
        port=cfg["milvus"]["port"],
    )
    logger.info("milvus_store_created", collection=cfg["milvus"]["collection_name"])
    return store


@lru_cache
def get_keyword_store() -> KeywordStore:
    """获取 Whoosh 关键词存储实例。"""

    cfg = get_config()
    store = KeywordStore(index_dir=Path(cfg["whoosh_dir"]))
    logger.info("keyword_store_initialized", index_dir=cfg["whoosh_dir"])
    return store


@lru_cache
def get_retrieval_engine() -> HybridRetrievalEngine:
    """获取混合检索引擎实例。"""

    return HybridRetrievalEngine(
        milvus_store=get_milvus_store(),
        keyword_store=get_keyword_store(),
        reranker=Reranker(),
    )


@lru_cache
def get_llm_engine() -> LlmEngine:
    """获取 LLM 引擎实例（根据配置选择 Provider）。"""

    cfg = get_config()
    provider = cfg["llm"]["provider"]

    providers_map = {
        "deepseek": DeepSeekProvider,
        "qwen": QwenProvider,
        "zhipu": ZhipuProvider,
    }

    provider_cls = providers_map.get(provider)
    if provider_cls is None:
        raise ValueError(f"未支持的 LLM Provider: {provider}")

    provider_cfg = cfg["llm"][provider]
    engine = provider_cls(
        api_key=provider_cfg["api_key"],
        model=provider_cfg["model"],
        temperature=cfg["llm"]["temperature"],
        max_tokens=cfg["llm"]["max_tokens"],
    )

    logger.info("llm_initialized", provider=provider, model=provider_cfg["model"])
    return engine


@lru_cache
def get_intent_classifier() -> IntentClassifier:
    """获取意图分类器实例。"""

    return IntentClassifier(llm_engine=get_llm_engine())


@lru_cache
def get_correctness_checker() -> CorrectnessChecker:
    """获取正确性校验器实例。"""

    return CorrectnessChecker()


@lru_cache
def get_document_sync() -> DocumentSync:
    """获取文档同步引擎实例。"""

    cfg = get_config()
    return DocumentSync(
        knowledge_dir=Path(cfg["knowledge_dir"]),
        redis_client=get_redis_client(),
        milvus_store=get_milvus_store(),
        keyword_store=get_keyword_store(),
    )


@lru_cache
def get_document_validator() -> DocumentValidator:
    """获取文档校验器实例。"""

    return DocumentValidator()


@lru_cache
def get_chat_orchestrator() -> ChatOrchestrator:
    """获取对话编排器实例（核心问答流程协调器）。"""

    return ChatOrchestrator(
        retrieval_engine=get_retrieval_engine(),
        llm_engine=get_llm_engine(),
        intent_classifier=get_intent_classifier(),
        correctness_checker=get_correctness_checker(),
        redis_client=get_redis_client(),
    )
