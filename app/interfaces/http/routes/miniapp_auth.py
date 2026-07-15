from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.application import MiniAppAuthError, MiniAppAuthResult, MiniAppAuthService
from app.interfaces.http.dependencies import get_mini_app_auth_service
from app.interfaces.http.schemas import MiniAppAuthRequest, MiniAppAuthResponse
from app.interfaces.http.schemas.miniapp import MiniAppUserResponse
from app.logging.config import get_logger
from app.settings.config import get_settings

router = APIRouter(prefix="/api/miniapp/auth", tags=["miniapp-auth"])
logger = get_logger(__name__)


@router.post("/telegram", response_model=MiniAppAuthResponse)
async def mini_app_telegram_auth(
    payload: MiniAppAuthRequest,
    response: Response,
    auth_service: Annotated[MiniAppAuthService, Depends(get_mini_app_auth_service)],
) -> MiniAppAuthResponse:
    settings = get_settings()
    if not settings.mini_app_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        result = await auth_service.authenticate(payload.init_data)
    except MiniAppAuthError as error:
        logger.warning(
            "Mini App authentication failed",
            extra={"event": "mini_app_auth_failed", "reason": error.code},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": error.code, "message": str(error)},
        ) from error

    response.set_cookie(
        key=settings.mini_app_cookie_name,
        value=result.session_token,
        max_age=settings.mini_app_session_ttl_seconds,
        expires=int(settings.mini_app_session_ttl_seconds),
        httponly=True,
        secure=settings.mini_app_cookie_secure,
        samesite=settings.mini_app_cookie_samesite,
        path="/",
    )
    return _auth_response(result)


def _auth_response(result: MiniAppAuthResult) -> MiniAppAuthResponse:
    user = result.user
    return MiniAppAuthResponse(
        user=MiniAppUserResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            telegram_username=user.telegram_username,
            full_name=user.full_name,
            email=user.email,
            has_consent=user.has_personal_data_consent,
            is_blocked=user.is_blocked,
            is_admin=result.is_admin,
        ),
        session_expires_at=result.expires_at,
    )
