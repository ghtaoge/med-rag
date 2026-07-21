from fastapi.testclient import TestClient

from app.core.dependencies import get_config_dep, get_document_sync
from app.main import app

client = TestClient(app)


class RecordingSync:
    def sync_file(self, filename, force=False):
        return 1


def _config(tmp_path, max_bytes=128):
    return {
        "knowledge_dir": str(tmp_path),
        "security": {
            "max_upload_bytes": max_bytes,
            "max_archive_ratio": 100,
            "max_archive_uncompressed_bytes": 1024,
            "max_archive_members": 100,
        },
    }


def test_retired_upload_endpoint_is_gone(tmp_path):
    app.dependency_overrides[get_config_dep] = lambda: _config(tmp_path)
    app.dependency_overrides[get_document_sync] = lambda: RecordingSync()
    try:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("large.txt", b"x" * 129, "text/plain")},
        )
    finally:
        app.dependency_overrides.pop(get_config_dep, None)
        app.dependency_overrides.pop(get_document_sync, None)
    assert response.status_code == 410
    assert response.json()["code"] == "LEGACY_ENDPOINT_RETIRED"
    assert not (tmp_path / "large.txt").exists()


def test_retired_upload_does_not_inspect_in_api_process(tmp_path):
    app.dependency_overrides[get_config_dep] = lambda: _config(tmp_path, 1024)
    app.dependency_overrides[get_document_sync] = lambda: RecordingSync()
    try:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
    finally:
        app.dependency_overrides.pop(get_config_dep, None)
        app.dependency_overrides.pop(get_document_sync, None)
    assert response.status_code == 410
    assert response.json()["code"] == "LEGACY_ENDPOINT_RETIRED"
    assert not (tmp_path / "fake.pdf").exists()


def test_delete_rejects_encoded_path_traversal(tmp_path):
    app.dependency_overrides[get_config_dep] = lambda: _config(tmp_path)
    try:
        response = client.delete("/api/v1/documents/..%2Foutside.txt")
    finally:
        app.dependency_overrides.pop(get_config_dep, None)
    assert response.status_code in {400, 404}
    assert not (tmp_path.parent / "outside.txt").exists()
