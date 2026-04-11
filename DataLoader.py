from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pandas as pd
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable


PROCESSED_DIR = Path("DataExploration/Processed")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "5000"))
CLEAR_EXISTING = os.getenv("CLEAR_EXISTING", "false").lower() in {"1", "true", "yes"}


def chunk_rows(df: pd.DataFrame, batch_size: int) -> Iterator[list[dict]]:
    rows = df.where(pd.notna(df), None).to_dict(orient="records")
    for i in range(0, len(rows), batch_size):
        yield rows[i : i + batch_size]


def load_dataframes() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    products = pd.read_csv(PROCESSED_DIR / "products.csv")
    product_plant = pd.read_csv(PROCESSED_DIR / "product_plant.csv")
    product_storage = pd.read_csv(PROCESSED_DIR / "product_storage.csv")
    observations = pd.read_csv(PROCESSED_DIR / "observations.csv")

    products["code"] = products["code"].astype(str).str.strip()
    products["group"] = products["group"].astype("string").str.strip()
    products["subgroup"] = products["subgroup"].astype("string").str.strip()
    products = products.drop_duplicates(subset=["code"]).reset_index(drop=True)

    product_plant["product_code"] = product_plant["product_code"].astype(str).str.strip()
    product_plant["plant_id"] = pd.to_numeric(product_plant["plant_id"], errors="coerce")
    product_plant = product_plant.dropna(subset=["product_code", "plant_id"])
    product_plant["plant_id"] = product_plant["plant_id"].astype(int).astype(str)
    product_plant = product_plant.drop_duplicates().reset_index(drop=True)

    product_storage["product_code"] = product_storage["product_code"].astype(str).str.strip()
    product_storage["storage_id"] = pd.to_numeric(product_storage["storage_id"], errors="coerce")
    product_storage = product_storage.dropna(subset=["product_code", "storage_id"])
    product_storage["storage_id"] = product_storage["storage_id"].astype(int).astype(str)
    product_storage = product_storage.drop_duplicates().reset_index(drop=True)

    observations["product_code"] = observations["product_code"].astype(str).str.strip()
    observations["date"] = pd.to_datetime(observations["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    observations["metric"] = observations["metric"].astype(str).str.strip()
    observations["unit_type"] = observations["unit_type"].astype(str).str.strip()
    observations["value"] = pd.to_numeric(observations["value"], errors="coerce")
    observations = observations.dropna(subset=["obs_key", "product_code", "date", "metric", "unit_type"])
    observations = observations.drop_duplicates(subset=["obs_key"]).reset_index(drop=True)

    return products, product_plant, product_storage, observations


def execute_constraints(session) -> None:
    constraints = [
        "CREATE CONSTRAINT product_code_unique IF NOT EXISTS FOR (p:Product) REQUIRE p.code IS UNIQUE",
        "CREATE CONSTRAINT plant_id_unique IF NOT EXISTS FOR (p:Plant) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT storage_id_unique IF NOT EXISTS FOR (s:Storage) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT observation_key_unique IF NOT EXISTS FOR (o:Observation) REQUIRE o.obs_key IS UNIQUE",
        "CREATE INDEX observation_date_idx IF NOT EXISTS FOR (o:Observation) ON (o.date)",
    ]
    for query in constraints:
        session.run(query).consume()


def load_batches(session, df: pd.DataFrame, query: str, label: str) -> None:
    total = len(df)
    if total == 0:
        print(f"{label}: 0 rows to load")
        return

    loaded = 0
    for rows in chunk_rows(df, BATCH_SIZE):
        session.run(query, rows=rows).consume()
        loaded += len(rows)
        print(f"{label}: {loaded}/{total}")


def print_graph_counts(session) -> None:
    checks = {
        "Product nodes": "MATCH (n:Product) RETURN count(n) AS c",
        "Plant nodes": "MATCH (n:Plant) RETURN count(n) AS c",
        "Storage nodes": "MATCH (n:Storage) RETURN count(n) AS c",
        "Observation nodes": "MATCH (n:Observation) RETURN count(n) AS c",
        "Product->Plant rels": "MATCH (:Product)-[r:ASSIGNED_TO_PLANT]->(:Plant) RETURN count(r) AS c",
        "Product->Storage rels": "MATCH (:Product)-[r:STORED_IN]->(:Storage) RETURN count(r) AS c",
        "Product->Observation rels": "MATCH (:Product)-[r:HAS_OBSERVATION]->(:Observation) RETURN count(r) AS c",
    }
    print("\nGraph counts:")
    for name, query in checks.items():
        count = session.run(query).single()["c"]
        print(f"- {name}: {count}")


def main() -> None:
    if not PROCESSED_DIR.exists():
        raise FileNotFoundError(f"Processed directory not found: {PROCESSED_DIR.resolve()}")

    products, product_plant, product_storage, observations = load_dataframes()
    print(f"products        : {products.shape}")
    print(f"product_plant   : {product_plant.shape}")
    print(f"product_storage : {product_storage.shape}")
    print(f"observations    : {observations.shape}")

    q_products = """
    UNWIND $rows AS row
    MERGE (p:Product {code: row.code})
    SET p.`group` = row.group,
        p.subgroup = row.subgroup
    """

    q_product_plant = """
    UNWIND $rows AS row
    MERGE (p:Product {code: row.product_code})
    MERGE (pl:Plant {id: row.plant_id})
    MERGE (p)-[:ASSIGNED_TO_PLANT]->(pl)
    """

    q_product_storage = """
    UNWIND $rows AS row
    MERGE (p:Product {code: row.product_code})
    MERGE (s:Storage {id: row.storage_id})
    MERGE (p)-[:STORED_IN]->(s)
    """

    q_observations = """
    UNWIND $rows AS row
    MERGE (p:Product {code: row.product_code})
    MERGE (o:Observation {obs_key: row.obs_key})
    SET o.date = date(row.date),
        o.metric = row.metric,
        o.unit_type = row.unit_type,
        o.value = toFloat(row.value)
    MERGE (p)-[:HAS_OBSERVATION]->(o)
    """

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        try:
            with driver.session() as session:
                print("Connected:", session.run("RETURN 1 AS ok").single()["ok"] == 1)
                execute_constraints(session)

                if CLEAR_EXISTING:
                    print("CLEAR_EXISTING=true -> deleting existing graph data...")
                    session.run("MATCH (n) DETACH DELETE n").consume()
                    execute_constraints(session)

                load_batches(session, products, q_products, "Products")
                load_batches(session, product_plant, q_product_plant, "Product-Plant")
                load_batches(session, product_storage, q_product_storage, "Product-Storage")
                load_batches(session, observations, q_observations, "Observations")

                print_graph_counts(session)
        except ServiceUnavailable as exc:
            raise RuntimeError(
                "Cannot connect to Neo4j. Start it first (e.g. `docker compose up -d neo4j`) "
                f"and verify URI/user/password. Current URI: {NEO4J_URI}"
            ) from exc
    finally:
        driver.close()


if __name__ == "__main__":
    main()
