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
        source_context = ""
        for path in file_paths[:3]:
            try:
                content = github.get_file_content(path)
                if content:
                    source_context += f"--- {path} ---\n{truncate_log(content, 2000)}\n\n"
            except Exception as e:
                logger.warning(f"Could not fetch context for {path}: {e}")

        llm = get_llm_provider()
        analysis = llm.analyze_error(
            service_name=record.service_name,
            exception_type=record.exception_type,
            error_message=record.error_message,
            stack_trace=stack_trace,
            source_context=source_context,
        )

        record.root_cause = analysis.get("root_cause")
        record.suggested_fix = analysis.get("suggested_fix")
        record.confidence_score = analysis.get("confidence_score")
        record.status = "triaged"

        if open_pr and record.suggested_fix:
            try:
                pr_url = github.create_pull_request(
                    title=f"Fix: {record.exception_type} in {record.service_name}",
                    body=f"Automated fix suggestion for error log {record.id}.\n\nRoot Cause:\n{record.root_cause}",
                    patch=record.suggested_fix,
                )
                record.pr_url = pr_url
            except Exception as e:
                logger.error(f"Failed to create PR for error log {record.id}: {e}")

        db.commit()
    except Exception as e:
        logger.error(f"Error during triage for {error_log_id}: {e}")
        record.status = "failed"
        db.commit()
        raise

    return record
