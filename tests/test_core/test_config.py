"""配置模块测试。"""

import os

from app.core.config import load_config, _deep_merge


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


def test_dotenv_overrides_config(monkeypatch, tmp_path):
    """本地 .env 文件可以覆盖配置文件值。"""

    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=from-dotenv\n", encoding="utf-8")

    monkeypatch.setattr("app.core.config.ENV_FILE", env_file)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    config = load_config()

    assert config["llm"]["deepseek"]["api_key"] == "from-dotenv"


def test_deep_merge_nested():
    """深合并字典正确覆盖嵌套值。"""

    base = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 10}}
    _deep_merge(base, override)
    assert base["a"]["b"] == 10
    assert base["a"]["c"] == 2
    assert base["d"] == 3


def test_llm_max_tokens_is_int():
    """OpenAI-compatible APIs require max_tokens to be an integer."""

    config = load_config()

    assert isinstance(config["llm"]["max_tokens"], int)


def test_llm_fallback_enabled_is_bool():
    """llm_fallback_enabled 应为布尔类型。"""

    config = load_config()
    assert isinstance(config["retrieval"]["llm_fallback_enabled"], bool)
    assert config["retrieval"]["llm_fallback_enabled"] is True


def test_min_relevance_score_is_float():
    """min_relevance_score 应为浮点数。"""

    config = load_config()
    assert isinstance(config["retrieval"]["min_relevance_score"], float)
    assert config["retrieval"]["min_relevance_score"] == 0.05


def test_env_var_overrides_llm_fallback_enabled():
    """环境变量可以关闭 LLM 兜底。"""

    os.environ["RAG_LLM_FALLBACK_ENABLED"] = "false"
    config = load_config()
    assert config["retrieval"]["llm_fallback_enabled"] is False
    del os.environ["RAG_LLM_FALLBACK_ENABLED"]
