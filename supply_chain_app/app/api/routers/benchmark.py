from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.services.container import AppContainer

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


@router.get("/strategy")
def strategy(container: AppContainer = Depends(get_container)) -> dict:
    return container.benchmark_strategy()
