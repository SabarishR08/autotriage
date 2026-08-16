"""
Database engine, session factory, and initialisation.

Supports SQLite (dev/test) and Postgres (production) via DATABASE_URL.
Postgres gets connection pool tuning and pool_pre_ping to recycle stale
connections silently (important on managed Postgres where connections can
be dropped between requests).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_is_sqlite = "sqlite" in settings.DATABASE_URL

if _is_sqlite:
    # SQLite: disable the same-thread check so FastAPI's thread pool works,
    # use a StaticPool replacement in tests (conftest overrides the dependency).
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    # Postgres (and other production DBs): tune the connection pool.
    #
    # pool_pre_ping=True  — issue a lightweight SELECT 1 before handing a
    #   connection to a request; detects and recycles stale connections that
    #   were dropped by the managed DB or a network blip.
    # pool_size=10        — keep up to 10 connections open at steady state.
    # max_overflow=20     — allow up to 20 additional connections under burst
    #   load; they are closed as soon as they're returned to the pool.
    # pool_recycle=1800   — force-recycle connections older than 30 minutes,
    #   staying well inside Postgres's default idle_in_transaction_session_timeout.
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session per request, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """
    Run Alembic migrations at startup (upgrade to head).

    This replaces the old `create_all` call and works for both SQLite (dev)
    and Postgres (production). Running on every startup is safe — Alembic
    is idempotent and only applies pending revisions.
    """
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
