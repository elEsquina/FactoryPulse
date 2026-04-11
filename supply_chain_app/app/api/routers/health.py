from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.api.schemas.dashboard import HealthResponse
from app.services.container import AppContainer

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def health(container: AppContainer = Depends(get_container)) -> HealthResponse:
    h = container.health()
    status = "ok" if h["neo4j"] and h["embeddings_ready"] else "degraded"
    return HealthResponse(status=status, **h)
