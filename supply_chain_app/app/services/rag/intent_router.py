from __future__ import annotations

import re

from app.services.rag.base import RetrievalResult
from app.services.rag.graphrag_service import GraphRAGService
from app.services.rag.semantic_rag_service import SemanticRAGService
from app.services.rag.text2cypher_service import Text2CypherService


class IntentRouterService:
    """Routes each query to the best strategy using benchmark-backed policy."""

    def __init__(
        self,
        text2cypher: Text2CypherService,
        graphrag: GraphRAGService,
        semantic_rag: SemanticRAGService,
    ) -> None:
        self._text2cypher = text2cypher
        self._graphrag = graphrag
        self._semantic_rag = semantic_rag

    def answer(self, question: str) -> RetrievalResult:
        route = self._detect_route(question)

        if route == "text2cypher":
            result = self._text2cypher.answer(question)
            if result.answer.lower().startswith("text2cypher route could not"):
                # Controlled fallback chain.
                fallback = self._graphrag.answer(question)
                fallback.route_reason += " Fallback after Text2Cypher failure."
                return fallback
            return result

        if route == "graphrag":
            return self._graphrag.answer(question)

        return self._semantic_rag.answer(question)

    def _detect_route(self, question: str) -> str:
        q = question.lower().strip()

        if _looks_structured(q):
            return "text2cypher"

        if _looks_relational_or_reasoning(q):
            return "graphrag"

        return "semantic"


def _looks_structured(q: str) -> bool:
    if any(token in q for token in ["how many", "count", "total", "sum", "average", "avg", "list", "which products"]):
        if any(token in q for token in ["plant", "group", "subgroup", "storage", "assigned", "belong"]):
            return True
    return False


def _looks_relational_or_reasoning(q: str) -> bool:
    relational_tokens = [
        "similar",
        "related",
        "compare",
        "difference",
        "risk",
        "underperformance",
        "bottleneck",
        "anomaly",
        "operational profile",
        "network",
        "impact",
    ]
    if any(token in q for token in relational_tokens):
        return True

    if re.search(r"\bwhy\b|\bhow\b.*\baffect\b", q):
        return True

    return False
