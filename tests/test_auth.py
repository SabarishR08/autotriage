"""
Tests for X-API-Key auth on the ingestion endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"

VALID_PAYLOAD = {
    "service_name": "auth-test-svc",
    "endpoint": "POST /v1/test",
    "stack_trace": 'File "app/test.py", line 1, in fn\nValueError: oops',
    "occurred_at": "2026-08-16T10:00:00Z",
}


@pytest.fixture()
def authed_client(monkeypatch):
    """TestClient with AUTOTRIAGE_API_KEY configured."""
    # Patch settings before the client is created
    settings = get_settings()
    monkeypatch.setattr(settings, "AUTOTRIAGE_API_KEY", "test-secret-key")

    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    # Reset the key after test
    monkeypatch.setattr(settings, "AUTOTRIAGE_API_KEY", None)


def test_ingest_without_key_is_rejected(authed_client):
    resp = authed_client.post("/api/v1/logs", json=VALID_PAYLOAD)
    assert resp.status_code == 401


def test_ingest_with_wrong_key_is_rejected(authed_client):
    resp = authed_client.post(
        "/api/v1/logs", json=VALID_PAYLOAD, headers={"X-API-Key": "wrong-key"}
    )
    assert resp.status_code == 401


def test_ingest_with_correct_key_succeeds(authed_client):
    resp = authed_client.post(
        "/api/v1/logs", json=VALID_PAYLOAD, headers={"X-API-Key": "test-secret-key"}
    )
    assert resp.status_code == 201


def test_ingest_open_when_no_key_configured(client):
    """When AUTOTRIAGE_API_KEY is unset, any request is accepted."""
    resp = client.post("/api/v1/logs", json=VALID_PAYLOAD)
    assert resp.status_code == 201
