from fastapi import APIRouter

from app.logging.config import get_logger
from app.settings.config import get_settings

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    settings = get_settings()
    logger.info(
        "Healthcheck requested",
        extra={"event": "healthcheck_ok", "service": "app"},
    )
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }
