from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass

import numpy as np

from app.domain.models import ProductProfile
from app.storage.embedding_store import EmbeddingStore


# A module-level logger is used instead of print() so embedding failures,
# cache hits, rebuilds, and fallback behavior integrate with the application's
# normal logging configuration.
logger = logging.getLogger(__name__)


@dataclass
class EmbeddingIndex:
    """
    In-memory representation of the searchable embedding collection.

    vectors:
        Maps each product code to its numeric embedding vector.

    texts:
        Stores the original generated product document corresponding to each
        code. Keeping this alongside the vector makes retrieval results useful
        without having to reconstruct the product description again.

    fingerprint:
        Hash representing the exact collection of product documents used to
        build the index. It is used to detect whether cached embeddings are
        still valid.

    model:
        Identifies which embedding implementation/model generated the vectors.
        This prevents vectors created by one model from being reused with a
        different model.
    """

    vectors: dict[str, np.ndarray]
    texts: dict[str, str]
    fingerprint: str
    model: str


class EmbeddingService:
    """
    Handles the complete embedding and semantic-retrieval workflow.

    The service has two possible embedding backends:

        1. A remote Google embedding model, when an API key and working client
           are available.

        2. A deterministic local hash-based embedding fallback.

    The fallback allows the application to remain functional even if remote
    embedding initialization or an API request fails.

    The service also coordinates persistent caching through EmbeddingStore so
    embeddings do not need to be regenerated every time the application starts.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        dims: int,
        store: EmbeddingStore,
    ) -> None:
        # Store configuration required by both remote and fallback embedding
        # paths.
        self._api_key = api_key
        self._model = model
        self._dims = dims
        self._store = store

        # None means the remote embedding backend is currently unavailable.
        # This also controls whether model_name reports the requested remote
        # model or the local fallback implementation.
        self._client = None

        # Start with an empty index. ensure_embeddings() will either load a
        # compatible persisted index or construct a new one.
        self._index = EmbeddingIndex(
            vectors={},
            texts={},
            fingerprint="",
            model=model,
        )

        # The external SDK is imported only when a key is supplied.
        #
        # This lazy import has two benefits:
        #   - environments using only the local fallback do not necessarily
        #     depend on successful Google client initialization;
        #   - configuration/client problems do not make the whole application
        #     unusable.
        if api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=api_key)

            except Exception as exc:
                # Failure to initialize the remote backend is intentionally
                # non-fatal. Retrieval can continue using deterministic local
                # hash embeddings.
                logger.warning(
                    "Embedding client init failed. "
                    "Falling back to local hash embeddings: %s",
                    exc,
                )

    @property
    def ready(self) -> bool:
        """
        Return True once at least one product embedding is available.

        An initialized service is not necessarily ready: the index remains empty
        until ensure_embeddings() either loads or creates embeddings.
        """
        return bool(self._index.vectors)

    @property
    def size(self) -> int:
        """
        Number of indexed product documents.
        """
        return len(self._index.vectors)

    @property
    def model_name(self) -> str:
        """
        Return the effective embedding backend name.

        This is deliberately based on whether the remote client exists rather
        than always returning self._model. The value becomes part of the cache
        metadata, which prevents local hash vectors from being mistaken for
        vectors produced by the remote model.
        """
        return self._model if self._client else "local-hash-v1"

    def ensure_embeddings(
        self,
        profiles: list[ProductProfile],
        force_rebuild: bool = False,
    ) -> None:
        """
        Ensure an embedding index exists for the supplied product profiles.

        High-level flow:

            ProductProfile objects
                -> normalized text documents
                -> fingerprint
                -> attempt cache load
                -> otherwise generate embeddings
                -> persist embeddings
                -> place them into the in-memory index

        The fingerprint and model name together determine whether a stored
        index is safe to reuse.
        """

        # A product code acts as the unique retrieval key.
        #
        # Profiles without a code are ignored because there would be no stable
        # identifier with which to store or retrieve their embeddings.
        documents = {
            p.code: self._build_product_document(p)
            for p in profiles
            if p.code
        }

        # The fingerprint represents the actual textual content that will be
        # embedded. If any relevant product data changes, its document changes,
        # causing a different fingerprint and therefore a cache rebuild.
        fingerprint = self._fingerprint_documents(documents)

        if not force_rebuild:
            # Persistent storage is checked before making potentially expensive
            # remote embedding calls.
            snapshot = self._store.load()

            if snapshot:
                cached_fp = str(
                    snapshot.metadata.get("fingerprint", "")
                )
                cached_model = str(
                    snapshot.metadata.get("model", "")
                )
                current_model = self.model_name

                # Cached vectors are reusable only when BOTH:
                #
                # 1. the underlying product documents are unchanged, and
                # 2. the embedding model/backend is unchanged.
                #
                # The second condition is important because vectors generated by
                # different embedding models generally do not share the same
                # semantic vector space.
                if (
                    cached_fp == fingerprint
                    and cached_model == current_model
                ):
                    logger.info(
                        "Loaded %d embeddings from persistent cache.",
                        len(snapshot.vectors),
                    )

                    # Reconstruct the in-memory search index directly from the
                    # persisted snapshot. No embedding API calls are needed.
                    self._index = EmbeddingIndex(
                        vectors=snapshot.vectors,
                        texts=snapshot.texts,
                        fingerprint=fingerprint,
                        model=current_model,
                    )
                    return

        # Reaching this point means one of the following occurred:
        #
        #   - no persistent cache exists;
        #   - product data changed;
        #   - the embedding backend/model changed;
        #   - force_rebuild=True was requested.
        logger.info(
            "Building %d embeddings "
            "(cache miss or forced rebuild).",
            len(documents),
        )

        vectors: dict[str, np.ndarray] = {}

        # Every product document receives exactly one vector using its product
        # code as the lookup key.
        for code, text in documents.items():
            vectors[code] = self.embed_document(text)

        # Store enough metadata to validate the cache on a future run.
        #
        # The actual vector dimension is read from the generated vectors rather
        # than blindly trusting self._dims because a remote model may return a
        # dimension different from the local fallback configuration.
        metadata = {
            "fingerprint": fingerprint,
            "model": self.model_name,
            "dims": (
                int(next(iter(vectors.values())).shape[0])
                if vectors
                else self._dims
            ),
        }

        # Persist vectors AND their source text together. The retrieval layer can
        # therefore return both similarity scores and the text responsible for
        # each vector.
        self._store.save(
            vectors=vectors,
            texts=documents,
            metadata=metadata,
        )

        # Update the live in-memory index after persistence succeeds.
        self._index = EmbeddingIndex(
            vectors=vectors,
            texts=documents,
            fingerprint=fingerprint,
            model=self.model_name,
        )

        logger.info(
            "Embeddings persisted to %s.",
            self._store.npz_path,
        )

    def embed_document(self, text: str) -> np.ndarray:
        """
        Embed text that will be stored in the retrieval index.

        Remote embedding APIs can distinguish between documents being indexed
        and queries being searched. Here the RETRIEVAL_DOCUMENT task type tells
        the model that this text represents searchable corpus content.
        """

        if self._client:
            try:
                result = _embed_with_task(
                    self._client,
                    self._model,
                    text,
                    "RETRIEVAL_DOCUMENT",
                )

                # Convert the SDK representation into a consistent float32
                # NumPy vector used throughout the rest of the service.
                vec = np.array(
                    result.embeddings[0].values,
                    dtype=np.float32,
                )

                # All vectors are normalized to unit length so semantic ranking
                # can later use a simple dot product as cosine similarity.
                return _normalize(vec)

            except Exception as exc:
                # A temporary network/API failure should not make retrieval
                # impossible. The service falls back to its local deterministic
                # embedding method.
                logger.warning(
                    "Remote embedding failed for document; "
                    "using local fallback: %s",
                    exc,
                )

        return self._local_hash_embedding(text)

    def embed_query(self, text: str) -> np.ndarray:
        """
        Embed the user's search/query text.

        Query and document embeddings are kept as separate operations because
        retrieval-oriented embedding models may optimize vectors differently
        depending on whether the input is a stored document or a search query.
        """

        if self._client:
            try:
                result = _embed_with_task(
                    self._client,
                    self._model,
                    text,
                    "RETRIEVAL_QUERY",
                )

                vec = np.array(
                    result.embeddings[0].values,
                    dtype=np.float32,
                )

                return _normalize(vec)

            except Exception as exc:
                logger.warning(
                    "Remote query embedding failed; "
                    "using local fallback: %s",
                    exc,
                )

        return self._local_hash_embedding(text)

    def top_k(
        self,
        query: str,
        k: int = 4,
    ) -> list[dict]:
        """
        Return the k indexed products most similar to a query.

        Since every stored vector and query vector is normalized, the matrix
        multiplication performed below computes cosine similarity:

            cosine(a, b) = a dot b

        when ||a|| = ||b|| = 1.
        """

        # There is nothing to search before ensure_embeddings() has populated
        # the index.
        if not self._index.vectors:
            return []

        # The query is embedded using the same effective backend used by the
        # service.
        q = self.embed_query(query)

        # Dictionary ordering is preserved so `codes[i]` corresponds exactly to
        # row i of the stacked embedding matrix.
        codes = list(self._index.vectors.keys())

        # Convert individual vectors into shape:
        #
        #     (number_of_products, embedding_dimensions)
        #
        # This lets NumPy compute every similarity score in one vectorized
        # matrix operation.
        matrix = np.stack([
            self._index.vectors[c]
            for c in codes
        ])

        # matrix has shape (N, D)
        # q      has shape (D,)
        #
        # Result:
        # sims   has shape (N,)
        #
        # Each output value is the cosine similarity between the query and one
        # indexed product because the vectors were normalized earlier.
        sims = matrix @ q

        # argsort() returns ascending order, so [::-1] reverses it to highest
        # similarity first. [:k] keeps only the requested number of results.
        top_idx = np.argsort(sims)[::-1][:k]

        # Include product code, numerical score, and the original generated text
        # so downstream callers have both machine-readable ranking information
        # and human-readable context.
        return [
            {
                "code": codes[i],
                "score": float(sims[i]),
                "text": self._index.texts.get(
                    codes[i],
                    "",
                ),
            }
            for i in top_idx
        ]

    def text_for_code(self, code: str) -> str | None:
        """
        Retrieve the indexed document text associated with a product code.

        None is returned naturally by dict.get() when the product is not part of
        the current embedding index.
        """
        return self._index.texts.get(code)

    def _local_hash_embedding(
        self,
        text: str,
    ) -> np.ndarray:
        """
        Produce a deterministic fixed-dimensional fallback embedding.

        This is not a semantic language-model embedding. Instead, it is a
        feature-hashing representation: each token deterministically contributes
        to one vector dimension based on SHA-256.

        It is useful as a lightweight fallback because:

            - no network connection is required;
            - no external model/API is required;
            - the same input always produces the same vector;
            - texts sharing tokens tend to share vector components.

        Therefore it provides approximate lexical similarity rather than the
        deeper semantic similarity expected from a learned embedding model.
        """

        # Start with an all-zero feature vector of the configured dimension.
        vec = np.zeros(
            self._dims,
            dtype=np.float32,
        )

        # Keep letters, digits, and underscores and normalize case.
        #
        # For example:
        #
        #     "Plant A12, storage_4"
        #
        # becomes approximately:
        #
        #     ["plant", "a12", "storage_4"]
        tokens = re.findall(
            r"[a-zA-Z0-9_]+",
            text.lower(),
        )

        for token in tokens:
            # SHA-256 is used here as a deterministic mapping mechanism, not for
            # password/security purposes.
            digest = hashlib.sha256(
                token.encode("utf-8")
            ).digest()

            # Convert the first four hash bytes into an integer and reduce it
            # modulo the embedding dimension. This determines which coordinate
            # the token contributes to.
            idx = (
                int.from_bytes(
                    digest[:4],
                    "big",
                )
                % self._dims
            )

            # Signed feature hashing reduces systematic positive collisions.
            # Two different tokens hashing to the same coordinate can therefore
            # make contributions with opposite signs.
            sign = (
                1.0
                if digest[4] % 2 == 0
                else -1.0
            )

            # Give each token a deterministic magnitude between approximately
            # 1.0 and 2.0. The sixth hash byte determines this weight.
            magnitude = 1.0 + (
                digest[5] / 255.0
            )

            # Repeated tokens accumulate in the same hashed feature, meaning
            # token frequency influences the final representation.
            vec[idx] += sign * magnitude

        # An empty input would otherwise produce an all-zero vector, which
        # cannot meaningfully be normalized or compared using cosine similarity.
        #
        # Assigning one dimension creates a deterministic non-zero placeholder.
        if not tokens:
            vec[0] = 1.0

        return _normalize(vec)

    def _build_product_document(
        self,
        p: ProductProfile,
    ) -> str:
        """
        Convert a structured ProductProfile into natural-language retrieval text.

        Embedding models work on text, while ProductProfile stores information
        across structured fields. This method acts as the bridge between those
        representations.

        Only the first 15 plant/storage values are included to prevent extremely
        large profiles from dominating document length.
        """

        plants = (
            ", ".join(p.plants[:15])
            if p.plants
            else "none"
        )

        storages = (
            ", ".join(p.storages[:15])
            if p.storages
            else "none"
        )

        # Numeric values are converted through fmt() so missing/NaN values have
        # a stable textual representation instead of being embedded as Python
        # implementation details such as "nan" or "None".
        return (
            f"Product {p.code}. "
            f"Group {p.group}. "
            f"Subgroup {p.subgroup}. "
            f"Plants: {plants}. "
            f"Storages: {storages}. "
            f"Average delivery units {fmt(p.avg_delivery_unit)}. "
            f"Average production units {fmt(p.avg_production_unit)}. "
            f"Average sales order units {fmt(p.avg_sales_order_unit)}. "
            f"Total delivery units {fmt(p.total_delivery_unit)}. "
            f"Total production units {fmt(p.total_production_unit)}. "
            f"Observation count {p.observation_count}."
        )

    @staticmethod
    def _fingerprint_documents(
        documents: dict[str, str],
    ) -> str:
        """
        Produce a stable SHA-256 fingerprint of the complete document collection.

        This fingerprint is used for cache invalidation.

        Sorting the codes is essential: dictionary insertion order should not
        determine whether two logically identical datasets receive the same
        fingerprint.
        """

        h = hashlib.sha256()

        for code in sorted(documents.keys()):
            # Include both the identifier and document content so changing either
            # one invalidates the cached embedding collection.
            h.update(code.encode("utf-8"))
            h.update(b"\n")

            h.update(
                documents[code].encode("utf-8")
            )
            h.update(b"\n")

        return h.hexdigest()


def _normalize(v: np.ndarray) -> np.ndarray:
    """
    Convert a vector to unit L2 length.

    After normalization:

        ||v|| = 1

    This allows a dot product between two normalized embedding vectors to act
    as cosine similarity, which makes top_k() simple and efficient.
    """

    n = float(np.linalg.norm(v))

    # Avoid dividing by zero (or an extremely tiny number). Returning the vector
    # unchanged is safer than producing NaN/Inf values.
    if n <= 1e-12:
        return v

    return v / n


def fmt(value: float | None) -> str:
    """
    Convert optional numeric product metrics into stable document text.

    Missing values and NaN values are represented as "N/A"; otherwise values are
    rounded to two decimal places. This keeps generated product documents both
    readable and deterministic.
    """

    if value is None or math.isnan(value):
        return "N/A"

    return f"{value:.2f}"


def _embed_with_task(
    client,
    model: str,
    text: str,
    task_type: str,
):
    """
    Compatibility wrapper around the embedding SDK.

    Different versions of the client library may expose the retrieval task type
    using different calling conventions.

    The preferred call passes task_type inside the config dictionary. If that
    exact signature is rejected with TypeError, the function retries using the
    older/direct task_type argument style.
    """

    try:
        return client.models.embed_content(
            model=model,
            contents=text,
            config={
                "task_type": task_type,
            },
        )

    except TypeError:
        # This fallback specifically handles SDK signature differences. Other
        # runtime/API exceptions should continue upward to embed_document() or
        # embed_query(), where the service can switch to its local embedding
        # implementation.
        return client.models.embed_content(
            model=model,
            contents=text,
            task_type=task_type,
        )
