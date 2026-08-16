"""
Application configuration.

All secrets (LLM API keys, GitHub PAT) are read from environment variables
only. Nothing here is ever hardcoded or committed.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv(override=True)  # .env always wins over any inherited shell env vars


class Settings:
    # --- App ---
    APP_NAME: str = "AutoTriage"
    APP_ENV: str = os.getenv("APP_ENV", "development")

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./autotriage.db")

    # --- GitHub ---
    GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")
    GITHUB_REPO: str | None = os.getenv("GITHUB_REPO")  # e.g. "owner/repo"

    # --- LLM ---
    # Provider is swappable: "openai" | "anthropic"
    # For OpenAI-compatible providers (Groq, NVIDIA NIM, etc.) set OPENAI_API_BASE.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
    LLM_API_KEY: str | None = os.getenv("LLM_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    OPENAI_API_BASE: str | None = os.getenv("OPENAI_API_BASE")  # e.g. https://api.groq.com/openai/v1

    # --- Server ---
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # --- Auth ---
    # Set this to require an X-API-Key header on the ingestion endpoint.
    # Leave blank to run open (development / internal-only deployments).
    AUTOTRIAGE_API_KEY: str | None = os.getenv("AUTOTRIAGE_API_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
