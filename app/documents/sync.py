"""增量同步引擎。SHA-256 文件指纹 + 双缓冲索引切换。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_config
from app.core.exceptions import DocumentError
from app.core.models import DocumentChunk
from app.documents.loader import load_document
from app.documents.chunker import chunk_text, chunk_markdown
from app.documents.index_state import set_index_state, remove_index_state
from app.documents.file_safety import resolve_child, validate_client_filename

config = get_config()


@dataclass
class FileChange:
    """文件变更记录。"""

    filename: str
    change_type: str  # "add" | "modify" | "delete"
    old_hash: str = ""
    new_hash: str = ""


class DocumentSync:
    """增量同步引擎。

    核心机制：文件指纹 + 变更检测 + 双缓冲切换。
    - 每个文件计算 SHA-256 hash，存入 Redis
    - 新增 → 加载→切块→写入 Milvus+Whoosh
    - 修改 → 删除旧chunks→重新加载→切块→写入
    - 删除 → 从 Milvus+Whoosh 删除对应 chunks
    """

    def __init__(
        self,
        knowledge_dir: Path,
        redis_client=None,
        milvus_store=None,
        keyword_store=None,
    ):
        self.knowledge_dir = knowledge_dir
        self.redis_client = redis_client
        self.milvus_store = milvus_store
        self.keyword_store = keyword_store

        # 双缓冲
        self.active_chunks: dict[str, list[DocumentChunk]] = {}
        self.staging_chunks: dict[str, list[DocumentChunk]] = {}

    def _file_hash(self, file_path: Path) -> str:
        """计算文件的 SHA-256 hash。"""

        sha256 = hashlib.sha256()
        content = file_path.read_bytes()
        sha256.update(content)
        return sha256.hexdigest()

    def _get_stored_hash(self, filename: str) -> str:
        """从 Redis 获取已存储的文件 hash。"""

        if self.redis_client is None:
            return ""

        prefix = config["redis"]["file_hash_prefix"]
        key = f"{prefix}{filename}"
        return self.redis_client.get(key) or ""

    def _set_stored_hash(self, filename: str, hash_value: str) -> None:
        """将文件 hash 存入 Redis。"""

        if self.redis_client is None:
            return

        prefix = config["redis"]["file_hash_prefix"]
        key = f"{prefix}{filename}"
        self.redis_client.set(key, hash_value)

    def _delete_stored_hash(self, filename: str) -> None:
        """从 Redis 删除文件 hash。"""

        if self.redis_client is None:
            return

        prefix = config["redis"]["file_hash_prefix"]
        key = f"{prefix}{filename}"
        self.redis_client.delete(key)

    def detect_changes(self) -> list[FileChange]:
        """检测知识库目录中的文件变更。"""

        changes = []

        # 扫描现有文件
        existing_files = {}
        for file_path in sorted(self.knowledge_dir.glob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in {".txt", ".md", ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tiff", ".xlsx", ".csv", ".pptx", ".bmp"}:
                continue
            existing_files[file_path.name] = file_path

        # 检查每个现有文件
        for filename, file_path in existing_files.items():
            current_hash = self._file_hash(file_path)
            stored_hash = self._get_stored_hash(filename)

            if not stored_hash:
                changes.append(
                    FileChange(filename=filename, change_type="add", new_hash=current_hash)
                )
            elif stored_hash != current_hash:
                changes.append(
                    FileChange(
                        filename=filename,
                        change_type="modify",
                        old_hash=stored_hash,
                        new_hash=current_hash,
                    )
                )

        # 检查已删除文件（Redis 中有 hash 但文件不存在）
        if self.redis_client is not None:
            # 通过扫描 active_chunks 的 keys 来检测已删除文件
            for filename in list(self.active_chunks.keys()):
                if filename not in existing_files:
                    changes.append(
                        FileChange(
                            filename=filename,
                            change_type="delete",
                            old_hash=self._get_stored_hash(filename),
                        )
                    )

        return changes

    def sync_file(self, filename: str, force: bool = False) -> int:
        """同步单个文件。返回新 chunk 数量。"""

        filename = validate_client_filename(filename)
        file_path = resolve_child(self.knowledge_dir, filename)

        if not file_path.exists():
            # 文件已删除
            self._remove_chunks(filename)
            return 0

        # 加载文档
        try:
            text = load_document(file_path)
        except Exception as e:
            raise DocumentError(f"加载文件 {filename} 失败: {e}")

        # 切块
        if filename.endswith(".md"):
            chunks = chunk_markdown(
                text,
                source=filename,
                min_size=config["chunker"]["min_chunk_size"],
                max_size=config["chunker"]["max_chunk_size"],
            )
        else:
            chunks = chunk_text(
                text,
                source=filename,
                min_size=config["chunker"]["min_chunk_size"],
                max_size=config["chunker"]["max_chunk_size"],
                overlap=config["chunker"]["overlap"],
            )

        # 写入 staging（双缓冲）
        self.staging_chunks[filename] = chunks

        # 写入向量库和关键词索引
        if self.milvus_store is not None:
            self.milvus_store.delete_chunks(filename)
            self.milvus_store.add_chunks(chunks)

        if self.keyword_store is not None:
            self.keyword_store.delete_chunks(filename)
            self.keyword_store.add_chunks(chunks)

        # 更新 Redis hash
        self._set_stored_hash(filename, self._file_hash(file_path))
        set_index_state(self.knowledge_dir, filename, len(chunks))

        # Swap：从 staging 移到 active
        self.active_chunks[filename] = self.staging_chunks.pop(filename)

        return len(chunks)

    def sync_all(self) -> int:
        """全量同步所有变更文件。返回总 chunk 数量。"""

        changes = self.detect_changes()
        total = 0

        for change in changes:
            if change.change_type == "delete":
                self._remove_chunks(change.filename)
            else:
                total += self.sync_file(change.filename, force=True)

        return total

    def _remove_chunks(self, filename: str) -> None:
        """删除指定文件的 chunks。"""

        had_indexed_chunks = filename in self.active_chunks or filename in self.staging_chunks

        # 从活跃索引移除
        self.active_chunks.pop(filename, None)
        self.staging_chunks.pop(filename, None)

        if had_indexed_chunks:
            # 从向量库删除
            if self.milvus_store is not None:
                self.milvus_store.delete_chunks(filename)

            # 从关键词索引删除
            if self.keyword_store is not None:
                self.keyword_store.delete_chunks(filename)

        # 从 Redis 删除 hash
        self._delete_stored_hash(filename)
        remove_index_state(self.knowledge_dir, filename)

    def get_total_chunk_count(self) -> int:
        """获取活跃索引中的总 chunk 数。"""

        return sum(len(chunks) for chunks in self.active_chunks.values())

    def swap(self) -> None:
        """原子性交换：staging → active。"""

        for filename, chunks in self.staging_chunks.items():
            self.active_chunks[filename] = chunks
        self.staging_chunks.clear()
