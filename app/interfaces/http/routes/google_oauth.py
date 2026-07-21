from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import SecretStr

from app.integrations.google_calendar import (
    GoogleCalendarClient,
    GoogleCalendarError,
    GoogleOAuthService,
    GoogleOAuthTokens,
)
from app.logging.config import get_logger
from app.persistence.database import AsyncSessionFactory
from app.persistence.repositories.google_oauth import SqlAlchemyGoogleOAuthTokenStore
from app.settings.config import get_settings

router = APIRouter(prefix="/oauth/google", tags=["google-oauth"])
logger = get_logger(__name__)

_last_state: str | None = None


@router.get("/status")
async def google_oauth_status() -> dict[str, bool | str | None]:
    settings = get_settings()
    tokens = await SqlAlchemyGoogleOAuthTokenStore(
        session_factory=AsyncSessionFactory,
        settings=settings,
    ).get()

    if tokens is None and (
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_refresh_token
    ):
        tokens = GoogleOAuthTokens(
            access_token=None,
            refresh_token=settings.google_oauth_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_oauth_client_id,
            client_secret=SecretStr(settings.google_oauth_client_secret.get_secret_value()),
        )

    if tokens is None:
        return {
            "connected": False,
            "needs_reconnect": True,
            "error_code": "google_calendar_not_connected",
        }

    client = GoogleCalendarClient(settings=settings, token_provider=lambda: tokens)
    now = datetime.now(ZoneInfo(settings.app_timezone))
    try:
        client.list_busy_intervals(time_min=now, time_max=now + timedelta(minutes=1))
    except GoogleCalendarError as error:
        return {
            "connected": False,
            "needs_reconnect": True,
            "error_code": error.code,
        }

    return {"connected": True, "needs_reconnect": False, "error_code": None}


@router.get("/start")
async def start_google_oauth() -> dict[str, str]:
    global _last_state
    settings = get_settings()
    if settings.telegram_admin_id is None:
        raise HTTPException(status_code=503, detail="Telegram admin ID is not configured.")
    service = GoogleOAuthService(
        settings=settings,
        token_store=SqlAlchemyGoogleOAuthTokenStore(
            session_factory=AsyncSessionFactory,
            settings=settings,
        ),
    )
    try:
        authorization_url, state = service.authorization_url(
            admin_telegram_id=settings.telegram_admin_id,
        )
    except GoogleCalendarError as error:
        logger.warning(
            "Google OAuth start failed",
            extra={"event": "google_oauth_error", "error_code": error.code},
        )
        raise HTTPException(status_code=503, detail=error.code) from error
    _last_state = state
    return {"authorization_url": authorization_url}


@router.get("/callback")
async def google_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
) -> dict[str, str]:
    settings = get_settings()
    if settings.telegram_admin_id is None:
        raise HTTPException(status_code=503, detail="Telegram admin ID is not configured.")
    if _last_state is None or state != _last_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    service = GoogleOAuthService(
        settings=settings,
        token_store=SqlAlchemyGoogleOAuthTokenStore(
            session_factory=AsyncSessionFactory,
            settings=settings,
        ),
    )
    try:
        await service.handle_callback(code=code, admin_telegram_id=settings.telegram_admin_id)
    except GoogleCalendarError as error:
        raise HTTPException(status_code=502, detail=error.code) from error
    return {"status": "connected"}
