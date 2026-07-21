from fastapi.testclient import TestClient

from app.core.dependencies import get_chat_orchestrator
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_sse_error_never_returns_exception_text():
    class ExplodingOrchestrator:
        async def chat_stream(self, question, principal):
            raise RuntimeError("postgresql://admin:secret@internal-db/private")
            yield

    app.dependency_overrides[get_chat_orchestrator] = lambda: ExplodingOrchestrator()
    try:
        body = client.get("/api/v1/chat/stream?question=test").text
        assert "secret" not in body
        assert "internal-db" not in body
        assert "INTERNAL_ERROR" in body
    finally:
        app.dependency_overrides.pop(get_chat_orchestrator, None)


def test_unknown_cors_origin_is_not_allowed():
    response = client.options(
        "/health",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") is None
