"""CSV 加载器。pandas 读取数据表格。"""

from __future__ import annotations

from pathlib import Path

from app.documents.loader.base import DocumentLoader


class CsvLoader(DocumentLoader):
    """CSV 文件加载器。"""

    def load(self, file_path: Path) -> str:
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("CSV 加载需要 pandas，请执行: pip install pandas")

        df = pd.read_csv(str(file_path), encoding="utf-8")
        rows = ["| " + " | ".join(str(col) for col in df.columns) + " |"]
        for row in df.itertuples(index=False, name=None):
            rows.append("| " + " | ".join("" if value is None else str(value) for value in row) + " |")
        return "\n".join(rows)
