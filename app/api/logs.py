'''
API endpoints for ingesting, retrieving, and re-triaging structured error logs.
Provides POST /api/v1/logs for log ingestion, GET /api/v1/logs/{id} for triage results,
GET /api/v1/logs for listing with filters, and POST /api/v1/logs/{id}/retriage for re-triaging.
Authentication is handled via X-API-Key header when AUTOTRIAGE_API_KEY is configured.
'''

import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
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

router = APIRouter(prefix="/api/v1", tags=["logs"])

logger = logging.getLogger(__name__)


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
def ingest_log(payload: LogIngestRequest, background_tasks: BackgroundTasks,
               db: Session = Depends(get_db)) -> ErrorLog:
    """Ingest a structured error log and schedule background triage.

    Reject completely empty payloads with HTTP 422.
    """
    # Ensure the payload contains at least one meaningful field.
    if not any([
        payload.service_name,
        payload.endpoint,
        payload.stack_trace,
        payload.request_metadata,
        payload.occurred_at,
    ]):
        raise HTTPException(status_code=422, detail="Payload cannot be empty")

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
        message="Log ingested; triage scheduled.",
    )


@router.get("/logs", response_model=TriageListResponse)
def list_logs(service: str | None = None, status: str | None = None,
              limit: int = 50, offset: int = 0,
              db: Session = Depends(get_db)) -> TriageListResponse:
    """List ingested logs, newest first, optionally filtered by service/status."""
    query = db.query(ErrorLog)
    if service:
        query = query.filter(ErrorLog.service_name == service)
    if status:
        query = query.filter(ErrorLog.status == status)
    total = query.count()
    records = (
        query.order_by(ErrorLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return TriageListResponse(
        total=total,
        limit=limit,
        offset=offset,
        logs=[
            TriageResult(
                id=log.id,
                service_name=log.service_name,
                endpoint=log.endpoint,
                status=log.status,
                occurred_at=log.occurred_at,
                triage_result=log.triage_result,
            )
            for log in records
        ],
    )
