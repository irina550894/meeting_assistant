from fastapi import APIRouter, HTTPException, Query

from app.integrations.google_calendar import (
    GoogleCalendarError,
    GoogleOAuthService,
)
from app.logging.config import get_logger
from app.persistence.database import AsyncSessionFactory
from app.persistence.repositories.google_oauth import SqlAlchemyGoogleOAuthTokenStore
from app.settings.config import get_settings

router = APIRouter(prefix="/oauth/google", tags=["google-oauth"])
logger = get_logger(__name__)

_last_state: str | None = None


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
