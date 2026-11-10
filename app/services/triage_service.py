"""Triage service for analyzing error logs and generating fixes.

This module coordinates the error triage workflow by extracting source context
from GitHub, analyzing stack traces with an LLM, and optionally creating pull
requests with suggested fixes.
"""
import hashlib
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.error_log import ErrorLog
from app.services.github_service import GitHubService, GitHubServiceError
from app.services.llm_provider import LLMProviderError, get_llm_provider

logger = logging.getLogger(__name__)


def truncate_log(text: str, max_chars: int = 4000) -> str:
    """Truncate log text if it exceeds max_chars length."""
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars]


def stack_trace_hash(stack_trace: Optional[str]) -> str:
    """Generate a SHA-256 hash for a given stack trace string."""
    if not stack_trace:
        return ""
    return hashlib.sha256(stack_trace.strip().encode("utf-8")).hexdigest()


def deduplicate_errors(
    errors: List[Union[ErrorLog, Dict[str, Any]]],
    key_attr: str = "fingerprint",
) -> List[Union[ErrorLog, Dict[str, Any]]]:
    """Deduplicate error logs while preserving insertion order.

    Uses specified key_attr (default 'fingerprint') or falls back to error details.
    """
    seen = set()
    unique_errors = []
    for err in errors:
        if isinstance(err, dict):
            key = err.get(key_attr) or (
                err.get("service_name"),
                err.get("exception_type"),
                err.get("error_message"),
            )
        else:
            key = getattr(err, key_attr, None) or (
                getattr(err, "service_name", None),
                getattr(err, "exception_type", None),
                getattr(err, "error_message", None),
            )
        if key not in seen:
            seen.add(key)
            unique_errors.append(err)
    return unique_errors


def run_triage(db: Session, error_log_id: str, open_pr: bool = False) -> ErrorLog:
    record = db.query(ErrorLog).filter(ErrorLog.id == error_log_id).first()
    if record is None:
        raise ValueError(f"No error log found with id={error_log_id}")
    record.status = "analyzing"
    db.commit()
    try:
        github = GitHubService()
        stack_trace = truncate_log(record.stack_trace or "")
        file_paths = github.extract_file_paths(stack_trace)
        source_context = github.fetch_source_context(file_paths)
        llm = get_llm_provider()
        result = llm.analyze(stack_trace, source_context)
        record.root_cause = result.get("root_cause")
        record.affected_files = result.get("affected_files")
        record.suggested_fix = result.get("suggested_fix")
        record.status = "triaged"
        record.triaged_at = datetime.now(timezone.utc)
        if open_pr and record.suggested_fix and file_paths:
            try:
                pr_url = github.create_fix_pull_request(
                    file_paths=file_paths,
                    fix_code=record.suggested_fix,
                    issue_title=f"Fix: {record.exception_type} in {record.service_name}",
                    issue_body=f"Root cause: {record.root_cause}",
                )
                record.pr_url = pr_url
            except GitHubServiceError as err:
                logger.error("Failed to create PR: %s", err)
        db.commit()
    except Exception as err:
        db.rollback()
        record.status = "failed"
        db.commit()
        raise err
    return record
