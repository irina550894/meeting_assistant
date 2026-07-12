from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.integrations.telegram.runtime import build_telegram_runtime
from app.interfaces.http.routes.google_oauth import router as google_oauth_router
from app.interfaces.http.routes.health import router as health_router
from app.interfaces.http.routes.telegram_webhook import router as telegram_webhook_router
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
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "Application started",
            extra={
                "event": (
                    "production_app_started"
                    if settings.app_env == "production"
                    else "app_started"
                ),
                "service": "app",
                "environment": settings.app_env,
            },
        )
        if settings.telegram_use_webhook:
            application.state.telegram_runtime = await build_telegram_runtime(settings)
            if settings.public_base_url is None:
                raise RuntimeError("PUBLIC_BASE_URL is required for Telegram webhook.")
            if settings.webhook_secret is None:
                raise RuntimeError("WEBHOOK_SECRET is required for Telegram webhook.")
            webhook_url = f"{settings.public_base_url.rstrip('/')}/telegram/webhook"
            await application.state.telegram_runtime.bot.set_webhook(
                webhook_url,
                secret_token=settings.webhook_secret.get_secret_value(),
                drop_pending_updates=True,
            )
            logger.info(
                "Telegram webhook configured",
                extra={"event": "telegram_webhook_configured"},
            )
        try:
            yield
        finally:
            runtime = getattr(application.state, "telegram_runtime", None)
            if runtime is not None:
                await runtime.bot.session.close()
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
    application.include_router(telegram_webhook_router)

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
