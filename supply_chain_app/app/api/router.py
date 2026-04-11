from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.analytics import router as analytics_router
from app.api.routers.benchmark import router as benchmark_router
from app.api.routers.copilot import router as copilot_router
from app.api.routers.health import router as health_router
from app.api.routers.products import router as products_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(benchmark_router)
api_router.include_router(analytics_router)
api_router.include_router(products_router)
api_router.include_router(copilot_router)
