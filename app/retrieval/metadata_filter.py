"""元数据过滤。将 Python dict 转为 Milvus filter expression。"""

from __future__ import annotations


def build_filter(filter_dict: dict | None) -> str | None:
    """将元数据过滤字典转为 Milvus filter expression。

    示例：
        {"source": "药品说明书.md"} → 'source == "药品说明书.md"'
        {"doc_type": "药品说明书"} → 'metadata_json like "%药品说明书%"'
        {"source": ["a.md", "b.md"]} → 'source == "a.md" || source == "b.md"'
    """

    if not filter_dict:
        return None

    expressions = []

    for key, value in filter_dict.items():
        if key == "source":
            if isinstance(value, list):
                parts = [f'source == "{v}"' for v in value]
                expressions.append(" || ".join(parts))
            else:
                expressions.append(f'source == "{value}"')
        elif key in ("doc_type", "heading", "section", "chunk_type"):
            # 这些字段存储在 metadata_json 中
            expressions.append(f'metadata_json like "%{value}%"')
        elif key == "page_num":
            expressions.append(f'metadata_json like "%page_num%{value}%"')

    if not expressions:
        return None

    return " && ".join(expressions)
