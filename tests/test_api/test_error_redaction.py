from fastapi.testclient import TestClient

from app.api import chat_routes
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_sse_error_never_returns_exception_text(monkeypatch):
    def explode():
        raise RuntimeError("postgresql://admin:secret@internal-db/private")

    monkeypatch.setattr(chat_routes, "get_chat_orchestrator", explode)
    body = client.get("/api/v1/chat/stream?question=test").text
    assert "secret" not in body
    assert "internal-db" not in body
    assert "INTERNAL_ERROR" in body


def test_unknown_cors_origin_is_not_allowed():
    response = client.options(
        "/health",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") is None
