"""
Application configuration.

All secrets are read from environment variables only — never hardcoded.

Load order (highest priority wins):
  1. Real environment variables (injected by Docker / Render / shell)
  2. .env file on disk (local dev only, gitignored)

In containerised deployments there is no .env file inside the image
(excluded by .dockerignore), so load_dotenv is effectively a no-op there
and injected env vars are used as-is.
"""

import os
import sys
from functools import lru_cache

from dotenv import load_dotenv

# Default constants
DEFAULT_PORT: int = 8000
DEFAULT_HTTP_TIMEOUT: float = 30.0
DEFAULT_GITHUB_TIMEOUT: float = 10.0

# override=False means real env vars always win over .env file.
# This is correct for containers: Docker/Render inject the real values;
# we don't want a stale .env file (if somehow present) to shadow them.
load_dotenv(override=False)


class Settings:
    # --- Default Constants ---
    DEFAULT_PORT: int = DEFAULT_PORT
    DEFAULT_HTTP_TIMEOUT: float = DEFAULT_HTTP_TIMEOUT
    DEFAULT_GITHUB_TIMEOUT: float = DEFAULT_GITHUB_TIMEOUT

    # --- App ---
    APP_NAME: str = "AutoTriage"
    APP_ENV: str = os.getenv("APP_ENV", "development")

    # --- Database ---
    # Render (and Heroku) inject DATABASE_URL as postgres:// — SQLAlchemy 2.x
    # requires postgresql://. Fix it transparently here.
    _raw_db_url: str = os.getenv("DATABASE_URL", "sqlite:///./autotriage.db")
    DATABASE_URL: str = _raw_db_url.replace("postgres://", "postgresql://", 1)

    # --- GitHub ---
    GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")
    GITHUB_REPO: str | None = os.getenv("GITHUB_REPO")
    GITHUB_TIMEOUT_SECONDS: float = float(
        os.getenv("GITHUB_TIMEOUT_SECONDS", str(DEFAULT_GITHUB_TIMEOUT))
    )

    # --- LLM ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
    LLM_API_KEY: str | None = os.getenv("LLM_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    # Custom base URL for OpenAI-compatible providers (Groq, NVIDIA NIM, etc.)
    OPENAI_API_BASE: str | None = os.getenv("OPENAI_API_BASE")
    LLM_TIMEOUT_SECONDS: float = float(
        os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_HTTP_TIMEOUT))
    )

    # --- Server ---
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", str(DEFAULT_PORT)))

    # --- CORS ---
    # Comma-separated list of allowed origins.
    # Defaults to "*" in development; MUST be set explicitly in production.
    # Example: ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com
    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
        if o.strip()
    ]

    # --- Auth ---
    # Set to require X-API-Key header on POST /api/v1/logs.
    # Leave blank for open access (dev / internal-only deployments).
    AUTOTRIAGE_API_KEY: str | None = os.getenv("AUTOTRIAGE_API_KEY")

    def validate(self) -> None:
        """
        Validate config at startup.

        Hard errors (sys.exit): missing required env vars in production.
        """
        if self.APP_ENV == "production":
            missing = []
            if not self.GITHUB_TOKEN:
                missing.append("GITHUB_TOKEN")
            if not self.LLM_API_KEY:
                missing.append("LLM_API_KEY")
            if missing:
                sys.stderr.write(
                    f"FATAL: Missing required environment variables for production: {', '.join(missing)}\n"
                )
                sys.exit(1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
