from fastapi import APIRouter

from app.core.config import get_settings
from app.__init__ import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "llm_provider": settings.LLM_PROVIDER,
        "github_configured": bool(settings.GITHUB_TOKEN and settings.GITHUB_REPO),
        "version": __version__,
    }