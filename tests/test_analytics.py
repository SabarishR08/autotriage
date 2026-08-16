"""
Tests for GET /api/v1/analytics.
"""


def test_analytics_empty_db(client):
    resp = client.get("/api/v1/analytics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_logs"] == 0
    assert body["by_status"] == {}
    assert body["by_service"] == {}
    assert body["top_affected_files"] == []
    assert body["top_root_causes"] == []
    assert body["error_rate_by_service"] == []


def test_analytics_after_ingest(client):
    payload = {
        "service_name": "checkout-api",
        "endpoint": "POST /v1/orders",
        "stack_trace": 'File "app/orders.py", line 5\nZeroDivisionError',
        "occurred_at": "2026-08-16T10:00:00Z",
    }
    client.post("/api/v1/logs", json=payload)
    client.post("/api/v1/logs", json=payload)

    resp = client.get("/api/v1/analytics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_logs"] == 2
    assert body["by_service"].get("checkout-api") == 2
    # Status will be one of: pending, analyzing, triaged, or failed depending
    # on whether a real LLM is reachable in this environment.
    # We only assert the logs were counted, not the outcome of background triage.
    assert len(body["by_status"]) >= 1


def test_analytics_service_filter_on_list(client):
    """List endpoint service filter works alongside analytics."""
    for svc in ["svc-a", "svc-b", "svc-a"]:
        client.post("/api/v1/logs", json={
            "service_name": svc,
            "endpoint": "GET /",
            "stack_trace": 'File "app/x.py", line 1\nError',
            "occurred_at": "2026-08-16T10:00:00Z",
        })

    resp = client.get("/api/v1/logs?service=svc-a")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(item["service_name"] == "svc-a" for item in body["items"])


def test_analytics_error_rate_keys(client):
    """error_rate_by_service entries have the expected shape."""
    client.post("/api/v1/logs", json={
        "service_name": "my-svc",
        "endpoint": "GET /ping",
        "stack_trace": 'File "app/ping.py", line 1\nRuntimeError',
        "occurred_at": "2026-08-16T10:00:00Z",
    })
    resp = client.get("/api/v1/analytics")
    body = resp.json()
    rates = body["error_rate_by_service"]
    assert len(rates) >= 1
    entry = next(r for r in rates if r["service"] == "my-svc")
    assert "total" in entry
    assert "failed" in entry
    assert "error_rate" in entry
