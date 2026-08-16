"""
Application configuration.

All secrets (LLM API keys, GitHub PAT) are read from environment variables
only. Nothing here is ever hardcoded or committed.
"""

import os
from functools import lru_cache


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
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
    LLM_API_KEY: str | None = os.getenv("LLM_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

    # --- Server ---
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
