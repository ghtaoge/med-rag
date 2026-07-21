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

    route = next(route for route in app.routes if route.path == "/api/v1/chat/complete")
    assert "POST" in route.methods


def test_chat_stream_endpoint_exists():
    """流式问答端点可访问。"""

    methods = set().union(
        *(
            route.methods
            for route in app.routes
            if route.path == "/api/v1/chat/stream"
        )
    )
    assert {"GET", "POST"}.issubset(methods)


def test_sessions_list_endpoint():
    """会话列表端点可访问（Redis 不可用时返回空列表）。"""

    response = client.get("/api/v1/chat/sessions")
    # Redis 不可用时应返回空列表而非 500
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data


def test_sessions_persist_without_redis(tmp_path):
    """History should still work when Redis is unavailable."""

    from datetime import datetime

    from app.api.chat import ChatOrchestrator
    from app.core.models import (
        ConfidenceLevel,
        CorrectnessResult,
        IntentCategory,
        IntentResult,
        QaSession,
    )
    from app.security.models import Role
    from app.security.principal import Principal, PrincipalMembership

    principal = Principal(
        user_id="test-user",
        username="test-user",
        memberships=(PrincipalMembership("test-department", Role.READER),),
        session_id="test-session",
    )

    store_path = tmp_path / ".med-rag-sessions.json"
    orchestrator = ChatOrchestrator(
        None,
        None,
        None,
        None,
        redis_client=None,
        session_store_path=store_path,
    )
    session = QaSession(
        session_id="local-session-1",
        question="历史记录测试",
        answer="可以保存",
        intent=IntentResult(
            category=IntentCategory.QUERY,
            confidence=0.9,
            method="rule",
        ),
        correctness=CorrectnessResult(
            confidence=ConfidenceLevel.HIGH,
            score=0.8,
            source_count=0,
        ),
        source_type="knowledge_base",
        user_id=principal.user_id,
        department_ids=principal.department_ids,
        created_at=datetime(2026, 7, 9, 10, 0, 0),
    )

    orchestrator._save_session(session)

    reloaded = ChatOrchestrator(
        None,
        None,
        None,
        None,
        redis_client=None,
        session_store_path=store_path,
    )
    sessions = reloaded.list_sessions(principal)

    assert sessions[0]["session_id"] == "local-session-1"
    assert reloaded.get_session("local-session-1", principal)["answer"] == "可以保存"
    assert reloaded.delete_session("local-session-1", principal) is True
    assert reloaded.list_sessions(principal) == []


def test_documents_list_endpoint():
    """文档列表端点可访问。"""

    response = client.get("/api/v1/documents/list")
    assert response.status_code == 200
    data = response.json()
    assert "total_files" in data
    assert "documents" in data


def test_evaluation_checklist_endpoint():
    """上线检查清单端点可访问。"""

    route = next(
        route for route in app.routes if route.path == "/api/v1/evaluation/checklist"
    )
    assert "GET" in route.methods


def test_evaluation_stats_endpoint():
    """评估统计端点可访问。"""

    route = next(route for route in app.routes if route.path == "/api/v1/evaluation/stats")
    assert "GET" in route.methods


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


def test_upload_document_syncs_immediately(tmp_path):
    """Uploading should save, validate, and immediately sync the uploaded file."""

    from app.api.documents import get_config_dep, get_document_sync

    class RecordingSync:
        def __init__(self):
            self.synced_filename = ""

        def sync_file(self, filename, force=False):
            self.synced_filename = filename
            return 2

    config = {
        "knowledge_dir": str(tmp_path),
    }

    app.dependency_overrides[get_config_dep] = lambda: config
    sync = RecordingSync()
    app.dependency_overrides[get_document_sync] = lambda: sync

    try:
        content = b"medical document content " * 8
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("medical.txt", content, "text/plain")},
        )
    finally:
        app.dependency_overrides.pop(get_config_dep, None)
        app.dependency_overrides.pop(get_document_sync, None)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["filename"] == "medical.txt"
    assert data["chunk_count"] == 2
    assert data["in_index"] is True
    assert sync.synced_filename == "medical.txt"
    assert (tmp_path / "medical.txt").exists()


def test_delete_uploaded_unsynced_document_does_not_initialize_sync(tmp_path):
    """Deleting an uploaded-only file should not require the sync dependency."""

    from app.api.documents import get_config_dep, get_document_sync

    test_file = tmp_path / "uploaded-only.txt"
    test_file.write_text("medical document content" * 8, encoding="utf-8")

    def fail_sync_dependency():
        raise AssertionError("sync dependency should not be initialized")

    app.dependency_overrides[get_config_dep] = lambda: {"knowledge_dir": str(tmp_path)}
    app.dependency_overrides[get_document_sync] = fail_sync_dependency

    try:
        response = client.delete("/api/v1/documents/uploaded-only.txt")
    finally:
        app.dependency_overrides.pop(get_config_dep, None)
        app.dependency_overrides.pop(get_document_sync, None)

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert not test_file.exists()


def test_documents_list_does_not_initialize_sync(tmp_path):
    """Listing uploaded files should not initialize vector or keyword indexes."""

    from app.api.documents import get_config_dep, get_document_sync

    (tmp_path / "medical.txt").write_text("medical document content" * 8, encoding="utf-8")
    (tmp_path / ".med-rag-index-state.json").write_text(
        '{"medical.txt": {"chunk_count": 3}}',
        encoding="utf-8",
    )

    def fail_sync_dependency():
        raise AssertionError("sync dependency should not be initialized")

    app.dependency_overrides[get_config_dep] = lambda: {"knowledge_dir": str(tmp_path)}
    app.dependency_overrides[get_document_sync] = fail_sync_dependency

    try:
        response = client.get("/api/v1/documents/list")
    finally:
        app.dependency_overrides.pop(get_config_dep, None)
        app.dependency_overrides.pop(get_document_sync, None)

    assert response.status_code == 200
    data = response.json()
    assert data["total_files"] == 1
    assert data["total_chunks"] == 3
    assert data["documents"][0]["filename"] == "medical.txt"
    assert data["documents"][0]["chunk_count"] == 3
    assert data["documents"][0]["in_index"] is True
