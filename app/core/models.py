"""Med-Rag 共享数据模型。

所有模块共用的核心数据结构。后续模块只依赖这些模型和 ABC 接口，
不依赖具体实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IntentCategory(str, Enum):
    """意图类别枚举。"""

    QUERY = "query"
    DEFINITION = "definition"
    COMPARISON = "comparison"
    PROCESS = "process"
    NEGATION = "negation"


class ConfidenceLevel(str, Enum):
    """置信度级别。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChunkType(str, Enum):
    """Chunk 类型枚举。"""

    PARAGRAPH = "paragraph"
    TABLE = "table"
    PAGE = "page"
    IMAGE = "image"
    LIST = "list"
    CODE = "code"


@dataclass
class ChunkMetadata:
    """Chunk 附加元数据。"""

    source: str = ""
    chunk_type: ChunkType = ChunkType.PARAGRAPH
    heading: str = ""
    page_num: int = 0
    section: str = ""
    doc_type: str = ""
    document_id: str = ""
    document_version_id: str = ""
    owner_department_id: str = ""
    visible_department_ids: tuple[str, ...] = field(default_factory=tuple)
    review_status: str = "draft"
    expires_at_epoch: int = 0


@dataclass
class DocumentChunk:
    """知识库中的一个小片段。"""

    id: str
    source: str
    content: str
    embedding: list[float] = field(default_factory=list)
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)


@dataclass
class SearchResult:
    """一次检索命中的结果。"""

    chunk: DocumentChunk
    score: float


@dataclass
class IntentResult:
    """意图识别结果。"""

    category: IntentCategory
    confidence: float
    method: str  # "rule" | "llm"


@dataclass
class CorrectnessResult:
    """正确性校验结果。"""

    confidence: ConfidenceLevel
    score: float
    source_count: int
    warnings: list[str] = field(default_factory=list)
    hallucination_flags: list[str] = field(default_factory=list)


@dataclass
class QaSession:
    """问答会话。"""

    session_id: str
    question: str
    answer: str = ""
    sources: list[SearchResult] = field(default_factory=list)
    intent: IntentResult | None = None
    correctness: CorrectnessResult | None = None
    source_type: str = "knowledge_base"  # "knowledge_base" | "llm_fallback" | "no_result"
    user_id: str = ""
    department_ids: tuple[str, ...] = field(default_factory=tuple)
    safety: dict[str, str] = field(default_factory=dict)
    request_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
