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


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    Dependency: enforce X-API-Key when AUTOTRIAGE_API_KEY is configured.
    If the env var is unset the endpoint is open (dev/internal mode).
    """
    expected = get_settings().AUTOTRIAGE_API_KEY
    if not expected:
        return  # auth disabled — open endpoint
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


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
):
    """
    Ingest a single structured API error log. Triage runs asynchronously in
    the background; poll GET /api/v1/logs/{id} for results.

    Requires X-API-Key header when AUTOTRIAGE_API_KEY env var is set.
    """
    record = ErrorLog(
        service_name=payload.service_name,
        endpoint=payload.endpoint,
        stack_trace=payload.stack_trace,
        request_metadata=payload.request_metadata,
        occurred_at=payload.occurred_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    background_tasks.add_task(run_triage, db, record.id)

    return LogIngestResponse(
        id=record.id,
        status=record.status,
        message="Log ingested. Triage is running in the background.",
    )


@router.get("/logs/{log_id}", response_model=TriageResult)
def get_log(log_id: str, db: Session = Depends(get_db)):
    record = db.query(ErrorLog).filter(ErrorLog.id == log_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Error log not found")
    return record


@router.get("/logs", response_model=TriageListResponse)
def list_logs(
    status: str | None = None,
    service: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List logs with optional filters for status and service name."""
    query = db.query(ErrorLog)
    if status:
        query = query.filter(ErrorLog.status == status)
    if service:
        query = query.filter(ErrorLog.service_name == service)
    total = query.count()
    items = query.order_by(ErrorLog.received_at.desc()).offset(offset).limit(limit).all()
    return TriageListResponse(total=total, items=items)


@router.post("/logs/{log_id}/retriage", response_model=TriageResult)
def retriage_log(log_id: str, open_pr: bool = False, db: Session = Depends(get_db)):
    """Re-run triage synchronously for a given log. Pass ?open_pr=true to create a PR."""
    try:
        record = run_triage(db, log_id, open_pr=open_pr)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record
