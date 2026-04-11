from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalResult:
    strategy: str
    answer: str
    route_reason: str
    benchmark_reference: str
    sources: list[dict] = field(default_factory=list)
    cypher: str | None = None
    context: str | None = None
