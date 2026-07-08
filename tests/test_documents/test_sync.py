"""增量同步测试。"""

import tempfile
from pathlib import Path

from app.documents.sync import DocumentSync, FileChange
from app.core.models import DocumentChunk, ChunkMetadata


def test_file_hash_calculation():
    """SHA-256 hash 计算正确。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("hello", encoding="utf-8")

        sync = DocumentSync(knowledge_dir=Path(tmpdir))
        hash1 = sync._file_hash(test_file)

        # 修改文件内容
        test_file.write_text("world", encoding="utf-8")
        hash2 = sync._file_hash(test_file)

        # hash 不同
        assert hash1 != hash2


def test_detect_changes_new_file():
    """检测新增文件变更。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("content", encoding="utf-8")

        sync = DocumentSync(knowledge_dir=Path(tmpdir))
        changes = sync.detect_changes()

        # 新文件 → add 变更
        assert len(changes) == 1
        assert changes[0].change_type == "add"
        assert changes[0].filename == "test.txt"


def test_sync_file_creates_chunks():
    """sync_file 创建 chunks 并写入活跃索引。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("第一段内容\n\n第二段内容\n\n第三段内容", encoding="utf-8")

        sync = DocumentSync(knowledge_dir=Path(tmpdir))
        count = sync.sync_file("test.txt")

        assert count >= 1
        assert "test.txt" in sync.active_chunks
        assert len(sync.active_chunks["test.txt"]) == count


def test_sync_file_markdown():
    """sync_file 对 Markdown 文件使用 chunk_markdown。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        md_file = Path(tmpdir) / "药品说明书.md"
        md_file.write_text("# 标题1\n内容1\n\n## 标题2\n内容2", encoding="utf-8")

        sync = DocumentSync(knowledge_dir=Path(tmpdir))
        count = sync.sync_file("药品说明书.md")

        assert count >= 1
        # Markdown chunks 应有 heading metadata
        chunks = sync.active_chunks["药品说明书.md"]
        assert any(c.metadata.heading for c in chunks)


def test_swap_moves_staging_to_active():
    """swap 原子性移动 staging → active。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("内容", encoding="utf-8")

        sync = DocumentSync(knowledge_dir=Path(tmpdir))
        # 手动添加到 staging
        sync.staging_chunks["manual.txt"] = [
            DocumentChunk(id="manual:1", source="manual.txt", content="手动内容")
        ]

        sync.swap()
        assert "manual.txt" in sync.active_chunks
        assert len(sync.staging_chunks) == 0


def test_get_total_chunk_count():
    """获取活跃索引总 chunk 数。"""

    sync = DocumentSync(knowledge_dir=Path("/tmp/nonexistent"))
    sync.active_chunks = {
        "a.md": [DocumentChunk(id="a:1", source="a.md", content="1")],
        "b.md": [
            DocumentChunk(id="b:1", source="b.md", content="1"),
            DocumentChunk(id="b:2", source="b.md", content="2"),
        ],
    }
    assert sync.get_total_chunk_count() == 3
