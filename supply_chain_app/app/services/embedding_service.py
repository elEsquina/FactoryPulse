from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass

import numpy as np

from app.domain.models import ProductProfile
from app.storage.embedding_store import EmbeddingStore

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingIndex:
    vectors: dict[str, np.ndarray]
    texts: dict[str, str]
    fingerprint: str
    model: str


class EmbeddingService:
    def __init__(
        self,
        api_key: str,
        model: str,
        dims: int,
        store: EmbeddingStore,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dims = dims
        self._store = store
        self._client = None
        self._index = EmbeddingIndex(vectors={}, texts={}, fingerprint="", model=model)

        if api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=api_key)
            except Exception as exc:
                logger.warning("Embedding client init failed. Falling back to local hash embeddings: %s", exc)

    @property
    def ready(self) -> bool:
        return bool(self._index.vectors)

    @property
    def size(self) -> int:
        return len(self._index.vectors)

    @property
    def model_name(self) -> str:
        return self._model if self._client else "local-hash-v1"

    def ensure_embeddings(self, profiles: list[ProductProfile], force_rebuild: bool = False) -> None:
        documents = {p.code: self._build_product_document(p) for p in profiles if p.code}
        fingerprint = self._fingerprint_documents(documents)

        if not force_rebuild:
            snapshot = self._store.load()
            if snapshot:
                cached_fp = str(snapshot.metadata.get("fingerprint", ""))
                cached_model = str(snapshot.metadata.get("model", ""))
                current_model = self.model_name
                if cached_fp == fingerprint and cached_model == current_model:
                    logger.info("Loaded %d embeddings from persistent cache.", len(snapshot.vectors))
                    self._index = EmbeddingIndex(
                        vectors=snapshot.vectors,
                        texts=snapshot.texts,
                        fingerprint=fingerprint,
                        model=current_model,
                    )
                    return

        logger.info("Building %d embeddings (cache miss or forced rebuild).", len(documents))
        vectors = {}
        for code, text in documents.items():
            vectors[code] = self.embed_document(text)

        metadata = {
            "fingerprint": fingerprint,
            "model": self.model_name,
            "dims": int(next(iter(vectors.values())).shape[0]) if vectors else self._dims,
        }
        self._store.save(vectors=vectors, texts=documents, metadata=metadata)
        self._index = EmbeddingIndex(vectors=vectors, texts=documents, fingerprint=fingerprint, model=self.model_name)
        logger.info("Embeddings persisted to %s.", self._store.npz_path)

    def embed_document(self, text: str) -> np.ndarray:
        if self._client:
            try:
                result = _embed_with_task(self._client, self._model, text, "RETRIEVAL_DOCUMENT")
                vec = np.array(result.embeddings[0].values, dtype=np.float32)
                return _normalize(vec)
            except Exception as exc:
                logger.warning("Remote embedding failed for document; using local fallback: %s", exc)

        return self._local_hash_embedding(text)

    def embed_query(self, text: str) -> np.ndarray:
        if self._client:
            try:
                result = _embed_with_task(self._client, self._model, text, "RETRIEVAL_QUERY")
                vec = np.array(result.embeddings[0].values, dtype=np.float32)
                return _normalize(vec)
            except Exception as exc:
                logger.warning("Remote query embedding failed; using local fallback: %s", exc)

        return self._local_hash_embedding(text)

    def top_k(self, query: str, k: int = 4) -> list[dict]:
        if not self._index.vectors:
            return []

        q = self.embed_query(query)
        codes = list(self._index.vectors.keys())
        matrix = np.stack([self._index.vectors[c] for c in codes])
        sims = matrix @ q
        top_idx = np.argsort(sims)[::-1][:k]

        return [
            {
                "code": codes[i],
                "score": float(sims[i]),
                "text": self._index.texts.get(codes[i], ""),
            }
            for i in top_idx
        ]

    def text_for_code(self, code: str) -> str | None:
        return self._index.texts.get(code)

    def _local_hash_embedding(self, text: str) -> np.ndarray:
        vec = np.zeros(self._dims, dtype=np.float32)
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self._dims
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            magnitude = 1.0 + (digest[5] / 255.0)
            vec[idx] += sign * magnitude
        if not tokens:
            vec[0] = 1.0
        return _normalize(vec)

    def _build_product_document(self, p: ProductProfile) -> str:
        plants = ", ".join(p.plants[:15]) if p.plants else "none"
        storages = ", ".join(p.storages[:15]) if p.storages else "none"
        return (
            f"Product {p.code}. Group {p.group}. Subgroup {p.subgroup}. "
            f"Plants: {plants}. Storages: {storages}. "
            f"Average delivery units {fmt(p.avg_delivery_unit)}. "
            f"Average production units {fmt(p.avg_production_unit)}. "
            f"Average sales order units {fmt(p.avg_sales_order_unit)}. "
            f"Total delivery units {fmt(p.total_delivery_unit)}. "
            f"Total production units {fmt(p.total_production_unit)}. "
            f"Observation count {p.observation_count}."
        )

    @staticmethod
    def _fingerprint_documents(documents: dict[str, str]) -> str:
        h = hashlib.sha256()
        for code in sorted(documents.keys()):
            h.update(code.encode("utf-8"))
            h.update(b"\n")
            h.update(documents[code].encode("utf-8"))
            h.update(b"\n")
        return h.hexdigest()


def _normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n <= 1e-12:
        return v
    return v / n


def fmt(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    return f"{value:.2f}"


def _embed_with_task(client, model: str, text: str, task_type: str):
    try:
        return client.models.embed_content(
            model=model,
            contents=text,
            config={"task_type": task_type},
        )
    except TypeError:
        return client.models.embed_content(
            model=model,
            contents=text,
            task_type=task_type,
        )
