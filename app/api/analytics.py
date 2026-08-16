"""
Analytics endpoint — aggregate failure patterns across all ingested logs.

All aggregation is done in Python over the SQLite dataset rather than via
raw SQL so the logic is easy to follow, test, and swap for a proper DB
aggregation layer when the dataset grows.
"""

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.error_log import ErrorLog

router = APIRouter(prefix="/api/v1", tags=["analytics"])


@router.get("/analytics", response_model=dict[str, Any])
def get_analytics(db: Session = Depends(get_db)):
    """
    Return aggregate statistics across all triaged error logs.

    Response shape:
    ```json
    {
      "total_logs": 42,
      "by_status": {"triaged": 30, "failed": 8, "pending": 4},
      "by_service": {"checkout-api": 20, "auth-api": 12, ...},
      "by_confidence": {"high": 18, "medium": 9, "low": 3},
      "top_affected_files": [
        {"file": "app/utils/math.py", "count": 7}, ...
      ],
      "top_root_causes": [
        {"root_cause": "ZeroDivisionError in calculate_total", "count": 5}, ...
      ],
      "error_rate_by_service": [
        {"service": "checkout-api", "total": 20, "failed": 3, "error_rate": 0.15}, ...
      ]
    }
    ```
    """
    logs: list[ErrorLog] = db.query(ErrorLog).all()

    total = len(logs)
    by_status: Counter = Counter()
    by_service: Counter = Counter()
    by_confidence: Counter = Counter()
    file_counter: Counter = Counter()
    cause_counter: Counter = Counter()
    # service → {total, failed}
    service_stats: dict[str, dict[str, int]] = {}

    for log in logs:
        by_status[log.status] += 1
        by_service[log.service_name] += 1

        svc = service_stats.setdefault(log.service_name, {"total": 0, "failed": 0})
        svc["total"] += 1
        if log.status == "failed":
            svc["failed"] += 1

        if log.confidence:
            by_confidence[log.confidence] += 1

        if log.affected_files:
            for f in log.affected_files:
                file_counter[f] += 1

        if log.root_cause:
            # Truncate long root causes to a readable label
            label = log.root_cause[:120].strip()
            cause_counter[label] += 1

    top_files = [
        {"file": f, "count": c} for f, c in file_counter.most_common(10)
    ]
    top_causes = [
        {"root_cause": rc, "count": c} for rc, c in cause_counter.most_common(10)
    ]
    error_rates = [
        {
            "service": svc,
            "total": stats["total"],
            "failed": stats["failed"],
            "error_rate": round(stats["failed"] / stats["total"], 3) if stats["total"] else 0.0,
        }
        for svc, stats in sorted(service_stats.items(), key=lambda x: -x[1]["total"])
    ]

    return {
        "total_logs": total,
        "by_status": dict(by_status),
        "by_service": dict(by_service),
        "by_confidence": dict(by_confidence),
        "top_affected_files": top_files,
        "top_root_causes": top_causes,
        "error_rate_by_service": error_rates,
    }
