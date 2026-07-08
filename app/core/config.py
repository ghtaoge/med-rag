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

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = BASE_DIR / "config.yaml"

DEFAULTS: dict[str, Any] = {
    "app": {
        "name": "Med-Rag 知识助手",
        "version": "1.0.0",
        "host": "0.0.0.0",
        "port": 8000,
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
    "knowledge_dir": "data",
    "whoosh_dir": "whoosh_index",
    "log_level": "INFO",
}

# 环境变量 → 配置键映射
ENV_MAPPINGS: dict[str, tuple[str, str | None]] = {
    "RAG_MILVUS_HOST": ("milvus", "host"),
    "RAG_MILVUS_PORT": ("milvus", "port"),
    "RAG_REDIS_HOST": ("redis", "host"),
    "RAG_REDIS_PORT": ("redis", "port"),
    "RAG_LLM_PROVIDER": ("llm", "provider"),
    "RAG_LOG_LEVEL": ("", "log_level"),
    "RAG_KNOWLEDGE_DIR": ("", "knowledge_dir"),
    "DEEPSEEK_API_KEY": ("llm.deepseek", "api_key"),
    "QWEN_API_KEY": ("llm.qwen", "api_key"),
    "ZHIPU_API_KEY": ("llm.zhipu", "api_key"),
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
]

# 需要强制转 float 的字段
FLOAT_FIELDS: list[tuple[str, str]] = [
    ("llm", "temperature"),
    ("llm", "max_tokens"),
]


def load_config() -> dict[str, Any]:
    """加载配置：合并默认值 + YAML 文件 + 环境变量。"""

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

    # 类型转换
    for section, key in INT_FIELDS:
        val = _get_nested(config, section, key)
        if val is not None:
            _set_nested(config, section, key, int(val))

    for section, key in FLOAT_FIELDS:
        val = _get_nested(config, section, key)
        if val is not None:
            _set_nested(config, section, key, float(val))

    return config


def get_config() -> dict[str, Any]:
    """获取配置（带缓存，只读取一次）。"""

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
