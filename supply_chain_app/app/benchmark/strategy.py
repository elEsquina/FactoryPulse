from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkApproachScore:
    name: str
    average_score: float
    strength: str
    weakness: str


BENCHMARK_SOURCE = "graphrag_benchmark.ipynb"
BENCHMARK_DATE_NOTE = "Notebook outputs captured locally on this project."

# Extracted from notebook cell 27 outputs.
APPROACH_SCORES: tuple[BenchmarkApproachScore, ...] = (
    BenchmarkApproachScore(
        name="Gemini RAG",
        average_score=4.89,
        strength="Best overall for open-ended narrative answers.",
        weakness="Can miss exact structured counts and strict graph filters.",
    ),
    BenchmarkApproachScore(
        name="GraphRAG",
        average_score=4.83,
        strength="Strong on relational and similarity reasoning.",
        weakness="Can be limited when seed node selection is narrow.",
    ),
    BenchmarkApproachScore(
        name="Text2Cypher",
        average_score=3.67,
        strength="Best precision for structural/analytical graph lookups.",
        weakness="Weak on fuzzy, semantic, and open-ended reasoning prompts.",
    ),
)

ROUTING_POLICY = {
    "structured_or_analytical": "Text2Cypher",
    "semantic_or_relational": "GraphRAG",
    "open_ended_narrative": "Gemini RAG",
}

BENCHMARK_HIGHLIGHTS = (
    "Semantic similarity question favored GraphRAG (5.0 vs Gemini 4.67 vs Text2Cypher 1.0).",
    "Text2Cypher excelled for exact Cypher-compatible lookups and aggregations.",
    "Gemini RAG had highest global average (4.89) for narrative clarity and completeness.",
)
