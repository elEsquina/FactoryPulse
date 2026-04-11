from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    neo4j: bool
    llm_available: bool
    embedding_model: str
    embeddings_ready: bool
    embeddings_count: int
