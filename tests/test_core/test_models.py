"""共享数据模型测试。"""

from app.core.models import (
    DocumentChunk,
    SearchResult,
    IntentCategory,
    ConfidenceLevel,
    ChunkType,
    IntentResult,
    CorrectnessResult,
    ChunkMetadata,
)


def test_document_chunk_creation():
    """DocumentChunk 可以正常创建。"""

    chunk = DocumentChunk(id="test:1", source="test.txt", content="hello")
    assert chunk.id == "test:1"
    assert chunk.source == "test.txt"
    assert chunk.content == "hello"
    assert chunk.embedding == []
    assert isinstance(chunk.metadata, ChunkMetadata)


def test_document_chunk_with_metadata():
    """DocumentChunk 可以指定 metadata。"""

    meta = ChunkMetadata(source="test.md", chunk_type=ChunkType.TABLE, heading="表格标题")
    chunk = DocumentChunk(id="t:1", source="test.md", content="表格内容", metadata=meta)
    assert chunk.metadata.chunk_type == ChunkType.TABLE
    assert chunk.metadata.heading == "表格标题"


def test_search_result_creation():
    """SearchResult 可以正常创建。"""

    chunk = DocumentChunk(id="t:1", source="t.txt", content="c")
    result = SearchResult(chunk=chunk, score=0.85)
    assert result.score == 0.85
    assert result.chunk.id == "t:1"


def test_intent_category_enum():
    """IntentCategory 包含 5 种意图。"""

    assert IntentCategory.QUERY == "query"
    assert IntentCategory.DEFINITION == "definition"
    assert IntentCategory.COMPARISON == "comparison"
    assert IntentCategory.PROCESS == "process"
    assert IntentCategory.NEGATION == "negation"


def test_confidence_level_enum():
    """ConfidenceLevel 包含 3 个级别。"""

    assert ConfidenceLevel.HIGH == "high"
    assert ConfidenceLevel.MEDIUM == "medium"
    assert ConfidenceLevel.LOW == "low"


def test_correctness_result_fields():
    """CorrectnessResult 包含所有字段。"""

    cr = CorrectnessResult(
        confidence=ConfidenceLevel.HIGH,
        score=0.85,
        source_count=3,
        warnings=["仅单一来源"],
    )
    assert cr.confidence == ConfidenceLevel.HIGH
    assert cr.score == 0.85
    assert cr.source_count == 3
    assert len(cr.warnings) == 1


def test_intent_result_creation():
    """IntentResult 可以正常创建。"""

    ir = IntentResult(category=IntentCategory.QUERY, confidence=0.92, method="rule")
    assert ir.category == IntentCategory.QUERY
    assert ir.method == "rule"
