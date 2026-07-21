from __future__ import annotations

import unicodedata


class InputShapeError(ValueError):
    pass


def normalize_input(value: str, max_chars: int) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    kept: list[str] = []
    for char in normalized:
        category = unicodedata.category(char)
        if char in {"\n", "\t"}:
            kept.append(char)
        elif category not in {"Cc", "Cf", "Cs"}:
            kept.append(char)
    result = "".join(kept).strip()
    if not result:
        raise InputShapeError("输入内容为空")
    if len(result) > max_chars:
        raise InputShapeError("输入内容过长")
    return result
