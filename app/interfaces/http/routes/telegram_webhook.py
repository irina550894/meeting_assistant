from fastapi import APIRouter, Header, HTTPException, Request, status

from app.logging.config import get_logger
from app.settings.config import get_settings

router = APIRouter(prefix="/telegram", tags=["telegram-webhook"])
logger = get_logger(__name__)


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    settings = get_settings()
    if not settings.telegram_use_webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if settings.webhook_secret is None:
        logger.error(
            "Telegram webhook secret is not configured",
            extra={"event": "telegram_webhook_secret_missing"},
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    if x_telegram_bot_api_secret_token != settings.webhook_secret.get_secret_value():
        logger.warning(
            "Telegram webhook secret mismatch",
            extra={"event": "telegram_webhook_access_denied"},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    runtime = getattr(request.app.state, "telegram_runtime", None)
    if runtime is None:
        logger.error(
            "Telegram webhook runtime is not configured",
            extra={"event": "telegram_webhook_runtime_missing"},
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    update = await request.json()
    await runtime.dispatcher.feed_webhook_update(runtime.bot, update)
    return {"ok": True}
