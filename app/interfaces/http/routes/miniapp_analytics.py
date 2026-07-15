from typing import Annotated

from fastapi import APIRouter, Depends

from app.application import MiniAppAnalyticsService
from app.core.booking import UserProfile
from app.interfaces.http.dependencies import (
    get_current_mini_app_user,
    get_mini_app_analytics_service,
)
from app.interfaces.http.schemas.miniapp import MiniAppAnalyticsEventRequest, MiniAppOkResponse

router = APIRouter(prefix="/api/miniapp/analytics", tags=["miniapp-analytics"])


@router.post("/event", response_model=MiniAppOkResponse)
async def mini_app_track_event(
    payload: MiniAppAnalyticsEventRequest,
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
    analytics: Annotated[MiniAppAnalyticsService, Depends(get_mini_app_analytics_service)],
) -> MiniAppOkResponse:
    await analytics.track_event(
        user=user,
        event_name=payload.event_name,
        payload=payload.payload,
    )
    return MiniAppOkResponse()
