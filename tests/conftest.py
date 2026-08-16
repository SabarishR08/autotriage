"""
Test configuration and shared fixtures.

The lifespan in main.py calls settings.validate() and run_migrations().
Both fail in the test environment (no real LLM key, no alembic.ini on PATH).
We mock them out so tests run against an in-memory SQLite DB only.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture()
def test_db():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestingSessionLocal
    app.dependency_overrides.clear()


@pytest.fixture()
def client(test_db):
    # Patch out the two lifespan side-effects that require real infrastructure:
    #   - settings.validate()  → would sys.exit(1) if LLM_API_KEY is unset
    #   - run_migrations()     → requires alembic.ini + a real DB connection
    # Tests use an in-memory SQLite DB created directly via Base.metadata.create_all
    # in the test_db fixture, so no migration runner is needed.
    with (
        patch("app.main.settings.validate"),
        patch("app.main.run_migrations"),
    ):
        with TestClient(app) as c:
            yield c
