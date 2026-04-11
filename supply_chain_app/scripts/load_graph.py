from __future__ import annotations

from app.core.config import get_settings
from app.repositories.data_bootstrap_repository import DataBootstrapRepository
from app.repositories.neo4j_repository import Neo4jRepository


def main() -> None:
    settings = get_settings()
    repo = Neo4jRepository(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    try:
        loader = DataBootstrapRepository(repo, settings.processed_data_dir_path, settings.bootstrap_batch_size)
        loader.bootstrap_if_needed()
    finally:
        repo.close()


if __name__ == "__main__":
    main()
