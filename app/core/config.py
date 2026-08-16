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

# override=False means real env vars always win over .env file.
# This is correct for containers: Docker/Render inject the real values;
# we don't want a stale .env file (if somehow present) to shadow them.
load_dotenv(override=False)


class Settings:
    # --- App ---
    APP_NAME: str = "AutoTriage"
    APP_ENV: str = os.getenv("APP_ENV", "development")

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./autotriage.db")

    # --- GitHub ---
    GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")
    GITHUB_REPO: str | None = os.getenv("GITHUB_REPO")

    # --- LLM ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
    LLM_API_KEY: str | None = os.getenv("LLM_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    # Custom base URL for OpenAI-compatible providers (Groq, NVIDIA NIM, etc.)
    OPENAI_API_BASE: str | None = os.getenv("OPENAI_API_BASE")

    # --- Server ---
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

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
        Fail fast on startup if required secrets are missing.

        Called from the FastAPI lifespan so the container exits immediately
        with a clear error rather than surfacing a cryptic 500 on the first
        triage attempt.
        """
        errors: list[str] = []

        if not self.LLM_API_KEY:
            errors.append(
                "LLM_API_KEY is not set. "
                "AutoTriage requires a provider API key to run triage."
            )

        if self.APP_ENV == "production":
            if self.ALLOWED_ORIGINS == ["*"]:
                errors.append(
                    "ALLOWED_ORIGINS must not be '*' in production. "
                    "Set it to your frontend domain(s)."
                )
            if not self.AUTOTRIAGE_API_KEY:
                errors.append(
                    "AUTOTRIAGE_API_KEY is not set. "
                    "The ingestion endpoint is open to anyone in production."
                )

        if errors:
            for msg in errors:
                print(f"[AutoTriage] STARTUP ERROR: {msg}", file=sys.stderr)
            sys.exit(1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
