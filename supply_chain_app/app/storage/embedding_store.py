from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class EmbeddingSnapshot:
    vectors: dict[str, np.ndarray]
    texts: dict[str, str]
    metadata: dict


class EmbeddingStore:
    """Persists vectors and metadata to disk to avoid unnecessary recomputation."""

    def __init__(self, npz_path: Path, metadata_path: Path) -> None:
        self._npz_path = npz_path
        self._metadata_path = metadata_path
        self._npz_path.parent.mkdir(parents=True, exist_ok=True)
        self._metadata_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def npz_path(self) -> Path:
        return self._npz_path

    @property
    def metadata_path(self) -> Path:
        return self._metadata_path

    def save(self, vectors: dict[str, np.ndarray], texts: dict[str, str], metadata: dict) -> None:
        if not vectors:
            return
        arrays = {key: value.astype(np.float32) for key, value in vectors.items()}
        np.savez_compressed(self._npz_path, **arrays)

        full_metadata = {
            **metadata,
            "doc_keys": sorted(vectors.keys()),
            "texts": texts,
        }
        self._metadata_path.write_text(json.dumps(full_metadata, indent=2), encoding="utf-8")

    def load(self) -> EmbeddingSnapshot | None:
        if not self._npz_path.exists() or not self._metadata_path.exists():
            return None

        metadata = json.loads(self._metadata_path.read_text(encoding="utf-8"))
        npz_data = np.load(self._npz_path)
        vectors = {k: np.array(npz_data[k], dtype=np.float32) for k in npz_data.files}
        texts = metadata.get("texts", {})
        return EmbeddingSnapshot(vectors=vectors, texts=texts, metadata=metadata)
