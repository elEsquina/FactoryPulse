from __future__ import annotations

from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.rag.base import RetrievalResult


class SemanticRAGService:
    def __init__(self, embeddings: EmbeddingService, llm: LLMService, top_k: int = 4) -> None:
        self._embeddings = embeddings
        self._llm = llm
        self._top_k = top_k

    def answer(self, question: str) -> RetrievalResult:
        hits = self._embeddings.top_k(question, k=self._top_k)
        if not hits:
            return RetrievalResult(
                strategy="Gemini RAG",
                answer="No semantic context was available to answer this question.",
                route_reason="Fallback because no embeddings were available.",
                benchmark_reference="graphrag_benchmark.ipynb: Gemini RAG remains strong for narrative synthesis.",
            )

        context_lines = []
        for i, hit in enumerate(hits, start=1):
            context_lines.append(f"[{i}] {hit['code']} (score={hit['score']:.4f})")
            context_lines.append(hit["text"])
        context = "\n".join(context_lines)

        prompt = (
            "You are an enterprise supply-chain copilot. "
            "Use only the provided semantic context to answer. "
            "If uncertain, say what is missing. Provide concise business insight and actions.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n"
            "Answer:"
        )
        answer = self._llm.generate(prompt)
        sources = [{"product_code": h["code"], "score": round(h["score"], 4), "role": "semantic_hit"} for h in hits]

        return RetrievalResult(
            strategy="Gemini RAG",
            answer=answer,
            route_reason="Open-ended narrative path selected for broad synthesis.",
            benchmark_reference="Notebook avg score (DeepSeek-judge run): Gemini RAG 4.17/5.",
            sources=sources,
            context=context,
        )
