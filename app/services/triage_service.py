"""Triage service for analyzing error logs and generating fixes.

This module coordinates the error triage workflow by extracting source context
from GitHub, analyzing stack traces with an LLM, and optionally creating pull
requests with suggested fixes.
"""
import logging
from typing import Any, Dict, List, Union
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
        record.confidence = result.get("confidence")
        record.suggested_fix = result.get("suggested_fix")
        record.patch_diff = result.get("patch_diff")
        record.status = "triaged"
        
        if open_pr and record.patch_diff and github.is_configured:
            try:
                pr_url = github.open_pull_request(
                    title=f"AutoTriage fix: {record.service_name} — {record.endpoint}",
                    body=(
                        f"**Root cause:** {record.root_cause}\n\n"
                        f"**Suggested fix:** {record.suggested_fix}\n\n"
                        f"_Opened automatically by AutoTriage from error {record.id}._"
                    ),
                    branch_name=f"autotriage/fix-{record.id[:8]}",
                    patch_diff=record.patch_diff,
                )
                record.pull_request_url = pr_url
            except GitHubServiceError as exc:
                logger.warning(f"PR creation failed: {exc}")
    except (LLMProviderError, Exception) as exc:
        logger.error(f"Triage failed for error {error_log_id}: {exc}")
        record.status = "failed"
        db.commit()
        raise
    return record
