"""bge-reranker-v2-m3 重排序。"""

from __future__ import annotations

from app.core.models import SearchResult


class Reranker:
    """bge-reranker-v2-m3 重排序引擎。

    使用 sentence-transformers 的 CrossEncoder 加载模型。
    对 (query, content) 评分后重新排序。
    """

    def __init__(self):
        self._model = None

    def _get_model(self):
        """延迟加载重排序模型。"""

        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder("BAAI/bge-reranker-v2-m3")
        return self._model

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 5,
    ) -> list[SearchResult]:
        """对检索结果重排序。

        对每个 (query, content) 计算相关性分数，
        重新排序后返回 top_k 结果。
        """

        if not results:
            return []

        model = self._get_model()

        pairs = [(query, r.chunk.content) for r in results]
        scores = model.predict(pairs)

        # 按新分数重新排序
        reranked = [
            SearchResult(chunk=results[i].chunk, score=float(scores[i]))
            for i in range(len(results))
        ]
        reranked.sort(key=lambda x: x.score, reverse=True)

        return reranked[:top_k]
