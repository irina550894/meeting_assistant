from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.interfaces.http.routes.google_oauth import router as google_oauth_router
from app.interfaces.http.routes.health import router as health_router
from app.logging.config import (
    configure_logging,
    get_logger,
    new_operation_id,
    reset_operation_id,
    set_operation_id,
)
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
    application.include_router(google_oauth_router)

    @application.middleware("http")
    async def operation_id_middleware(request: Request, call_next):
        operation_id = request.headers.get("x-operation-id") or new_operation_id()
        token = set_operation_id(operation_id)
        try:
            response = await call_next(request)
        finally:
            reset_operation_id(token)
        response.headers["x-operation-id"] = operation_id
        return response

    return application


app = create_app()
