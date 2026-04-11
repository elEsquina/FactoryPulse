from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)


class DataBootstrapRepository:
    def __init__(self, neo4j_repo: Neo4jRepository, processed_dir: Path, batch_size: int = 5000) -> None:
        self._neo4j = neo4j_repo
        self._processed_dir = processed_dir
        self._batch_size = batch_size

    def bootstrap_if_needed(self) -> bool:
        if self._neo4j.count_products() > 0:
            logger.info("Neo4j already contains products; bootstrap skipped.")
            return False

        if not self._processed_dir.exists():
            raise FileNotFoundError(f"Processed data directory missing: {self._processed_dir}")

        logger.info("Neo4j is empty. Bootstrapping graph from %s", self._processed_dir)
        products, product_plant, product_storage, observations = self._load_dataframes()

        self._create_constraints()
        self._load_batches(products, self._query_products, "products")
        self._load_batches(product_plant, self._query_product_plant, "product_plant")
        self._load_batches(product_storage, self._query_product_storage, "product_storage")
        self._load_batches(observations, self._query_observations, "observations")
        logger.info("Bootstrap complete.")
        return True

    def _load_dataframes(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        products = pd.read_csv(self._processed_dir / "products.csv")
        product_plant = pd.read_csv(self._processed_dir / "product_plant.csv")
        product_storage = pd.read_csv(self._processed_dir / "product_storage.csv")
        observations = pd.read_csv(self._processed_dir / "observations.csv")

        products["code"] = products["code"].astype(str).str.strip()
        products["group"] = products["group"].astype(str).str.strip()
        products["subgroup"] = products["subgroup"].astype(str).str.strip()
        products = products.drop_duplicates(subset=["code"])

        product_plant["product_code"] = product_plant["product_code"].astype(str).str.strip()
        product_plant["plant_id"] = pd.to_numeric(product_plant["plant_id"], errors="coerce").astype("Int64")
        product_plant = product_plant.dropna().drop_duplicates()
        product_plant["plant_id"] = product_plant["plant_id"].astype(int).astype(str)

        product_storage["product_code"] = product_storage["product_code"].astype(str).str.strip()
        product_storage["storage_id"] = pd.to_numeric(product_storage["storage_id"], errors="coerce").astype("Int64")
        product_storage = product_storage.dropna().drop_duplicates()
        product_storage["storage_id"] = product_storage["storage_id"].astype(int).astype(str)

        observations["product_code"] = observations["product_code"].astype(str).str.strip()
        observations["metric"] = observations["metric"].astype(str).str.strip()
        observations["unit_type"] = observations["unit_type"].astype(str).str.strip()
        observations["date"] = pd.to_datetime(observations["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        observations["value"] = pd.to_numeric(observations["value"], errors="coerce")
        observations = observations.dropna(subset=["obs_key", "product_code", "date", "metric", "unit_type", "value"])
        observations = observations.drop_duplicates(subset=["obs_key"])

        return products, product_plant, product_storage, observations

    def _create_constraints(self) -> None:
        statements = [
            "CREATE CONSTRAINT product_code_unique IF NOT EXISTS FOR (p:Product) REQUIRE p.code IS UNIQUE",
            "CREATE CONSTRAINT plant_id_unique IF NOT EXISTS FOR (p:Plant) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT storage_id_unique IF NOT EXISTS FOR (s:Storage) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT observation_key_unique IF NOT EXISTS FOR (o:Observation) REQUIRE o.obs_key IS UNIQUE",
            "CREATE INDEX observation_date_idx IF NOT EXISTS FOR (o:Observation) ON (o.date)",
        ]
        for statement in statements:
            self._neo4j.execute_statement(statement)

    @property
    def _query_products(self) -> str:
        return """
        UNWIND $rows AS row
        MERGE (p:Product {code: row.code})
        SET p.`group` = row.group,
            p.subgroup = row.subgroup
        """

    @property
    def _query_product_plant(self) -> str:
        return """
        UNWIND $rows AS row
        MERGE (p:Product {code: row.product_code})
        MERGE (pl:Plant {id: row.plant_id})
        MERGE (p)-[:ASSIGNED_TO_PLANT]->(pl)
        """

    @property
    def _query_product_storage(self) -> str:
        return """
        UNWIND $rows AS row
        MERGE (p:Product {code: row.product_code})
        MERGE (st:Storage {id: row.storage_id})
        MERGE (p)-[:STORED_IN]->(st)
        """

    @property
    def _query_observations(self) -> str:
        return """
        UNWIND $rows AS row
        MERGE (p:Product {code: row.product_code})
        MERGE (o:Observation {obs_key: row.obs_key})
        SET o.date = date(row.date),
            o.metric = row.metric,
            o.unit_type = row.unit_type,
            o.value = toFloat(row.value)
        MERGE (p)-[:HAS_OBSERVATION]->(o)
        """

    def _load_batches(self, df: pd.DataFrame, query: str, label: str) -> None:
        rows = df.where(pd.notnull(df), None).to_dict(orient="records")
        total = len(rows)
        if total == 0:
            logger.info("No %s rows to load.", label)
            return

        for i in range(0, total, self._batch_size):
            batch = rows[i : i + self._batch_size]
            self._neo4j.execute_write_batches(query, batch)
            logger.info("Loaded %s rows: %d/%d", label, min(i + len(batch), total), total)
