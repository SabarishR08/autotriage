def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "AutoTriage"


def test_ingest_valid_log(client):
    payload = {
        "service_name": "checkout-api",
        "endpoint": "POST /v1/orders",
        "stack_trace": (
            "Traceback (most recent call last):\n"
            '  File "app/services/orders.py", line 42, in create_order\n'
            "    total = calculate_total(items)\n"
            "ZeroDivisionError: division by zero"
        ),
        "occurred_at": "2026-08-16T10:00:00Z",
        "request_metadata": {"user_id": "u_123", "cart_size": 0},
    }
    response = client.post("/api/v1/logs", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert "id" in body


def test_ingest_missing_required_field_rejected(client):
    payload = {
        "service_name": "checkout-api",
        # missing endpoint, stack_trace, occurred_at
    }
    response = client.post("/api/v1/logs", json=payload)
    assert response.status_code == 422


def test_get_nonexistent_log_returns_404(client):
    response = client.get("/api/v1/logs/does-not-exist")
    assert response.status_code == 404


def test_list_logs_empty(client):
    response = client.get("/api/v1/logs")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_logs_after_ingest(client):
    payload = {
        "service_name": "auth-api",
        "endpoint": "POST /v1/login",
        "stack_trace": 'File "app/auth.py", line 10, in login\nKeyError: token',
        "occurred_at": "2026-08-16T11:00:00Z",
    }
    client.post("/api/v1/logs", json=payload)
    response = client.get("/api/v1/logs")
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["service_name"] == "auth-api"
