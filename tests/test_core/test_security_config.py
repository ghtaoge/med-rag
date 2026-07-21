from app.core import config as config_module


def _clear_cache():
    if hasattr(config_module.get_config, "_cache"):
        del config_module.get_config._cache


def test_security_defaults_fail_closed(monkeypatch):
    _clear_cache()
    cfg = config_module.get_config()
    assert cfg["security"]["max_upload_bytes"] == 50 * 1024 * 1024
    assert cfg["security"]["max_archive_ratio"] == 100
    _clear_cache()


def test_security_environment_overrides(monkeypatch):
    monkeypatch.setenv(
        "RAG_CORS_ORIGINS",
        "http://localhost:3000,https://med.example.test",
    )
    _clear_cache()
    cfg = config_module.get_config()
    assert cfg["cors"]["allowed_origins"] == [
        "http://localhost:3000",
        "https://med.example.test",
    ]
    _clear_cache()
