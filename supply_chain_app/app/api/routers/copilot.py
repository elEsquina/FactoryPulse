from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.api.schemas.copilot import CopilotQueryRequest, CopilotQueryResponse
from app.services.container import AppContainer

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/query", response_model=CopilotQueryResponse)
def copilot_query(
    body: CopilotQueryRequest,
    container: AppContainer = Depends(get_container),
) -> CopilotQueryResponse:
    payload = container.copilot.ask(body.question)
    return CopilotQueryResponse(**payload)
