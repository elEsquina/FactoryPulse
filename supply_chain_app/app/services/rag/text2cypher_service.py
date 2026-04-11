from __future__ import annotations

import json
import re
from typing import Any

from app.repositories.neo4j_repository import Neo4jRepository
from app.services.llm_service import LLMService
from app.services.rag.base import RetrievalResult


GRAPH_SCHEMA = """
Nodes:
- Product {code, group, subgroup}
- Plant {id}
- Storage {id}
- Observation {obs_key, date, metric, unit_type, value}

Relationships:
- (:Product)-[:ASSIGNED_TO_PLANT]->(:Plant)
- (:Product)-[:STORED_IN]->(:Storage)
- (:Product)-[:HAS_OBSERVATION]->(:Observation)
"""


class Text2CypherService:
    def __init__(self, neo4j: Neo4jRepository, llm: LLMService) -> None:
        self._neo4j = neo4j
        self._llm = llm

    def answer(self, question: str) -> RetrievalResult:
        cypher = self._generate_cypher(question)
        rows: list[dict[str, Any]] = []
        error = None
        if cypher:
            try:
                rows = self._neo4j.run_read_query(cypher)
            except Exception as exc:
                error = str(exc)

        if error or not cypher:
            return RetrievalResult(
                strategy="Text2Cypher",
                answer=f"Text2Cypher route could not safely execute a query ({error or 'no query generated'}).",
                route_reason="Structured query route selected, but generation/execution failed.",
                benchmark_reference="Notebook: Text2Cypher best for exact structured lookups.",
                sources=[],
                cypher=cypher,
            )

        answer = self._summarize_rows(question, cypher, rows)
        return RetrievalResult(
            strategy="Text2Cypher",
            answer=answer,
            route_reason="Structured/analytical question routed to Text2Cypher.",
            benchmark_reference="Notebook: Text2Cypher excels on precise graph lookups.",
            sources=[{"product_code": None, "score": None, "role": "query_result_rows", "count": len(rows)}],
            cypher=cypher,
            context=f"Rows returned: {len(rows)}",
        )

    def _generate_cypher(self, question: str) -> str | None:
        heuristic = _heuristic_cypher(question)
        if heuristic:
            return heuristic

        if not self._llm.available:
            return None

        prompt = (
            "Generate a read-only Cypher query for Neo4j.\n"
            "Strict rules: only MATCH/OPTIONAL MATCH/WHERE/WITH/RETURN/ORDER BY/LIMIT.\n"
            "No CREATE, MERGE, DELETE, SET, CALL, APOC, LOAD CSV.\n"
            "Return JSON only: {\"cypher\":\"...\"}.\n"
            f"Schema:\n{GRAPH_SCHEMA}\n\n"
            f"Question: {question}"
        )

        parsed = self._llm.generate_json(prompt)
        if not parsed:
            return None
        cypher = str(parsed.get("cypher", "")).strip()
        if not cypher:
            return None
        return cypher

    def _summarize_rows(self, question: str, cypher: str, rows: list[dict[str, Any]]) -> str:
        preview = rows[:12]
        prompt = (
            "You are a corporate supply chain analyst. "
            "Explain the query result in concise business terms. "
            "If rows are empty, say that clearly.\n\n"
            f"Question: {question}\n"
            f"Cypher: {cypher}\n"
            f"Rows: {json.dumps(preview, default=str)}\n"
            "Answer:"
        )
        return self._llm.generate(prompt)


def _heuristic_cypher(question: str) -> str | None:
    q = question.lower().strip()

    plant_match = re.search(r"plant\s+(\d+)", q)
    if "assigned" in q and plant_match:
        plant_id = plant_match.group(1)
        return (
            "MATCH (p:Product)-[:ASSIGNED_TO_PLANT]->(pl:Plant) "
            f"WHERE pl.id = '{plant_id}' "
            "RETURN p.code AS product_code ORDER BY product_code"
        )

    group_match = re.search(r"group\s+([a-z])\b", q)
    if group_match and ("belong" in q or "products" in q or "list" in q):
        grp = group_match.group(1).upper()
        return (
            "MATCH (p:Product) "
            f"WHERE p.`group` = '{grp}' "
            "RETURN p.code AS product_code, p.subgroup AS subgroup ORDER BY product_code"
        )

    subgroup_match = re.search(r"subgroup\s+([a-z0-9_]+)", q)
    if subgroup_match and ("total" in q or "sum" in q) and "delivery" in q:
        subgroup = subgroup_match.group(1).upper()
        return (
            "MATCH (p:Product)-[:HAS_OBSERVATION]->(o:Observation) "
            f"WHERE p.subgroup = '{subgroup}' AND o.metric = 'delivery' AND o.unit_type = 'unit' "
            "RETURN round(sum(o.value), 2) AS total_delivery_units"
        )

    if "top" in q and "delivery" in q:
        return (
            "MATCH (p:Product)-[:HAS_OBSERVATION]->(o:Observation) "
            "WHERE o.metric = 'delivery' AND o.unit_type = 'unit' "
            "RETURN p.code AS product_code, round(sum(o.value), 2) AS delivery_units "
            "ORDER BY delivery_units DESC LIMIT 10"
        )

    return None
