"""Triage service for analyzing error logs and generating fixes.

This module coordinates the error triage workflow by extracting source context
from GitHub, analyzing stack traces with an LLM, and optionally creating pull
requests with suggested fixes.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.error_log import ErrorLog
from app.services.github_service import GitHubService, GitHubServiceError
from app.services.llm_provider import LLMProviderError, get_llm_provider

logger = logging.getLogger(__name__)

def run_triage(db: Session, error_log_id: str, open_pr: bool = False) -> ErrorLog:
    record = db.query(ErrorLog).filter(ErrorLog.id == error_log_id).first()
    if record is None:
        raise ValueError(f"No error log found with id={error_log_id}")
    record.status = "analyzing"
    db.commit()
    try:
        github = GitHubService()
        file_paths = github.extract_file_paths(record.stack_trace)
        source_context = github.fetch_source_context(file_paths)
        llm = get_llm_provider()
        result = llm.analyze(record.stack_trace, source_context)
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
                    body=
                    ("**Root cause:** {record.root_cause}\n\n"
                     "**Suggested fix:** {record.suggested_fix}\n\n"
                     "_Opened automatically by AutoTriage from error {record.id}._"
                    ),
                    branch_name=f"autotriage/fix-{record.id[:8]}",
                    patch_diff=record.patch_diff,
                )
                record.pull_request_url = pr_url
            except GitHubServiceError as exc:
                logger.warning("PR creation skipped: %s", exc)
                record.error_detail = f"Triaged, but PR creation failed: {exc}"
        
    except LLMProviderError as exc:
        record.status = "failed"
        record.error_detail = str(exc)
        logger.error("Triage failed for %s: %s", error_log_id, exc)
    except Exception as exc:  # noqa: BLE001
        record.status = "failed"
        record.error_detail = f"Unexpected error: {exc}"
        logger.exception("Unexpected triage failure for %s", error_log_id)
    finally:
        record.received_at = record.received_at or datetime.now(timezone.utc)
        db.commit()
        db.refresh(record)
    return record
