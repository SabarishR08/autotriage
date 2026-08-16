import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.types import JSON

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ErrorLog(Base):
    """A single ingested API error, plus the triage results once processed."""

    __tablename__ = "error_logs"

    id = Column(String, primary_key=True, default=_uuid)
    service_name = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    stack_trace = Column(Text, nullable=False)
    request_metadata = Column(JSON, nullable=True)
    occurred_at = Column(DateTime, nullable=False)
    received_at = Column(DateTime, default=_now)

    # Triage status: pending -> analyzing -> triaged | failed
    status = Column(String, default="pending")

    root_cause = Column(Text, nullable=True)
    affected_files = Column(JSON, nullable=True)
    confidence = Column(String, nullable=True)
    suggested_fix = Column(Text, nullable=True)
    patch_diff = Column(Text, nullable=True)
    pull_request_url = Column(String, nullable=True)
    error_detail = Column(Text, nullable=True)
