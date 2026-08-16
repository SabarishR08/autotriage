from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

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


@router.post("/logs", response_model=LogIngestResponse, status_code=201)
def ingest_log(
    payload: LogIngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Ingest a single structured API error log. Triage runs asynchronously in
    the background; poll GET /api/v1/logs/{id} for results.
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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(ErrorLog)
    if status:
        query = query.filter(ErrorLog.status == status)
    total = query.count()
    items = query.order_by(ErrorLog.received_at.desc()).offset(offset).limit(limit).all()
    return TriageListResponse(total=total, items=items)


@router.post("/logs/{log_id}/retriage", response_model=TriageResult)
def retriage_log(log_id: str, open_pr: bool = False, db: Session = Depends(get_db)):
    """Re-run triage synchronously for a given log — useful for demos/tests."""
    try:
        record = run_triage(db, log_id, open_pr=open_pr)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record
