from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path, PurePosixPath


class DocumentStorage:
    ZONES = {"quarantine", "original", "parsed", "temporary"}

    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, key: str) -> Path:
        pure = PurePosixPath(key)
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or not pure.parts
            or pure.parts[0] not in self.ZONES
        ):
            raise ValueError("invalid storage key")
        candidate = (self.root / Path(*pure.parts)).resolve()
        if self.root not in candidate.parents:
            raise ValueError("invalid storage key")
        return candidate

    def allocate_quarantine_key(
        self, document_id: str, version_id: str, suffix: str
    ) -> str:
        return f"quarantine/{document_id}/{version_id}{suffix}"

    def copy_original(
        self,
        source_key: str,
        document_id: str,
        version_id: str,
        suffix: str,
    ) -> str:
        source = self.resolve(source_key)
        target_key = f"original/{document_id}/{version_id}{suffix}"
        target = self.resolve(target_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with source.open("rb") as input_file, temporary.open("xb") as output_file:
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                output_file.flush()
                os.fsync(output_file.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target_key

    def write_parsed(self, document_id: str, version_id: str, text: str) -> str:
        key = f"parsed/{document_id}/{version_id}.txt"
        target = self.resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="") as output:
                output.write(text)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return key
