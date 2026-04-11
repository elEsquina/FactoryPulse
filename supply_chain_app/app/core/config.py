from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Supply Chain Intelligence Hub"
    app_version: str = "2.0.0"
    debug: bool = False
    api_prefix: str = "/api/v1"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"

    gemini_api_key: str = ""
    llm_model: str = "gemma-3-27b-it"
    embed_model: str = "gemini-embedding-001"
    embedding_dims: int = 3072

    embedding_cache_npz: str = "/app/runtime/embeddings/products.npz"
    embedding_cache_meta: str = "/app/runtime/embeddings/products.meta.json"

    processed_data_dir: str = "/app/data/processed"
    auto_bootstrap_data: bool = True
    bootstrap_batch_size: int = 5000

    semantic_top_k: int = 4
    graphrag_seed_k: int = 2
    graphrag_peer_limit: int = 12

    llm_timeout_seconds: int = 45

    @property
    def embedding_cache_npz_path(self) -> Path:
        return Path(self.embedding_cache_npz)

    @property
    def embedding_cache_meta_path(self) -> Path:
        return Path(self.embedding_cache_meta)

    @property
    def processed_data_dir_path(self) -> Path:
        return Path(self.processed_data_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
