# Supply Chain Intelligence Hub

FastAPI-based production-style application rebuilt from scratch around a benchmark-driven hybrid retrieval architecture.

## Why this architecture

`graphrag_benchmark.ipynb` outputs showed:

- Gemini RAG average score: **4.89/5**
- GraphRAG average score: **4.83/5**
- Text2Cypher average score: **3.67/5**

But each approach wins in different question classes. The app therefore uses intent routing:

- `Text2Cypher` for structured/analytical queries
- `GraphRAG` for relational reasoning/similarity
- `Semantic RAG` for open-ended narrative synthesis

## Folder structure

- `app/main.py`: FastAPI app and lifecycle
- `app/api/`: routers and schemas
- `app/core/`: config and logging
- `app/domain/`: domain entities
- `app/repositories/`: Neo4j and bootstrap repositories
- `app/services/llm_service.py`: LLM abstraction
- `app/services/embedding_service.py`: embedding + persistence
- `app/services/rag/`: GraphRAG, Semantic RAG, Text2Cypher, router
- `app/storage/embedding_store.py`: vector persistence layer
- `app/frontend/static/`: corporate web UI
- `scripts/load_graph.py`: explicit graph bootstrap script
- `runtime/`: persisted embeddings/cache (mounted in docker-compose)

## Run with Docker Compose

From project root:

```bash
docker compose up --build
```

Then open:

- App: `http://localhost:8000`
- Health: `http://localhost:8000/api/v1/health`
- Neo4j Browser: `http://localhost:7474`

## Notes

- Embeddings are persisted under `supply_chain_app/runtime/embeddings` and reused unless source fingerprint changes.
- If Neo4j has no product nodes and `AUTO_BOOTSTRAP_DATA=true`, the app imports data from `/app/data/processed`.
- Without `GEMINI_API_KEY`, the app still runs with deterministic offline fallback logic.
