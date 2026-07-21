"""BM25 关键词检索测试。"""

import tempfile

from app.core.models import DocumentChunk, ChunkMetadata
from app.retrieval.keyword_store import KeywordStore
from app.retrieval.access import RetrievalAccess

DEPARTMENT_ID = "4b413c1d-625e-4ef5-956d-95900f7e4674"
ACCESS = RetrievalAccess("user-1", (DEPARTMENT_ID,))


def test_keyword_store_add_and_search():
    """KeywordStore 添加 chunks 并搜索。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        store = KeywordStore(index_dir=tmpdir)

        chunks = [
            DocumentChunk(
                id="test:1",
                source="test.md",
                content="阿司匹林的适应症包括降低心肌梗死风险",
                metadata=ChunkMetadata(
                    source="test.md",
                    visible_department_ids=(DEPARTMENT_ID,),
                    review_status="approved",
                ),
            ),
            DocumentChunk(
                id="test:2",
                source="test.md",
                content="布洛芬用于缓解轻至中度疼痛",
                metadata=ChunkMetadata(
                    source="test.md",
                    visible_department_ids=(DEPARTMENT_ID,),
                    review_status="approved",
                ),
            ),
        ]

        store.add_chunks(chunks)

        results = store.search("阿司匹林适应症", top_k=5, access=ACCESS)
        assert len(results) >= 1
        # 阿司匹林相关 chunk 应排名靠前
        assert results[0].chunk.id == "test:1"


def test_keyword_store_delete_by_source():
    """KeywordStore 按 source 删除 chunks。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        store = KeywordStore(index_dir=tmpdir)

        chunks = [
            DocumentChunk(id="a:1", source="a.md", content="内容a"),
            DocumentChunk(id="b:1", source="b.md", content="内容b"),
        ]

        store.add_chunks(chunks)
        assert store.get_chunk_count() == 2

        store.delete_chunks("a.md")
        assert store.get_chunk_count() == 1


def test_keyword_store_get_chunk_count():
    """KeywordStore 获取 chunk 数量。"""

    with tempfile.TemporaryDirectory() as tmpdir:
        store = KeywordStore(index_dir=tmpdir)

        chunks = [
            DocumentChunk(id=f"test:{i}", source="test.md", content=f"内容{i}")
            for i in range(5)
        ]

        store.add_chunks(chunks)
        assert store.get_chunk_count() == 5
