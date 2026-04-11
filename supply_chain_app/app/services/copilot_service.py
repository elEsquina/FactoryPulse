from __future__ import annotations

from datetime import datetime, timezone

from app.benchmark.strategy import BENCHMARK_SOURCE
from app.domain.models import RoutedAnswer
from app.services.rag.intent_router import IntentRouterService


class CopilotService:
    def __init__(self, router: IntentRouterService) -> None:
        self._router = router

    def ask(self, question: str) -> dict:
        result = self._router.answer(question)
        payload = RoutedAnswer(
            strategy=result.strategy,
            route_reason=result.route_reason,
            benchmark_reference=f"{BENCHMARK_SOURCE} | {result.benchmark_reference}",
            answer=result.answer,
            sources=result.sources,
            cypher=result.cypher,
            debug_context=result.context,
        )
        return {
            "question": question,
            "strategy": payload.strategy,
            "route_reason": payload.route_reason,
            "benchmark_reference": payload.benchmark_reference,
            "answer": payload.answer,
            "sources": payload.sources,
            "cypher": payload.cypher,
            "debug_context": payload.debug_context,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
