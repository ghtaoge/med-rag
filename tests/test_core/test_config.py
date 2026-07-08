"""配置模块测试。"""

import os

from app.core.config import load_config, get_config, _deep_merge


def test_load_config_returns_defaults():
    """加载配置返回包含所有默认键的字典。"""

    config = load_config()
    assert "milvus" in config
    assert "redis" in config
    assert "llm" in config
    assert config["milvus"]["host"] == "localhost"
    assert config["chunker"]["min_chunk_size"] == 150


def test_env_var_overrides_config():
    """环境变量覆盖配置文件值。"""

    os.environ["RAG_MILVUS_HOST"] = "custom-host"
    config = load_config()
    assert config["milvus"]["host"] == "custom-host"
    del os.environ["RAG_MILVUS_HOST"]


def test_deep_merge_nested():
    """深合并字典正确覆盖嵌套值。"""

    base = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 10}}
    _deep_merge(base, override)
    assert base["a"]["b"] == 10
    assert base["a"]["c"] == 2
    assert base["d"] == 3
