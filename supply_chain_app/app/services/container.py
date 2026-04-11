from __future__ import annotations

import logging

from app.benchmark.strategy import (
    APPROACH_SCORES,
    BENCHMARK_DATE_NOTE,
    BENCHMARK_HIGHLIGHTS,
    BENCHMARK_SOURCE,
    ROUTING_POLICY,
)
from app.core.config import Settings
from app.repositories.data_bootstrap_repository import DataBootstrapRepository
from app.repositories.neo4j_repository import Neo4jRepository
from app.services.analytics_service import AnalyticsService
from app.services.copilot_service import CopilotService
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.rag.graphrag_service import GraphRAGService
from app.services.rag.intent_router import IntentRouterService
from app.services.rag.semantic_rag_service import SemanticRAGService
from app.services.rag.text2cypher_service import Text2CypherService
from app.storage.embedding_store import EmbeddingStore

logger = logging.getLogger(__name__)


class AppContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.neo4j = Neo4jRepository(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )
        self.bootstrap = DataBootstrapRepository(
            neo4j_repo=self.neo4j,
            processed_dir=settings.processed_data_dir_path,
            batch_size=settings.bootstrap_batch_size,
        )
        self.embedding_store = EmbeddingStore(
            npz_path=settings.embedding_cache_npz_path,
            metadata_path=settings.embedding_cache_meta_path,
        )
        self.llm = LLMService(
            api_key=settings.gemini_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        self.embeddings = EmbeddingService(
            api_key=settings.gemini_api_key,
            model=settings.embed_model,
            dims=settings.embedding_dims,
            store=self.embedding_store,
        )
        self.graph_rag = GraphRAGService(
            neo4j=self.neo4j,
            embeddings=self.embeddings,
            llm=self.llm,
            seed_k=settings.graphrag_seed_k,
            peer_limit=settings.graphrag_peer_limit,
        )
        self.semantic_rag = SemanticRAGService(
            embeddings=self.embeddings,
            llm=self.llm,
            top_k=settings.semantic_top_k,
        )
        self.text2cypher = Text2CypherService(neo4j=self.neo4j, llm=self.llm)
        self.intent_router = IntentRouterService(
            text2cypher=self.text2cypher,
            graphrag=self.graph_rag,
            semantic_rag=self.semantic_rag,
        )
        self.analytics = AnalyticsService(self.neo4j)
        self.copilot = CopilotService(self.intent_router)

    def startup(self) -> None:
        if not self.neo4j.ping():
            raise RuntimeError("Cannot connect to Neo4j. Check URI/user/password and container health.")

        if self.settings.auto_bootstrap_data:
            self.bootstrap.bootstrap_if_needed()

        profiles = self.neo4j.fetch_product_profiles()
        self.embeddings.ensure_embeddings(profiles=profiles)
        logger.info("Startup complete: products=%d embeddings=%d", len(profiles), self.embeddings.size)

    def shutdown(self) -> None:
        self.neo4j.close()

    def health(self) -> dict:
        return {
            "neo4j": self.neo4j.ping(),
            "llm_available": self.llm.available,
            "embedding_model": self.embeddings.model_name,
            "embeddings_ready": self.embeddings.ready,
            "embeddings_count": self.embeddings.size,
        }

    def benchmark_strategy(self) -> dict:
        return {
            "source": BENCHMARK_SOURCE,
            "notes": BENCHMARK_DATE_NOTE,
            "scores": [
                {
                    "approach": score.name,
                    "average_score": score.average_score,
                    "strength": score.strength,
                    "weakness": score.weakness,
                }
                for score in APPROACH_SCORES
            ],
            "routing_policy": ROUTING_POLICY,
            "highlights": list(BENCHMARK_HIGHLIGHTS),
        }
