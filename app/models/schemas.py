from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LogIngestRequest(BaseModel):
    """Structured error log submitted by a client service."""

    service_name: str = Field(..., examples=["checkout-api"])
    endpoint: str = Field(..., examples=["POST /v1/orders"])
    stack_trace: str = Field(..., min_length=1)
    occurred_at: datetime
    request_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional extra context: request payload, headers, user id, etc.",
    )


class LogIngestResponse(BaseModel):
    id: str
    status: str
    message: str


class TriageResult(BaseModel):
    id: str
    service_name: str
    endpoint: str
    status: str
    root_cause: str | None = None
    affected_files: list[str] | None = None
    confidence: str | None = None
    suggested_fix: str | None = None
    patch_diff: str | None = None
    pull_request_url: str | None = None
    error_detail: str | None = None
    occurred_at: datetime
    received_at: datetime

    model_config = {"from_attributes": True}


class TriageListResponse(BaseModel):
    total: int
    items: list[TriageResult]
