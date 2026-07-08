"""API 路由测试。"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    """健康检查返回 ok。"""

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_engines_info():
    """引擎信息返回配置。"""

    response = client.get("/api/v1/engines")
    assert response.status_code == 200
    data = response.json()
    assert "llm_provider" in data
    assert "embedding_model" in data
    assert "vector_store" in data


def test_chat_complete_endpoint_exists():
    """非流式问答端点可访问。"""

    # 无 LLM 配置时应返回异常而非 404
    response = client.post("/api/v1/chat/complete?question=测试问题")
    # 期望 500 或 503（LLM 配置问题），但不应 404
    assert response.status_code != 404


def test_chat_stream_endpoint_exists():
    """流式问答端点可访问。"""

    response = client.post("/api/v1/chat/stream?question=测试问题")
    # SSE 流式端点存在
    assert response.status_code != 404


def test_sessions_list_endpoint():
    """会话列表端点可访问（Redis 不可用时返回空列表）。"""

    response = client.get("/api/v1/chat/sessions")
    # Redis 不可用时应返回空列表而非 500
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data


def test_documents_list_endpoint():
    """文档列表端点可访问。"""

    response = client.get("/api/v1/documents/list")
    assert response.status_code == 200
    data = response.json()
    assert "total_files" in data
    assert "documents" in data


def test_evaluation_checklist_endpoint():
    """上线检查清单端点可访问。"""

    response = client.get("/api/v1/evaluation/checklist")
    # 可能因 Milvus/Redis 未连接而返回部分失败，但端点应存在
    assert response.status_code != 404
    data = response.json()
    assert "checks" in data
    assert "overall_status" in data


def test_evaluation_stats_endpoint():
    """评估统计端点可访问。"""

    response = client.get("/api/v1/evaluation/stats")
    assert response.status_code != 404
    data = response.json()
    assert "llm_provider" in data


def test_cors_headers_present():
    """CORS 头存在。"""

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


def test_404_unknown_route():
    """未知路由返回 404。"""

    response = client.get("/unknown-route")
    assert response.status_code == 404
