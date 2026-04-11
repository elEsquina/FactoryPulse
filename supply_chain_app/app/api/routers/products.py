from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_container
from app.services.container import AppContainer

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
def list_products(
    group: str | None = Query(default=None, min_length=1, max_length=2),
    limit: int = Query(default=100, ge=1, le=500),
    container: AppContainer = Depends(get_container),
) -> list[dict]:
    group_val = group.upper() if group else None
    return container.neo4j.list_products(group=group_val, limit=limit)


@router.get("/{code}")
def product_detail(code: str, container: AppContainer = Depends(get_container)) -> dict:
    payload = container.neo4j.get_product_detail(code.upper())
    if not payload:
        raise HTTPException(status_code=404, detail=f"Product '{code}' not found")
    return payload
