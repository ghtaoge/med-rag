from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.dependencies import get_config_dep
from app.security.bootstrap_auth import verify_bootstrap_admin


def _client(key: str) -> TestClient:
    mini_app = FastAPI()
    mini_app.dependency_overrides[get_config_dep] = lambda: {
        "security": {"bootstrap_admin_key": key}
    }

    @mini_app.get("/protected", dependencies=[Depends(verify_bootstrap_admin)])
    def protected():
        return {"ok": True}

    return TestClient(mini_app)


def test_missing_server_key_fails_closed():
    assert _client("").get("/protected").status_code == 503


def test_missing_request_key_is_unauthorized():
    assert _client("a" * 32).get("/protected").status_code == 401


def test_valid_request_key_is_accepted():
    response = _client("a" * 32).get(
        "/protected", headers={"X-Med-Rag-Admin-Key": "a" * 32}
    )
    assert response.status_code == 200
