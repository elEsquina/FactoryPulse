from __future__ import annotations

import logging
from typing import Any

from neo4j import GraphDatabase

from app.domain.models import ProductProfile

logger = logging.getLogger(__name__)


class Neo4jRepository:
    def __init__(self, uri: str, user: str, password: str, database: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def ping(self) -> bool:
        try:
            with self._driver.session(database=self._database) as session:
                value = session.run("RETURN 1 AS ok").single()
            return bool(value and value.get("ok") == 1)
        except Exception:
            return False

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._driver.session(database=self._database) as session:
            records = session.run(cypher, params or {})
            return [record.data() for record in records]

    def execute_write_batches(self, cypher: str, rows: list[dict[str, Any]]) -> None:
        with self._driver.session(database=self._database) as session:
            session.run(cypher, rows=rows).consume()

    def execute_statement(self, cypher: str) -> None:
        with self._driver.session(database=self._database) as session:
            session.run(cypher).consume()

    def count_products(self) -> int:
        rows = self.query("MATCH (p:Product) RETURN count(p) AS count")
        return int(rows[0]["count"]) if rows else 0

    def fetch_product_profiles(self) -> list[ProductProfile]:
        rows = self.query(
            """
            MATCH (p:Product)
            OPTIONAL MATCH (p)-[:ASSIGNED_TO_PLANT]->(pl:Plant)
            OPTIONAL MATCH (p)-[:STORED_IN]->(st:Storage)
            OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
            RETURN
                p.code AS code,
                p.`group` AS grp,
                p.subgroup AS subgroup,
                collect(DISTINCT pl.id) AS plants,
                collect(DISTINCT st.id) AS storages,
                avg(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END) AS avg_delivery_unit,
                avg(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END) AS avg_production_unit,
                avg(CASE WHEN o.metric = 'sales_order' AND o.unit_type = 'unit' THEN o.value END) AS avg_sales_order_unit,
                sum(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END) AS total_delivery_unit,
                sum(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END) AS total_production_unit,
                count(o) AS observation_count
            ORDER BY code
            """
        )

        result: list[ProductProfile] = []
        for row in rows:
            result.append(
                ProductProfile(
                    code=row.get("code", ""),
                    group=row.get("grp") or "?",
                    subgroup=row.get("subgroup") or "?",
                    plants=[str(x) for x in row.get("plants", []) if x is not None],
                    storages=[str(x) for x in row.get("storages", []) if x is not None],
                    avg_delivery_unit=_to_float(row.get("avg_delivery_unit")),
                    avg_production_unit=_to_float(row.get("avg_production_unit")),
                    avg_sales_order_unit=_to_float(row.get("avg_sales_order_unit")),
                    total_delivery_unit=_to_float(row.get("total_delivery_unit")),
                    total_production_unit=_to_float(row.get("total_production_unit")),
                    observation_count=int(row.get("observation_count") or 0),
                )
            )
        return result

    def get_dashboard_metrics(self) -> dict[str, Any]:
        kpi = self.query(
            """
            MATCH (p:Product)
            WITH count(p) AS products
            MATCH (pl:Plant)
            WITH products, count(pl) AS plants
            MATCH (st:Storage)
            WITH products, plants, count(st) AS storages
            MATCH (o:Observation)
            RETURN products, plants, storages, count(o) AS observations
            """
        )[0]

        group_breakdown = self.query(
            """
            MATCH (p:Product)
            RETURN p.`group` AS grp, count(*) AS count
            ORDER BY count DESC
            """
        )

        top_delivery = self.query(
            """
            MATCH (p:Product)-[:HAS_OBSERVATION]->(o:Observation)
            WHERE o.metric = 'delivery' AND o.unit_type = 'unit'
            RETURN p.code AS code, sum(o.value) AS delivery_units
            ORDER BY delivery_units DESC
            LIMIT 8
            """
        )

        monthly_flow = self.query(
            """
            MATCH (:Product)-[:HAS_OBSERVATION]->(o:Observation)
            WHERE o.metric IN ['delivery', 'production'] AND o.unit_type = 'unit'
            RETURN toString(o.date) AS date, o.metric AS metric, sum(o.value) AS total
            ORDER BY date ASC, metric ASC
            """
        )

        return {
            "kpi": {
                "products": int(kpi.get("products", 0)),
                "plants": int(kpi.get("plants", 0)),
                "storages": int(kpi.get("storages", 0)),
                "observations": int(kpi.get("observations", 0)),
            },
            "groups": [
                {"group": row.get("grp"), "count": int(row.get("count", 0))} for row in group_breakdown
            ],
            "top_delivery": [
                {
                    "code": row.get("code"),
                    "delivery_units": round(_to_float(row.get("delivery_units")) or 0.0, 2),
                }
                for row in top_delivery
            ],
            "monthly_flow": [
                {
                    "date": row.get("date"),
                    "metric": row.get("metric"),
                    "total": round(_to_float(row.get("total")) or 0.0, 2),
                }
                for row in monthly_flow
            ],
        }

    def get_risk_products(self, limit: int = 25) -> list[dict[str, Any]]:
        rows = self.query(
            """
            MATCH (p:Product)-[:HAS_OBSERVATION]->(o:Observation)
            WITH
                p,
                avg(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END) AS delivery_avg,
                avg(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END) AS production_avg,
                avg(CASE WHEN o.metric = 'sales_order' AND o.unit_type = 'unit' THEN o.value END) AS sales_order_avg
            WITH
                p,
                coalesce(delivery_avg, 0.0) AS delivery_avg,
                coalesce(production_avg, 0.0) AS production_avg,
                coalesce(sales_order_avg, 0.0) AS sales_order_avg,
                CASE
                    WHEN coalesce(production_avg, 0.0) <= 0 THEN 0.0
                    ELSE coalesce(delivery_avg, 0.0) / production_avg
                END AS fulfillment_ratio
            WHERE production_avg > 0 OR sales_order_avg > 0
            RETURN
                p.code AS code,
                p.`group` AS grp,
                p.subgroup AS subgroup,
                round(delivery_avg, 2) AS delivery_avg,
                round(production_avg, 2) AS production_avg,
                round(sales_order_avg, 2) AS sales_order_avg,
                round(fulfillment_ratio, 4) AS fulfillment_ratio,
                CASE
                    WHEN fulfillment_ratio < 0.6 THEN 'HIGH'
                    WHEN fulfillment_ratio < 0.85 THEN 'MEDIUM'
                    ELSE 'LOW'
                END AS risk_level
            ORDER BY fulfillment_ratio ASC, sales_order_avg DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )
        return rows

    def get_factory_floor_metrics(self, plant_limit: int = 12, storage_limit: int = 12) -> dict[str, Any]:
        plant_load = self.query(
            """
            MATCH (pl:Plant)<-[:ASSIGNED_TO_PLANT]-(p:Product)
            OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
            WITH
                pl,
                count(DISTINCT p) AS assigned_products,
                avg(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END) AS avg_production,
                avg(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END) AS avg_delivery
            RETURN
                pl.id AS plant_id,
                assigned_products,
                round(coalesce(avg_production, 0.0), 2) AS avg_production,
                round(coalesce(avg_delivery, 0.0), 2) AS avg_delivery,
                round(
                    CASE
                        WHEN coalesce(avg_production, 0.0) <= 0 THEN 0.0
                        ELSE coalesce(avg_delivery, 0.0) / avg_production
                    END,
                    4
                ) AS delivery_production_ratio
            ORDER BY assigned_products DESC, plant_id ASC
            LIMIT $limit
            """,
            {"limit": plant_limit},
        )

        storage_load = self.query(
            """
            MATCH (st:Storage)<-[:STORED_IN]-(p:Product)
            RETURN
                st.id AS storage_id,
                count(DISTINCT p) AS products
            ORDER BY products DESC, storage_id ASC
            LIMIT $limit
            """,
            {"limit": storage_limit},
        )

        relation_density = self.query(
            """
            MATCH (p:Product)
            OPTIONAL MATCH (p)-[:ASSIGNED_TO_PLANT]->(pl:Plant)
            OPTIONAL MATCH (p)-[:STORED_IN]->(st:Storage)
            RETURN
                count(DISTINCT p) AS products,
                count(DISTINCT pl) AS connected_plants,
                count(DISTINCT st) AS connected_storages,
                count(pl) AS plant_links,
                count(st) AS storage_links
            """
        )

        relation = relation_density[0] if relation_density else {}
        return {
            "plant_load": plant_load,
            "storage_load": storage_load,
            "network_density": {
                "products": int(relation.get("products", 0)),
                "connected_plants": int(relation.get("connected_plants", 0)),
                "connected_storages": int(relation.get("connected_storages", 0)),
                "plant_links": int(relation.get("plant_links", 0)),
                "storage_links": int(relation.get("storage_links", 0)),
            },
        }

    def list_products(self, group: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = """
        MATCH (p:Product)
        WHERE $group IS NULL OR p.`group` = $group
        OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
        RETURN
            p.code AS code,
            p.`group` AS grp,
            p.subgroup AS subgroup,
            round(sum(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END), 2) AS total_delivery,
            round(sum(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END), 2) AS total_production,
            round(avg(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END), 2) AS avg_delivery,
            round(avg(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END), 2) AS avg_production
        ORDER BY p.code
        LIMIT $limit
        """
        return self.query(query, {"group": group, "limit": limit})

    def get_product_detail(self, code: str) -> dict[str, Any] | None:
        rows = self.query(
            """
            MATCH (p:Product {code: $code})
            OPTIONAL MATCH (p)-[:ASSIGNED_TO_PLANT]->(pl:Plant)
            OPTIONAL MATCH (p)-[:STORED_IN]->(st:Storage)
            OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
            WITH p, collect(DISTINCT pl.id) AS plants, collect(DISTINCT st.id) AS storages, o
            RETURN
                p.code AS code,
                p.`group` AS grp,
                p.subgroup AS subgroup,
                plants,
                storages,
                round(sum(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END), 2) AS total_delivery,
                round(sum(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END), 2) AS total_production,
                round(avg(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END), 2) AS avg_delivery,
                round(avg(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END), 2) AS avg_production,
                round(avg(CASE WHEN o.metric = 'sales_order' AND o.unit_type = 'unit' THEN o.value END), 2) AS avg_sales_order,
                count(o) AS observation_count
            """,
            {"code": code},
        )
        if not rows:
            return None

        recent_observations = self.query(
            """
            MATCH (:Product {code: $code})-[:HAS_OBSERVATION]->(o:Observation)
            RETURN toString(o.date) AS date, o.metric AS metric, o.unit_type AS unit_type, round(o.value, 3) AS value
            ORDER BY o.date DESC
            LIMIT 24
            """,
            {"code": code},
        )

        similar_context = self.query(
            """
            MATCH (p:Product {code: $code})-[:ASSIGNED_TO_PLANT|STORED_IN]->(n)<-[:ASSIGNED_TO_PLANT|STORED_IN]-(peer:Product)
            WHERE peer.code <> $code
            RETURN peer.code AS peer_code, count(*) AS shared_links
            ORDER BY shared_links DESC, peer_code ASC
            LIMIT 10
            """,
            {"code": code},
        )

        payload = rows[0]
        payload["recent_observations"] = recent_observations
        payload["related_products"] = similar_context
        return payload

    def get_subgraph_context(self, seed_codes: list[str], peer_limit: int) -> dict[str, Any]:
        if not seed_codes:
            return {"seeds": [], "metrics": []}

        seed_rows = self.query(
            """
            MATCH (seed:Product)
            WHERE seed.code IN $seed_codes
            OPTIONAL MATCH (seed)-[:ASSIGNED_TO_PLANT]->(pl:Plant)
            OPTIONAL MATCH (seed)-[:STORED_IN]->(st:Storage)
            OPTIONAL MATCH (seed)-[:ASSIGNED_TO_PLANT|STORED_IN]->(loc)<-[:ASSIGNED_TO_PLANT|STORED_IN]-(peer:Product)
            WHERE peer.code <> seed.code
            RETURN
                seed.code AS seed_code,
                seed.`group` AS grp,
                seed.subgroup AS subgroup,
                collect(DISTINCT pl.id) AS plants,
                collect(DISTINCT st.id) AS storages,
                collect(DISTINCT peer.code)[..$peer_limit] AS peers
            """,
            {"seed_codes": seed_codes, "peer_limit": peer_limit},
        )

        all_codes = set(seed_codes)
        for row in seed_rows:
            all_codes.update(code for code in row.get("peers", []) if code)

        metric_rows = self.query(
            """
            MATCH (p:Product)
            WHERE p.code IN $codes
            OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
            RETURN
                p.code AS code,
                p.`group` AS grp,
                p.subgroup AS subgroup,
                round(avg(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END), 2) AS avg_delivery,
                round(avg(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END), 2) AS avg_production,
                round(sum(CASE WHEN o.metric = 'delivery' AND o.unit_type = 'unit' THEN o.value END), 2) AS total_delivery,
                round(sum(CASE WHEN o.metric = 'production' AND o.unit_type = 'unit' THEN o.value END), 2) AS total_production
            """,
            {"codes": sorted(all_codes)},
        )

        return {"seeds": seed_rows, "metrics": metric_rows}

    def run_read_query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        lowered = cypher.lower()
        blocked = [
            "create ",
            "merge ",
            "delete ",
            "set ",
            "remove ",
            "drop ",
            "call ",
            "apoc.",
            "load csv",
            "foreach ",
            "dbms.",
        ]
        if any(token in lowered for token in blocked):
            raise ValueError("Only read-only Cypher queries are permitted.")
        if "return" not in lowered:
            raise ValueError("Generated Cypher must contain RETURN.")
        return self.query(cypher, params)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
