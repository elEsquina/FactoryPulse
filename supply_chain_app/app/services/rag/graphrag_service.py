from __future__ import annotations

from app.repositories.neo4j_repository import Neo4jRepository
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.rag.base import RetrievalResult


class GraphRAGService:
    def __init__(
        self,
        neo4j: Neo4jRepository,
        embeddings: EmbeddingService,
        llm: LLMService,
        seed_k: int,
        peer_limit: int,
    ) -> None:
        self._neo4j = neo4j
        self._embeddings = embeddings
        self._llm = llm
        self._seed_k = seed_k
        self._peer_limit = peer_limit

    def answer(self, question: str) -> RetrievalResult:
        seeds = self._embeddings.top_k(question, k=self._seed_k)
        seed_codes = [s["code"] for s in seeds]
        subgraph = self._neo4j.get_subgraph_context(seed_codes, peer_limit=self._peer_limit)

        metrics_by_code = {row["code"]: row for row in subgraph.get("metrics", []) if row.get("code")}
        lines: list[str] = ["GraphRAG context:"]
        sources = []
        for seed in subgraph.get("seeds", []):
            code = seed.get("seed_code", "?")
            m = metrics_by_code.get(code, {})
            sources.append({"product_code": code, "score": None, "role": "seed"})
            lines.append(f"Seed {code} | group={seed.get('grp')} | subgroup={seed.get('subgroup')}")
            lines.append(f"Plants: {', '.join(seed.get('plants', [])[:15]) or 'none'}")
            lines.append(f"Storages: {', '.join(seed.get('storages', [])[:15]) or 'none'}")
            lines.append(
                "Metrics: "
                f"avg_delivery={m.get('avg_delivery')} avg_production={m.get('avg_production')} "
                f"total_delivery={m.get('total_delivery')} total_production={m.get('total_production')}"
            )
            peers = seed.get("peers", [])
            if peers:
                lines.append(f"Connected peers: {', '.join(peers[: self._peer_limit])}")
                for peer in peers[: self._peer_limit]:
                    sources.append({"product_code": peer, "score": None, "role": "peer"})
            lines.append("")

        context = "\n".join(lines)
        prompt = (
            "You are a supply-chain analyst for corporate operations. "
            "Use only this graph-aware context. "
            "Answer with: 1) direct answer, 2) risk/impact assessment, 3) recommended action.\n\n"
            f"{context}\n"
            f"Question: {question}\n"
            "Answer:"
        )
        answer = self._llm.generate(prompt)

        return RetrievalResult(
            strategy="GraphRAG",
            answer=answer,
            route_reason="Relational/semantic question routed to GraphRAG.",
            benchmark_reference="Notebook: GraphRAG scored 5.0 on semantic similarity question.",
            sources=sources,
            context=context,
        )
