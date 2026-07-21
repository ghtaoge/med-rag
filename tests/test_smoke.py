"""冒烟测试 — 验证所有端点可访问且返回合理响应。"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_smoke_health():
    """冒烟：健康检查端点正常。"""

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_smoke_engines():
    """冒烟：引擎信息端点正常。"""

    response = client.get("/api/v1/engines")
    assert response.status_code == 200
    data = response.json()
    assert "llm_provider" in data
    assert "embedding_model" in data


def test_smoke_sessions_list():
    """冒烟：会话列表端点正常。"""

    response = client.get("/api/v1/chat/sessions")
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data


def test_smoke_documents_list():
    """冒烟：文档列表端点正常。"""

    response = client.get("/api/v1/documents/list")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
    assert "total_files" in data


def test_smoke_evaluation_checklist():
    """冒烟：上线检查清单端点正常。"""

    routes = [route.path for route in app.routes if hasattr(route, "path")]
    assert "/api/v1/evaluation/checklist" in routes


def test_smoke_evaluation_stats():
    """冒烟：评估统计端点正常。"""

    routes = [route.path for route in app.routes if hasattr(route, "path")]
    assert "/api/v1/evaluation/stats" in routes


def test_smoke_cors():
    """冒烟：CORS 配置正确。"""

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" in response.headers


def test_smoke_404():
    """冒烟：未知路由返回 404。"""

    response = client.get("/nonexistent-path")
    assert response.status_code == 404


def test_smoke_all_routes_registered():
    """冒烟：所有预期路由已注册。"""

    routes = [route.path for route in app.routes if hasattr(route, "path")]

    expected_routes = [
        "/health",
        "/api/v1/engines",
        "/api/v1/chat/stream",
        "/api/v1/chat/complete",
        "/api/v1/chat/sessions",
        "/api/v1/documents/list",
        "/api/v1/documents/upload",
        "/api/v1/documents/sync",
        "/api/v1/evaluation/checklist",
        "/api/v1/evaluation/stats",
    ]

    for expected in expected_routes:
        assert expected in routes, f"路由未注册: {expected}"
