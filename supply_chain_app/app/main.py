from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.container import AppContainer

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = AppContainer(settings)
    container.startup()
    app.state.container = container
    yield
    container.shutdown()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(api_router, prefix=settings.api_prefix)

static_dir = Path(__file__).parent / "frontend" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/{path:path}", include_in_schema=False)
def spa_fallback(path: str) -> FileResponse:
    if path.startswith(settings.api_prefix.strip("/")):
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(static_dir / "index.html")
