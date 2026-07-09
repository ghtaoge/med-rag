"""Lightweight document index state persisted beside the knowledge files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

INDEX_STATE_FILE = ".med-rag-index-state.json"


def _state_path(knowledge_dir: Path) -> Path:
    return Path(knowledge_dir) / INDEX_STATE_FILE


def load_index_state(knowledge_dir: Path) -> dict[str, dict[str, Any]]:
    path = _state_path(knowledge_dir)
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def save_index_state(knowledge_dir: Path, state: dict[str, dict[str, Any]]) -> None:
    path = _state_path(knowledge_dir)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def set_index_state(knowledge_dir: Path, filename: str, chunk_count: int) -> None:
    state = load_index_state(knowledge_dir)
    state[filename] = {"chunk_count": chunk_count}
    save_index_state(knowledge_dir, state)


def remove_index_state(knowledge_dir: Path, filename: str) -> None:
    state = load_index_state(knowledge_dir)
    if filename not in state:
        return

    state.pop(filename, None)
    save_index_state(knowledge_dir, state)