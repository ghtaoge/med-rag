"""Whoosh BM25 关键词检索。jieba 分词 + 医疗词典。"""

from __future__ import annotations

import jieba
from pathlib import Path
from whoosh.index import create_in, open_dir, exists_in
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import QueryParser, OrGroup
from whoosh.analysis import Analyzer

from app.core.config import get_config
from app.core.exceptions import RetrievalError
from app.core.models import DocumentChunk, SearchResult

config = get_config()

# 医疗术语自定义词典
MEDICAL_DICT_WORDS = [
    "阿司匹林", "布洛芬", "心肌梗死", "脑卒中", "适应症",
    "不良反应", "药物相互作用", "临床路径", "处方", "剂量",
    "禁忌症", "注意事项", "用法用量", "药品说明书",
    "解热镇痛", "抗凝药", "消化道出血", "过敏性哮喘",
    "冠状动脉搭桥手术", "短暂性脑缺血发作",
]

# 加载医疗词典到 jieba
for word in MEDICAL_DICT_WORDS:
    jieba.add_word(word)


class ChineseAnalyzer(Analyzer):
    """中文分词分析器。使用 jieba 分词，生成 Whoosh Token 对象。"""

    def __call__(self, text, **kwargs):
        from whoosh.analysis import Token
        pos = 0
        token = Token()
        words = jieba.cut(text)
        for word in words:
            word = word.strip()
            if word:
                token.text = word
                token.pos = pos
                token.startchar = 0
                token.endchar = len(word)
                yield token
                pos += 1


class KeywordStore:
    """Whoosh BM25 关键词检索引擎。

    支持中文分词（jieba + 医疗词典）和 BM25 评分。
    """

    def __init__(self, index_dir: str = None):
        self.index_dir = Path(index_dir or config["whoosh_dir"])
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.schema = Schema(
            chunk_id=ID(stored=True, unique=True),
            source=ID(stored=True),
            content=TEXT(analyzer=ChineseAnalyzer(), stored=True),
        )

        self._ix = None

    def _get_index(self):
        """获取或创建 Whoosh 索引。"""

        if self._ix is not None:
            return self._ix

        if exists_in(str(self.index_dir)):
            self._ix = open_dir(str(self.index_dir))
        else:
            self._ix = create_in(str(self.index_dir), self.schema)
        return self._ix

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        """批量添加 chunks 到 Whoosh 索引。"""

        ix = self._get_index()
        writer = ix.writer()
        for chunk in chunks:
            writer.add_document(
                chunk_id=chunk.id,
                source=chunk.source,
                content=chunk.content,
            )
        writer.commit()

    def delete_chunks(self, source: str) -> None:
        """按 source 删除所有 chunks。"""

        ix = self._get_index()
        writer = ix.writer()
        writer.delete_by_term("source", source)
        writer.commit()

    def search(self, query: str, top_k: int = 20) -> list[SearchResult]:
        """BM25 关键词检索。"""

        ix = self._get_index()
        searcher = ix.searcher()

        # 构建查询：对每个分词构建 OR 组合查询
        parser = QueryParser("content", ix.schema, group=OrGroup)
        q = parser.parse(query)

        results = searcher.search(q, limit=top_k)

        search_results = []
        for hit in results:
            chunk = DocumentChunk(
                id=hit["chunk_id"],
                source=hit["source"],
                content=hit["content"],
            )
            # Whoosh 的 score 是 BM25 分数，需要归一化
            score = hit.score / (1.0 + hit.score)  # 归一化到 0-1
            search_results.append(SearchResult(chunk=chunk, score=score))

        searcher.close()
        return search_results

    def clear_index(self) -> None:
        """清空索引并重建。"""

        self._ix = None
        if self.index_dir.exists():
            for f in self.index_dir.iterdir():
                f.unlink()
        self._get_index()

    def get_chunk_count(self) -> int:
        """获取索引中的文档数量。"""

        ix = self._get_index()
        return ix.doc_count()
