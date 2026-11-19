"""
API endpoints for ingesting, retrieving, and re-triaging structured error logs.
Provides POST /api/v1/logs for log ingestion, GET /api/v1/logs/{id} for triage results,
GET /api/v1/logs for listing with filters, and POST /api/v1/logs/{id}/retriage for re-triaging.
Authentication is handled via X-API-Key header when AUTOTRIAGE_API_KEY is configured.
"""

import logging
import time
from typing import Callable

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


@router.post(
    "/logs",
    response_model=LogIngestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_api_key)],
)
def ingest_log(
    payload: LogIngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> LogIngestResponse:
    """Ingest a structured error log and trigger background triage."""
    log_entry = ErrorLog(
        service=payload.service,
        environment=payload.environment,
        error_message=payload.error_message,
        stack_trace=payload.stack_trace,
        severity=payload.severity,
        metadata_json=payload.metadata_json,
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)

    background_tasks.add_task(run_triage, log_entry.id)
    return LogIngestResponse(
        id=log_entry.id,
        status="queued",
        message="Log ingested and triage queued",
    )


@router.get(
    "/logs/{log_id}",
    response_model=TriageResult,
    dependencies=[Depends(_require_api_key)],
)
def get_log(log_id: str, db: Session = Depends(get_db)) -> ErrorLog:
    """Retrieve an error log and its triage results by ID."""
    log_entry = db.query(ErrorLog).filter(ErrorLog.id == log_id).first()
    if not log_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log not found",
        )
    return log_entry


@router.get(
    "/logs",
    response_model=TriageListResponse,
    dependencies=[Depends(_require_api_key)],
)
def list_logs(
    service: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TriageListResponse:
    """List error logs with optional filtering and pagination."""
    query = db.query(ErrorLog)
    if service:
        query = query.filter(ErrorLog.service == service)
    if environment:
        query = query.filter(ErrorLog.environment == environment)
    if severity:
        query = query.filter(ErrorLog.severity == severity)
    if status_filter:
        query = query.filter(ErrorLog.triage_status == status_filter)

    total = query.count()
    logs = (
        query.order_by(ErrorLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return TriageListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[TriageResult.model_validate(l) for l in logs],
    )


@router.post(
    "/logs/{log_id}/retriage",
    response_model=LogIngestResponse,
    dependencies=[Depends(_require_api_key)],
)
def retriage_log(
    log_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> LogIngestResponse:
    """Re-trigger automated triage for an existing error log."""
    log_entry = db.query(ErrorLog).filter(ErrorLog.id == log_id).first()
    if not log_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log not found",
        )

    log_entry.triage_status = "pending"
    db.commit()

    background_tasks.add_task(run_triage, log_entry.id)
    return LogIngestResponse(
        id=log_entry.id,
        status="queued",
        message="Retriage queued",
    )
