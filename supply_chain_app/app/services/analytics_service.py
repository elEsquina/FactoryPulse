from __future__ import annotations

from app.repositories.neo4j_repository import Neo4jRepository


class AnalyticsService:
    def __init__(self, neo4j: Neo4jRepository) -> None:
        self._neo4j = neo4j

    def dashboard(self) -> dict:
        payload = self._neo4j.get_dashboard_metrics()
        risk = self._neo4j.get_risk_products(limit=100)
        payload["kpi"]["at_risk_products"] = sum(1 for r in risk if r.get("risk_level") in {"HIGH", "MEDIUM"})
        return payload

    def risk_monitor(self, limit: int = 25) -> list[dict]:
        return self._neo4j.get_risk_products(limit=limit)

    def factory_floor(self, plant_limit: int = 12, storage_limit: int = 12) -> dict:
        return self._neo4j.get_factory_floor_metrics(plant_limit=plant_limit, storage_limit=storage_limit)
