"""
Orchestrates the full triage pipeline for a single error log:

  1. Extract candidate source file paths from the stack trace.
  2. Fetch that source context from GitHub (if configured).
  3. Send stack trace + context to the LLM for root-cause analysis.
  4. Persist the result. Optionally open a pull request.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.error_log import ErrorLog
from app.services.github_service import GitHubService, GitHubServiceError
from app.services.llm_provider import LLMProviderError, get_llm_provider

logger = logging.getLogger("autotriage.triage")


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
