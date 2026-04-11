from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_container
from app.services.container import AppContainer

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard")
def dashboard(container: AppContainer = Depends(get_container)) -> dict:
    return container.analytics.dashboard()


@router.get("/risk")
def risk(
    limit: int = Query(default=25, ge=1, le=200),
    container: AppContainer = Depends(get_container),
) -> list[dict]:
    return container.analytics.risk_monitor(limit=limit)


@router.get("/factory-floor")
def factory_floor(
    plant_limit: int = Query(default=12, ge=3, le=50),
    storage_limit: int = Query(default=12, ge=3, le=50),
    container: AppContainer = Depends(get_container),
) -> dict:
    return container.analytics.factory_floor(plant_limit=plant_limit, storage_limit=storage_limit)
