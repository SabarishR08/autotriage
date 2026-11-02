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
    """Ingest a structured error log and schedule background triage."""
    if not payload.dict(exclude_unset=True):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payload cannot be empty",
        )

    record = ErrorLog(
        service_name=payload.service_name,
        endpoint=payload.endpoint,
        stack_trace=payload.stack_trace,
        request_metadata=payload.request_metadata,
        occurred_at=payload.occurred_at,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    background_tasks.add_task(run_triage, db, record.id)
    return LogIngestResponse(
        id=record.id,
        status=record.status,
    )


@router.get(
    "/logs/{log_id}",
    response_model=TriageResult,
    dependencies=[Depends(_require_api_key)],
)
def get_log(log_id: int, db: Session = Depends(get_db)) -> TriageResult:
    """Retrieve a single error log and its triage status by ID."""
    record = db.query(ErrorLog).filter(ErrorLog.id == log_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Log not found")
    return record


@router.get(
    "/logs",
    response_model=TriageListResponse,
    dependencies=[Depends(_require_api_key)],
)
def list_logs(
    service_name: str | None = None,
    status: str | None = None,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> TriageListResponse:
    """List error logs with optional filtering by service_name and status."""
    query = db.query(ErrorLog)
    if service_name:
        query = query.filter(ErrorLog.service_name == service_name)
    if status:
        query = query.filter(ErrorLog.status == status)
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return TriageListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/logs/{log_id}/retriage",
    response_model=LogIngestResponse,
    dependencies=[Depends(_require_api_key)],
)
def retriage_log(
    log_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> LogIngestResponse:
    """Re-trigger triage processing for an existing log entry."""
    record = db.query(ErrorLog).filter(ErrorLog.id == log_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Log not found")
    record.status = "pending"
    db.commit()
    db.refresh(record)
    background_tasks.add_task(run_triage, db, record.id)
    return LogIngestResponse(id=record.id, status=record.status)
