"""Med-Rag 配置加载模块。

配置优先级：环境变量 > config.yaml > 默认值。
支持 Redis/Milvus/LLM/切块/检索等全部配置项。
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = BASE_DIR / "config.yaml"
ENV_FILE = BASE_DIR / ".env"

DEFAULTS: dict[str, Any] = {
    "app": {
        "name": "Med-Rag 知识助手",
        "version": "1.0.0",
        "host": "0.0.0.0",
        "port": 8000,
        "environment": "development",
    },
    "milvus": {
        "host": "localhost",
        "port": 19530,
        "collection_name": "med_rag_chunks",
        "embedding_dim": 1024,
        "index_type": "HNSW",
        "metric_type": "COSINE",
        "M": 32,
        "efConstruction": 256,
        "ef_search": 128,
    },
    "redis": {
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "file_hash_prefix": "med_rag:file_hash:",
        "session_prefix": "med_rag:session:",
        "session_ttl": 86400,
    },
    "chunker": {
        "min_chunk_size": 150,
        "max_chunk_size": 500,
        "overlap": 50,
    },
    "retrieval": {
        "default_top_k": 5,
        "vector_top_k": 20,
        "keyword_top_k": 20,
        "rrf_k": 60,
        "rerank_top_k": 5,
        "min_relevance_score": 0.05,
        "llm_fallback_enabled": True,
    },
    "llm": {
        "provider": "deepseek",
        "fallback": "qwen",
        "temperature": 0.3,
        "max_tokens": 4096,
        "deepseek": {
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
        },
        "qwen": {
            "api_key": "",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
        },
        "zhipu": {
            "api_key": "",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4-plus",
        },
    },
    "security": {
        "max_upload_bytes": 50 * 1024 * 1024,
        "max_archive_ratio": 100,
        "max_archive_uncompressed_bytes": 500 * 1024 * 1024,
        "max_archive_members": 10000,
    },
    "cors": {
        "allowed_origins": ["http://localhost:3000"],
    },
    "database": {
        "url": "sqlite:///./data/med_rag.db",
    },
    "auth": {
        "jwt_secret": "",
        "access_ttl_seconds": 900,
        "refresh_ttl_seconds": 604800,
        "issuer": "med-rag",
        "secure_cookies": True,
    },
    "safety": {
        "enabled": True,
        "policy_version": "2026-07-21.1",
        "classifier_base_url": "http://safety-model:8000/v1",
        "classifier_model": "Qwen/Qwen3Guard-Gen-0.6B",
        "classifier_timeout_seconds": 3,
        "normal_max_chars": 4000,
        "degraded_max_chars": 500,
        "restricted_top_k": 3,
        "restricted_preview_chars": 300,
        "stream_buffer_chars": 512,
    },
    "storage": {"root": "data/documents"},
    "parser": {
        "queue_name": "med-rag-parse",
        "clamav_host": "clamav",
        "clamav_port": 3310,
        "max_pdf_pages": 1000,
        "max_image_width": 10000,
        "max_image_height": 10000,
        "max_sheet_rows": 200000,
        "max_sheet_columns": 500,
        "max_nonempty_cells": 2000000,
        "timeout_seconds": 600,
        "quarantine_retention_days": 30,
    },
    "knowledge_dir": "data",
    "whoosh_dir": "whoosh_index",
    "log_level": "INFO",
}

# 环境变量 → 配置键映射
ENV_MAPPINGS: dict[str, tuple[str, str | None]] = {
    "RAG_ENVIRONMENT": ("app", "environment"),
    "RAG_MILVUS_HOST": ("milvus", "host"),
    "RAG_MILVUS_PORT": ("milvus", "port"),
    "RAG_REDIS_HOST": ("redis", "host"),
    "RAG_REDIS_PORT": ("redis", "port"),
    "RAG_LLM_PROVIDER": ("llm", "provider"),
    "RAG_LOG_LEVEL": ("", "log_level"),
    "RAG_KNOWLEDGE_DIR": ("", "knowledge_dir"),
    "RAG_MIN_RELEVANCE_SCORE": ("retrieval", "min_relevance_score"),
    "RAG_LLM_FALLBACK_ENABLED": ("retrieval", "llm_fallback_enabled"),
    "DEEPSEEK_API_KEY": ("llm.deepseek", "api_key"),
    "QWEN_API_KEY": ("llm.qwen", "api_key"),
    "ZHIPU_API_KEY": ("llm.zhipu", "api_key"),
    "RAG_CORS_ORIGINS": ("cors", "allowed_origins"),
    "RAG_DATABASE_URL": ("database", "url"),
    "RAG_JWT_SECRET": ("auth", "jwt_secret"),
    "RAG_SECURE_COOKIES": ("auth", "secure_cookies"),
    "RAG_SAFETY_ENABLED": ("safety", "enabled"),
    "RAG_SAFETY_POLICY_VERSION": ("safety", "policy_version"),
    "RAG_SAFETY_CLASSIFIER_BASE_URL": ("safety", "classifier_base_url"),
    "RAG_SAFETY_CLASSIFIER_MODEL": ("safety", "classifier_model"),
    "RAG_SAFETY_CLASSIFIER_TIMEOUT_SECONDS": (
        "safety",
        "classifier_timeout_seconds",
    ),
    "RAG_SAFETY_NORMAL_MAX_CHARS": ("safety", "normal_max_chars"),
    "RAG_SAFETY_DEGRADED_MAX_CHARS": ("safety", "degraded_max_chars"),
    "RAG_SAFETY_RESTRICTED_TOP_K": ("safety", "restricted_top_k"),
    "RAG_SAFETY_RESTRICTED_PREVIEW_CHARS": (
        "safety",
        "restricted_preview_chars",
    ),
    "RAG_SAFETY_STREAM_BUFFER_CHARS": ("safety", "stream_buffer_chars"),
    "RAG_STORAGE_ROOT": ("storage", "root"),
    "RAG_PARSE_QUEUE_NAME": ("parser", "queue_name"),
    "RAG_CLAMAV_HOST": ("parser", "clamav_host"),
    "RAG_CLAMAV_PORT": ("parser", "clamav_port"),
    "RAG_PARSER_TIMEOUT_SECONDS": ("parser", "timeout_seconds"),
    "RAG_QUARANTINE_RETENTION_DAYS": (
        "parser",
        "quarantine_retention_days",
    ),
}

# 需要强制转 int 的字段
INT_FIELDS: list[tuple[str, str]] = [
    ("milvus", "port"),
    ("milvus", "embedding_dim"),
    ("milvus", "M"),
    ("milvus", "efConstruction"),
    ("milvus", "ef_search"),
    ("redis", "port"),
    ("redis", "db"),
    ("redis", "session_ttl"),
    ("retrieval", "default_top_k"),
    ("retrieval", "vector_top_k"),
    ("retrieval", "keyword_top_k"),
    ("retrieval", "rrf_k"),
    ("retrieval", "rerank_top_k"),
    ("chunker", "min_chunk_size"),
    ("chunker", "max_chunk_size"),
    ("chunker", "overlap"),
    ("app", "port"),
    ("llm", "max_tokens"),
    ("security", "max_upload_bytes"),
    ("security", "max_archive_ratio"),
    ("security", "max_archive_uncompressed_bytes"),
    ("security", "max_archive_members"),
    ("auth", "access_ttl_seconds"),
    ("auth", "refresh_ttl_seconds"),
    ("safety", "classifier_timeout_seconds"),
    ("safety", "normal_max_chars"),
    ("safety", "degraded_max_chars"),
    ("safety", "restricted_top_k"),
    ("safety", "restricted_preview_chars"),
    ("safety", "stream_buffer_chars"),
    ("parser", "clamav_port"),
    ("parser", "max_pdf_pages"),
    ("parser", "max_image_width"),
    ("parser", "max_image_height"),
    ("parser", "max_sheet_rows"),
    ("parser", "max_sheet_columns"),
    ("parser", "max_nonempty_cells"),
    ("parser", "timeout_seconds"),
    ("parser", "quarantine_retention_days"),
]

# 需要强制转 float 的字段
FLOAT_FIELDS: list[tuple[str, str]] = [
    ("llm", "temperature"),
    ("retrieval", "min_relevance_score"),
]

BOOL_FIELDS: list[tuple[str, str]] = [
    ("retrieval", "llm_fallback_enabled"),
    ("auth", "secure_cookies"),
    ("safety", "enabled"),
]


def load_config() -> dict[str, Any]:
    """加载配置：合并默认值 + YAML 文件 + 环境变量。"""

    # 先加载 .env，再读取 os.getenv。override=False 表示系统环境变量优先，
    # 方便生产环境通过容器或进程管理器覆盖本地开发配置。
    load_dotenv(ENV_FILE, override=False)

    config = copy.deepcopy(DEFAULTS)

    # YAML 文件覆盖
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            file_config = yaml.safe_load(f) or {}
        _deep_merge(config, file_config)

    # 环境变量覆盖
    for env_key, (section, key) in ENV_MAPPINGS.items():
        value = os.getenv(env_key)
        if value is not None:
            _set_nested(config, section, key, value)

    # YAML 与环境变量读出来的值可能是字符串。这里集中做类型收敛，
    # 后续业务代码可以直接按 int/float/bool 使用，不需要在调用点反复转换。
    # 类型转换
    for section, key in INT_FIELDS:
        val = _get_nested(config, section, key)
        if val is not None:
            _set_nested(config, section, key, int(val))

    for section, key in FLOAT_FIELDS:
        val = _get_nested(config, section, key)
        if val is not None:
            _set_nested(config, section, key, float(val))

    for section, key in BOOL_FIELDS:
        val = _get_nested(config, section, key)
        if val is not None:
            _set_nested(config, section, key, _to_bool(val))

    origins = config["cors"]["allowed_origins"]
    if isinstance(origins, str):
        config["cors"]["allowed_origins"] = [
            item.strip() for item in origins.split(",") if item.strip()
        ]

    return config


def get_config() -> dict[str, Any]:
    """获取配置（带缓存，只读取一次）。"""

    # 配置在进程内缓存，避免每次请求都读 YAML/.env。
    # 测试如需刷新配置，可删除 get_config._cache 后重新调用。
    if not hasattr(get_config, "_cache"):
        get_config._cache = load_config()  # type: ignore[attr-defined]
    return get_config._cache  # type: ignore[attr-defined]


def _deep_merge(base: dict, override: dict) -> dict:
    """深合并字典（override 覆盖 base）。"""

    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _set_nested(config: dict, section: str, key: str, value: Any) -> None:
    """按嵌套路径设置配置值。"""

    if not section:
        config[key] = value
        return

    # section 支持 "llm.deepseek" 这种点分路径，
    # 用来把 DEEPSEEK_API_KEY 映射到 config["llm"]["deepseek"]["api_key"]。
    parts = section.split(".")
    target = config
    for part in parts:
        target = target.setdefault(part, {})
    target[key] = value


def _get_nested(config: dict, section: str, key: str) -> Any | None:
    """按嵌套路径获取配置值。"""

    if not section:
        return config.get(key)

    parts = section.split(".")
    target = config
    for part in parts:
        if not isinstance(target, dict) or part not in target:
            return None
        target = target[part]
    return target.get(key)


def _to_bool(value: Any) -> bool:
    """Convert YAML/env values to bool."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
