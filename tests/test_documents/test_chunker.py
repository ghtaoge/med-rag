"""智能切块测试。"""

from app.documents.chunker import chunk_text, chunk_markdown
from app.core.models import ChunkType


def test_chunk_text_basic():
    """chunk_text 按段落边界切。"""

    text = "第一段内容\n\n第二段内容\n\n第三段内容"
    chunks = chunk_text(text, source="test.txt", min_size=10, max_size=500)
    assert len(chunks) >= 1
    assert chunks[0].source == "test.txt"
    assert "第一段" in chunks[0].content


def test_chunk_text_empty():
    """chunk_text 处理空文本。"""

    chunks = chunk_text("", source="empty.txt")
    assert len(chunks) == 0


def test_chunk_text_short_text():
    """chunk_text 处理非常短的文本。"""

    chunks = chunk_text("短文本", source="short.txt", min_size=10, max_size=500)
    # 短文本低于 min_size，应该只有一个 chunk
    assert len(chunks) == 1
    assert chunks[0].content == "短文本"


def test_chunk_markdown_preserves_headings():
    """chunk_markdown 按标题层级切块。"""

    md = "# 标题1\n内容1\n\n## 标题2\n内容2\n\n## 标题3\n内容3"
    chunks = chunk_markdown(md, source="test.md", min_size=10, max_size=500)
    assert len(chunks) >= 1
    headings = [c.metadata.heading for c in chunks]
    assert any("标题1" in h for h in headings)


def test_chunk_markdown_table_protection():
    """chunk_markdown 不切断表格。"""

    md = "# 表格测试\n\n| 列1 | 列2 |\n| --- | --- |\n| a | b |\n| c | d |"
    chunks = chunk_markdown(md, source="test.md", min_size=10, max_size=500)
    table_chunks = [c for c in chunks if c.metadata.chunk_type == ChunkType.TABLE]
    assert len(table_chunks) >= 1
    assert "| 列1 | 列2 |" in table_chunks[0].content


def test_chunk_markdown_real_file():
    """chunk_markdown 处理 sample_medical.md。"""

    from pathlib import Path
    from app.core.config import get_config

    config = get_config()
    data_dir = Path(__file__).resolve().parent.parent.parent / config["knowledge_dir"]
    md_file = data_dir / "sample_medical.md"
    if md_file.exists():
        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_markdown(text, source="sample_medical.md", min_size=10, max_size=500)
        assert len(chunks) >= 3  # 多个标题节
        # 验证表格 chunk 存在
        table_chunks = [c for c in chunks if c.metadata.chunk_type == ChunkType.TABLE]
        assert len(table_chunks) >= 1
        # 验证所有 chunk 都有 heading
        for c in chunks:
            assert c.metadata.heading  # 每个 chunk 都有标题归属
