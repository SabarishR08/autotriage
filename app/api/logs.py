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
    """Ingest a structured error log and queue background triage analysis."""
    db_log = ErrorLog(
        service_name=payload.service_name,
        environment=payload.environment,
        error_message=payload.error_message,
        stack_trace=payload.stack_trace,
        metadata_json=payload.metadata,
        status="pending",
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)

    background_tasks.add_task(run_triage, db_log.id)

    return LogIngestResponse(
        id=db_log.id,
        status=db_log.status,
        message="Log ingested successfully",
    )


@router.get(
    "/logs/{log_id}",
    response_model=TriageResult,
    dependencies=[Depends(_require_api_key)],
)
def get_triage_result(
    log_id: int,
    db: Session = Depends(get_db),
) -> TriageResult:
    """Retrieve triage results for a specific error log."""
    log = db.query(ErrorLog).filter(ErrorLog.id == log_id).first()
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log not found",
        )
    return TriageResult(
        id=log.id,
        service_name=log.service_name,
        environment=log.environment,
        error_message=log.error_message,
        stack_trace=log.stack_trace,
        status=log.status,
        root_cause=log.root_cause,
        suggested_fix=log.suggested_fix,
        severity=log.severity,
        confidence_score=log.confidence_score,
        created_at=log.created_at,
        triaged_at=log.triaged_at,
    )


@router.get(
    "/logs",
    response_model=TriageListResponse,
    dependencies=[Depends(_require_api_key)],
)
def list_logs(
    service_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TriageListResponse:
    """List ingested logs with optional filtering by service name or status."""
    query = db.query(ErrorLog)
    if service_name:
        query = query.filter(ErrorLog.service_name == service_name)
    if status:
        query = query.filter(ErrorLog.status == status)

    total = query.count()
    logs = query.order_by(ErrorLog.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        TriageResult(
            id=log.id,
            service_name=log.service_name,
            environment=log.environment,
            error_message=log.error_message,
            stack_trace=log.stack_trace,
            status=log.status,
            root_cause=log.root_cause,
            suggested_fix=log.suggested_fix,
            severity=log.severity,
            confidence_score=log.confidence_score,
            created_at=log.created_at,
            triaged_at=log.triaged_at,
        )
        for log in logs
    ]

    return TriageListResponse(total=total, items=items)


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
    """Re-trigger automated triage analysis for an existing log."""
    log = db.query(ErrorLog).filter(ErrorLog.id == log_id).first()
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log not found",
        )

    log.status = "pending"
    db.commit()
    db.refresh(log)

    background_tasks.add_task(run_triage, log.id)

    return LogIngestResponse(
        id=log.id,
        status=log.status,
        message="Re-triage initiated successfully",
    )
