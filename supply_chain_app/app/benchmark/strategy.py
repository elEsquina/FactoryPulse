from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkApproachScore:
    name: str
    average_score: float
    strength: str
    weakness: str


BENCHMARK_SOURCE = "graphrag_benchmark.ipynb"
BENCHMARK_DATE_NOTE = "Notebook outputs captured locally (20-question DeepSeek-judge benchmark)."

# Extracted from notebook cell 27 outputs.
APPROACH_SCORES: tuple[BenchmarkApproachScore, ...] = (
    BenchmarkApproachScore(
        name="Gemini RAG",
        average_score=4.17,
        strength="Strong narrative synthesis and broad semantic context.",
        weakness="Can miss exact structured counts and strict graph filters.",
    ),
    BenchmarkApproachScore(
        name="GraphRAG",
        average_score=4.20,
        strength="Best overall in the DeepSeek-judge benchmark and strongest on relational reasoning.",
        weakness="Can be limited when seed node selection is narrow.",
    ),
    BenchmarkApproachScore(
        name="Text2Cypher",
        average_score=3.62,
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
    "DeepSeek-judge benchmark used 20 questions across structural, analytical, semantic, and reasoning intents.",
    "Text2Cypher remained strongest for exact structural/analytical lookups.",
    "GraphRAG scored highest overall (4.20) with strongest semantic/reasoning performance.",
)
