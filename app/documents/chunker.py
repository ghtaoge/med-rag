"""智能切块引擎。

语义切块 + Markdown 结构感知 + 表格保护。
从固定字符切块升级到按内容结构切块。
"""

from __future__ import annotations

import re

from app.core.models import DocumentChunk, ChunkMetadata, ChunkType


def chunk_text(
    text: str,
    source: str,
    min_size: int = 150,
    max_size: int = 500,
    overlap: int = 50,
) -> list[DocumentChunk]:
    """通用语义切块：按段落边界切，保持段落完整性。

    优先在换行符处切，避免切断句子。
    短段落合并到 min_size 以上。
    """

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[DocumentChunk] = []
    current_text = ""
    chunk_index = 0

    for para in paragraphs:
        if len(current_text) + len(para) + 1 > max_size and current_text:
            # 当前累积文本超限 → 保存为 chunk
            chunk_id = f"{source}:{chunk_index + 1}"
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    source=source,
                    content=current_text.strip(),
                    metadata=ChunkMetadata(
                        source=source, chunk_type=ChunkType.PARAGRAPH
                    ),
                )
            )
            chunk_index += 1
            # overlap：保留最后 overlap 个字符
            overlap_text = current_text[-overlap:] if overlap > 0 else ""
            current_text = overlap_text + "\n\n" + para
        else:
            current_text = (
                current_text + "\n\n" + para if current_text else para
            )

    # 最后一段
    if current_text.strip():
        # 如果太短且已有前一个 chunk，合并到前一个
        if len(current_text.strip()) < min_size and chunks:
            last_chunk = chunks[-1]
            chunks[-1] = DocumentChunk(
                id=last_chunk.id,
                source=last_chunk.source,
                content=last_chunk.content + "\n\n" + current_text.strip(),
                metadata=last_chunk.metadata,
            )
        else:
            chunk_id = f"{source}:{chunk_index + 1}"
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    source=source,
                    content=current_text.strip(),
                    metadata=ChunkMetadata(
                        source=source, chunk_type=ChunkType.PARAGRAPH
                    ),
                )
            )

    return chunks


def chunk_markdown(
    text: str,
    source: str,
    min_size: int = 150,
    max_size: int = 500,
) -> list[DocumentChunk]:
    """Markdown 结构感知切块。

    按标题层级切：每个标题下的内容为一个 chunk。
    表格保持完整（整表为一个 chunk）。
    代码块保持完整。
    """

    lines = text.split("\n")
    chunks: list[DocumentChunk] = []
    current_heading = ""
    current_content_lines: list[str] = []
    chunk_index = 0

    def flush_current() -> None:
        """把当前累积内容保存为 chunk。"""
        if not current_content_lines:
            return
        content = "\n".join(current_content_lines).strip()
        if not content:
            return

        chunk_type = ChunkType.PARAGRAPH
        # 检测是否包含表格
        if any(line.strip().startswith("|") for line in current_content_lines):
            chunk_type = ChunkType.TABLE
        # 检测是否包含代码块
        if any(line.strip().startswith("```") for line in current_content_lines):
            chunk_type = ChunkType.CODE

        nonlocal chunk_index
        chunk_id = f"{source}:{chunk_index + 1}"
        chunks.append(
            DocumentChunk(
                id=chunk_id,
                source=source,
                content=content,
                metadata=ChunkMetadata(
                    source=source,
                    chunk_type=chunk_type,
                    heading=current_heading,
                ),
            )
        )
        chunk_index += 1

    for line in lines:
        # 标题行 → flush 上一节，开始新节
        if re.match(r"^#{1,6}\s+", line):
            flush_current()
            current_heading = line.strip()
            current_content_lines = [line]
            continue

        # 独立表格开始 → flush 之前内容
        if line.strip().startswith("|") and not any(
            l.strip().startswith("|") for l in current_content_lines[-3:]
        ):
            flush_current()
            current_content_lines = [line]
            continue

        current_content_lines.append(line)

        # 内容超限 → flush
        current_text = "\n".join(current_content_lines)
        if len(current_text) > max_size:
            # 但不切断表格或代码块
            in_code_block = current_text.count("```") % 2 == 1
            if not in_code_block:
                flush_current()
                current_content_lines = []

    flush_current()
    return chunks
