from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.interfaces.http.routes.health import router as health_router
from app.logging.config import configure_logging, get_logger
from app.settings.config import get_settings

configure_logging()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "Application started",
            extra={"event": "app_started", "service": "app", "environment": settings.app_env},
        )
        yield
        logger.info(
            "Application stopped",
            extra={"event": "app_stopped", "service": "app"},
        )

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    application.include_router(health_router)
    return application


app = create_app()
