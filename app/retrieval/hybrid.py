"""RRF (Reciprocal Rank Fusion) 检索结果融合。"""

from __future__ import annotations

from app.core.models import DocumentChunk, SearchResult


def rrf_fusion(
    vector_results: list[SearchResult],
    keyword_results: list[SearchResult],
    k: int = 60,
) -> list[SearchResult]:
    """RRF 融合向量检索和关键词检索结果。

    score = Σ 1/(k + rank_i)
    同一个 chunk 在两路结果中都有时，分数相加。
    """

    scores: dict[str, float] = {}
    chunk_map: dict[str, DocumentChunk] = {}

    for rank, result in enumerate(vector_results):
        chunk_id = result.chunk.id
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
        chunk_map[chunk_id] = result.chunk

    for rank, result in enumerate(keyword_results):
        chunk_id = result.chunk.id
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
        chunk_map[chunk_id] = result.chunk

    fused = [
        SearchResult(chunk=chunk_map[cid], score=score)
        for cid, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ]
    return fused
