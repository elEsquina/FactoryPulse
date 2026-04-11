from __future__ import annotations

from pydantic import BaseModel, Field


class CopilotQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1500)


class CopilotQueryResponse(BaseModel):
    question: str
    strategy: str
    route_reason: str
    benchmark_reference: str
    answer: str
    sources: list[dict]
    cypher: str | None = None
    debug_context: str | None = None
    generated_at: str
