from datetime import datetime, timezone
from dataclasses import replace

import pytest

from app.core.exceptions import AuthorizationError
from app.core.models import ChunkMetadata, DocumentChunk, SearchResult
from app.retrieval.access import RetrievalAccess
from app.retrieval.hybrid_engine import HybridRetrievalEngine

DEPARTMENT_A = "4b413c1d-625e-4ef5-956d-95900f7e4674"
DEPARTMENT_B = "aefdd62d-cdf7-43bc-965b-1e4c6280aa63"


def _result(departments, status="approved", expires_at_epoch=0):
    return SearchResult(
        chunk=DocumentChunk(
            id="chunk-1",
            source="version.txt",
            content="阿司匹林剂量",
            metadata=ChunkMetadata(
                source="version.txt",
                visible_department_ids=departments,
                review_status=status,
                expires_at_epoch=expires_at_epoch,
            ),
        ),
        score=0.9,
    )


class VectorStore:
    def __init__(self, results):
        self.results = results
        self.filter_expr = None

    def search(self, query, top_k, filter_expr):
        self.filter_expr = filter_expr
        return self.results


class KeywordStore:
    def __init__(self, results):
        self.results = results
        self.access = None

    def search(self, query, top_k, access):
        self.access = access
        return self.results


def test_access_is_applied_to_both_retrieval_backends():
    access = RetrievalAccess("user-a", (DEPARTMENT_A,))
    result = _result((DEPARTMENT_A,))
    vector = VectorStore([result])
    keyword = KeywordStore([result])
    engine = HybridRetrievalEngine(vector, keyword)

    results = engine.search("阿司匹林", access=access)

    assert results
    assert DEPARTMENT_A in vector.filter_expr
    assert 'review_status == "approved"' in vector.filter_expr
    assert keyword.access == access


@pytest.mark.parametrize(
    "result",
    [
        _result((DEPARTMENT_B,)),
        _result((DEPARTMENT_A,), status="draft"),
        _result(
            (DEPARTMENT_A,),
            expires_at_epoch=int(datetime.now(timezone.utc).timestamp()) - 1,
        ),
    ],
)
def test_post_fusion_guard_rejects_unauthorized_result(result):
    engine = HybridRetrievalEngine(VectorStore([result]), KeywordStore([]))
    with pytest.raises(AuthorizationError):
        engine.search(
            "阿司匹林",
            access=RetrievalAccess("user-a", (DEPARTMENT_A,)),
        )


def test_retrieval_without_access_fails_closed():
    engine = HybridRetrievalEngine(VectorStore([]), KeywordStore([]))
    with pytest.raises(AuthorizationError):
        engine.search("阿司匹林")


def test_restricted_top_k_cannot_be_expanded_by_reranker():
    results = [
        replace(
            _result((DEPARTMENT_A,)),
            chunk=replace(_result((DEPARTMENT_A,)).chunk, id=f"chunk-{index}"),
        )
        for index in range(5)
    ]

    class RecordingReranker:
        def __init__(self):
            self.top_k = None

        def rerank(self, query, results, top_k):
            self.top_k = top_k
            return results[:top_k]

    reranker = RecordingReranker()
    engine = HybridRetrievalEngine(VectorStore(results), KeywordStore([]), reranker)
    output = engine.search(
        "阿司匹林",
        top_k=3,
        access=RetrievalAccess("user-a", (DEPARTMENT_A,)),
    )
    assert reranker.top_k == 3
    assert len(output) == 3
