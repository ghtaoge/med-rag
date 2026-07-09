"""Milvus 向量存储。embedding + query + upsert + delete。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core.config import get_config
from app.core.exceptions import RetrievalError
from app.core.models import DocumentChunk, SearchResult, ChunkMetadata

config = get_config()
MILVUS_CFG = config["milvus"]


class MilvusStore:
    """Milvus 向量存储引擎。

    使用 pymilvus 连接 Milvus，支持：
    - add_chunks: 批量入库（自动计算 embedding）
    - search: 向量相似度检索
    - delete_chunks: 按 source 删除
    - upsert_chunks: 增量更新
    """

    def __init__(self, host: str = None, port: int = None):
        self.host = host or MILVUS_CFG["host"]
        self.port = port or MILVUS_CFG["port"]
        self.collection_name = MILVUS_CFG["collection_name"]
        self.embedding_dim = MILVUS_CFG["embedding_dim"]

        # 嵌入模型（bge-large-zh-v1.5）
        self._embedding_model = None
        self._client = None
        self._collection = None

    def _get_embedding_model(self):
        """延迟加载嵌入模型。"""

        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer("BAAI/bge-large-zh-v1.5", local_files_only=True)
        return self._embedding_model

    def _connect(self):
        """延迟连接 Milvus。"""

        if self._client is None:
            try:
                from pymilvus import MilvusClient

                self._client = MilvusClient(
                    uri=f"http://{self.host}:{self.port}"
                )
            except ImportError:
                raise RetrievalError("Milvus 连接需要 pymilvus，请执行: pip install pymilvus")
            except Exception as e:
                raise RetrievalError(f"Milvus 连接失败: {e}")

    def _ensure_collection(self):
        """确保 collection 存在。"""

        self._connect()
        if self._client.has_collection(self.collection_name):
            if self._collection_has_string_primary_key():
                return
            if self.get_chunk_count() > 0:
                raise RetrievalError(
                    f"Milvus collection {self.collection_name} schema is incompatible. "
                    "Please migrate or recreate it before syncing documents."
                )
            self._client.drop_collection(self.collection_name)

        try:
            from pymilvus import DataType

            varchar_type = DataType.VARCHAR
            vector_type = DataType.FLOAT_VECTOR
        except Exception:
            varchar_type = "VARCHAR"
            vector_type = "FLOAT_VECTOR"

        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=varchar_type, is_primary=True, max_length=256)
        schema.add_field(field_name="vector", datatype=vector_type, dim=self.embedding_dim)
        schema.add_field(field_name="source", datatype=varchar_type, max_length=512)
        schema.add_field(field_name="content", datatype=varchar_type, max_length=8192)
        schema.add_field(field_name="metadata_json", datatype=varchar_type, max_length=4096)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type=MILVUS_CFG["index_type"],
            metric_type=MILVUS_CFG["metric_type"],
            params={
                "M": MILVUS_CFG["M"],
                "efConstruction": MILVUS_CFG["efConstruction"],
            },
        )

        self._client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
    def _collection_has_string_primary_key(self) -> bool:
        """Return True when the existing collection accepts string chunk ids."""

        try:
            from pymilvus import DataType

            varchar_type = DataType.VARCHAR
        except Exception:
            varchar_type = "VARCHAR"

        description = self._client.describe_collection(self.collection_name)
        for field in description.get("fields", []):
            name = field.get("name") or field.get("field_name")
            if name != "id":
                continue
            field_type = field.get("type") or field.get("datatype")
            return field_type == varchar_type or str(field_type).upper().endswith("VARCHAR")
        return False
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """计算文本的 embedding 向量。"""

        try:
            model = self._get_embedding_model()
            embeddings = model.encode(texts, normalize_embeddings=True)
            return [list(e) for e in embeddings]
        except Exception:
            return [self._fallback_embedding(text) for text in texts]

    def _fallback_embedding(self, text: str) -> list[float]:
        """Create a deterministic local embedding when the real model is unavailable."""

        vector = []
        seed = text.encode("utf-8") or b"med-rag"
        counter = 0
        while len(vector) < self.embedding_dim:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
            for byte in digest:
                vector.append((byte / 127.5) - 1.0)
                if len(vector) == self.embedding_dim:
                    break
            counter += 1

        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]
    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        """批量添加 chunks 到 Milvus。"""

        if not chunks:
            return

        self._ensure_collection()

        texts = [c.content for c in chunks]
        embeddings = self.embed_texts(texts)

        data = []
        for i, chunk in enumerate(chunks):
            metadata_json = json.dumps(
                {
                    "source": chunk.metadata.source,
                    "chunk_type": chunk.metadata.chunk_type,
                    "heading": chunk.metadata.heading,
                    "page_num": chunk.metadata.page_num,
                    "section": chunk.metadata.section,
                    "doc_type": chunk.metadata.doc_type,
                },
                ensure_ascii=False,
            )
            data.append(
                {
                    "id": chunk.id,
                    "vector": embeddings[i],
                    "source": chunk.source,
                    "content": chunk.content,
                    "metadata_json": metadata_json,
                }
            )

        self._client.insert(collection_name=self.collection_name, data=data)

    def search(self, query: str, top_k: int = 20, filter_expr: str = None) -> list[SearchResult]:
        """向量相似度检索。"""

        self._ensure_collection()

        query_embedding = self.embed_texts([query])[0]

        search_params = {
            "collection_name": self.collection_name,
            "data": [query_embedding],
            "limit": top_k,
            "output_fields": ["source", "content", "metadata_json"],
        }
        if filter_expr:
            search_params["filter"] = filter_expr

        results = self._client.search(**search_params)

        search_results = []
        for hit in results[0]:
            metadata = {}
            if hit["entity"].get("metadata_json"):
                try:
                    metadata = json.loads(hit["entity"]["metadata_json"])
                except json.JSONDecodeError:
                    pass

            chunk = DocumentChunk(
                id=hit["id"],
                source=hit["entity"]["source"],
                content=hit["entity"]["content"],
                metadata=ChunkMetadata(**metadata) if metadata else ChunkMetadata(source=hit["entity"]["source"]),
            )
            # cosine similarity = 1 - distance (Milvus returns distance)
            score = 1.0 - hit["distance"]
            search_results.append(SearchResult(chunk=chunk, score=score))

        return search_results

    def delete_chunks(self, source: str) -> None:
        """按 source 删除所有 chunks。"""

        self._connect()
        if not self._client.has_collection(self.collection_name):
            return

        self._client.delete(
            collection_name=self.collection_name,
            filter=f'source == "{source}"',
        )

    def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        """增量更新：先删除旧数据再插入新数据。"""

        if not chunks:
            return

        # 删除同一 source 的旧 chunks
        sources = set(c.source for c in chunks)
        for source in sources:
            self.delete_chunks(source)

        # 添加新 chunks
        self.add_chunks(chunks)

    def get_chunk_count(self) -> int:
        """获取 collection 中的 chunk 数量。"""

        self._connect()
        try:
            return self._client.query(
                collection_name=self.collection_name,
                filter="",
                output_fields=["count(*)"],
            )[0]["count(*)"]
        except Exception:
            return 0

    def ping(self) -> bool:
        """检查 Milvus 连接是否可用。"""

        try:
            self._connect()
            return True
        except Exception:
            return False
