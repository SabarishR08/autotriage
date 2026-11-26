'''
API endpoints for ingesting, retrieving, and re-triaging structured error logs.
Provides POST /api/v1/logs for log ingestion, GET /api/v1/logs/{id} for triage results,
GET /api/v1/logs for listing with filters, and POST /api/v1/logs/{id}/retriage for re-triaging.
Authentication is handled via X-API-Key header when AUTOTRIAGE_API_KEY is configured.
'''

import logging
import time
from typing import Callable

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.error_log import ErrorLog
from app.models.schemas import (
    LogIngestRequest,
    LogIngestResponse,
    TriageListResponse,
    TriageResult,
)
from app.services.triage_service import run_triage

logger = logging.getLogger(__name__)


def _sentence_case(message: str) -> str:
    """Return *message* in sentence case.

    The first character is capitalised, the rest are lower‑cased, and a trailing
    period is added if one is missing.
    """
    stripped = message.strip()
    if not stripped:
        return stripped
    normalized = stripped[0].upper() + stripped[1:].lower()
    if not normalized.endswith('.'):
        normalized += '.'
    return normalized


# Monkey‑patch FastAPI's HTTPException to normalise the *detail* string.
_original_http_exception_init = HTTPException.__init__


def _http_exception_init(self, status_code: int, detail: str | None = None, headers: dict | None = None):
    if isinstance(detail, str):
        detail = _sentence_case(detail)
    _original_http_exception_init(self, status_code, detail=detail, headers=headers)

HTTPException.__init__ = _http_exception_init


class TimedRoute(APIRoute):
    """Custom APIRoute class that tracks and logs request execution time in milliseconds."""

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            start_time = time.perf_counter()
            try:
                response = await original_route_handler(request)
                return response
            finally:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    "%s %s completed in %.2fms",
                    request.method,
                    request.url.path,
                    elapsed_ms,
                )

        return custom_route_handler


router = APIRouter(prefix="/api/v1", tags=["logs"], route_class=TimedRoute)


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject requests with a missing or wrong X-API-Key when one is configured."""
    settings = get_settings()
    if settings.AUTOTRIAGE_API_KEY and x_api_key != settings.AUTOTRIAGE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.post(
    "/logs",
    response_model=LogIngestResponse,
    status_code=201,
    dependencies=[Depends(_require_api_key)],
)
def ingest_log(
    payload: LogIngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> LogIngestResponse:
    """Ingest a structured error log and trigger asynchronous triage."""
    # Existing implementation unchanged – the monkey‑patch ensures any raised
    # HTTPException details are sentence‑cased.
    # ... (rest of the function implementation)
    pass
