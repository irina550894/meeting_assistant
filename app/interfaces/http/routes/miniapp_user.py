from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application import UserBookingUseCases
from app.core.booking import BookingRecord, UserProfile
from app.core.booking.errors import BusinessRuleError
from app.core.datetime_formatting import format_time_msk
from app.core.user_flow import BookingDraft, UserFlowError
from app.interfaces.http.dependencies import (
    get_current_mini_app_user,
    get_user_booking_use_cases,
)
from app.interfaces.http.schemas.miniapp import (
    MiniAppAvailableDateResponse,
    MiniAppAvailableDatesResponse,
    MiniAppBookingCancelRequest,
    MiniAppBookingCreateRequest,
    MiniAppBookingDetailResponse,
    MiniAppBookingResponse,
    MiniAppBookingsResponse,
    MiniAppConfigResponse,
    MiniAppConsentRequest,
    MiniAppConsentResponse,
    MiniAppMeetingTypeResponse,
    MiniAppMeetingTypesResponse,
    MiniAppSlotResponse,
    MiniAppSlotsResponse,
    MiniAppUserResponse,
)
from app.settings.config import get_settings

router = APIRouter(prefix="/api/miniapp", tags=["miniapp-user"])


@router.get("/config", response_model=MiniAppConfigResponse)
async def mini_app_config() -> MiniAppConfigResponse:
    settings = get_settings()
    return MiniAppConfigResponse(
        timezone=settings.app_timezone,
        consent_url=settings.personal_data_consent_url,
        policy_url=settings.personal_data_policy_url,
        mini_app_public_path=settings.mini_app_public_path,
    )


@router.get("/profile", response_model=MiniAppUserResponse)
async def mini_app_profile(
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
) -> MiniAppUserResponse:
    return _user_response(user)


@router.post("/consent", response_model=MiniAppConsentResponse)
async def mini_app_accept_consent(
    payload: MiniAppConsentRequest,
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
    use_cases: Annotated[UserBookingUseCases, Depends(get_user_booking_use_cases)],
) -> MiniAppConsentResponse:
    if not payload.accepted:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "consent_required",
            "Consent must be accepted.",
        )
    try:
        updated_user = await use_cases.accept_consent(user)
    except UserFlowError as error:
        raise _flow_http_error(error) from error
    return MiniAppConsentResponse(
        has_consent=updated_user.has_personal_data_consent,
        accepted_at=updated_user.consent_accepted_at,
    )


@router.get("/meeting-types", response_model=MiniAppMeetingTypesResponse)
async def mini_app_meeting_types(
    use_cases: Annotated[UserBookingUseCases, Depends(get_user_booking_use_cases)],
) -> MiniAppMeetingTypesResponse:
    meeting_types = await use_cases.list_meeting_types()
    return MiniAppMeetingTypesResponse(
        items=[
            MiniAppMeetingTypeResponse(
                id=meeting_type.id,
                name=meeting_type.name,
                allowed_durations_minutes=list(meeting_type.allowed_durations_minutes),
                is_fixed_duration=meeting_type.is_fixed_duration,
            )
            for meeting_type in meeting_types
        ]
    )


@router.get("/available-dates", response_model=MiniAppAvailableDatesResponse)
async def mini_app_available_dates(
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
    use_cases: Annotated[UserBookingUseCases, Depends(get_user_booking_use_cases)],
) -> MiniAppAvailableDatesResponse:
    del user
    dates = await use_cases.available_dates()
    return MiniAppAvailableDatesResponse(
        items=[MiniAppAvailableDateResponse(date=item) for item in dates]
    )


@router.get("/slots", response_model=MiniAppSlotsResponse)
async def mini_app_slots(
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
    use_cases: Annotated[UserBookingUseCases, Depends(get_user_booking_use_cases)],
    target_date: Annotated[date, Query(alias="date")],
    meeting_type_id: Annotated[UUID, Query()],
    duration_minutes: Annotated[int, Query()],
) -> MiniAppSlotsResponse:
    del user
    try:
        slots = await use_cases.available_slots(
            target_date=target_date,
            meeting_type_id=meeting_type_id,
            duration_minutes=duration_minutes,
        )
    except UserFlowError as error:
        raise _flow_http_error(error) from error
    return MiniAppSlotsResponse(
        items=[
            MiniAppSlotResponse(
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                label=format_time_msk(slot.starts_at),
            )
            for slot in slots
        ]
    )


@router.post("/bookings", response_model=MiniAppBookingDetailResponse)
async def mini_app_create_booking(
    payload: MiniAppBookingCreateRequest,
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
    use_cases: Annotated[UserBookingUseCases, Depends(get_user_booking_use_cases)],
) -> MiniAppBookingDetailResponse:
    draft = BookingDraft(
        full_name=payload.full_name,
        email=payload.email,
        meeting_type_id=payload.meeting_type_id,
        duration_minutes=payload.duration_minutes,
        selected_date=payload.starts_at.date(),
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        user_comment=payload.user_comment,
        previous_booking_id=payload.previous_booking_id,
    )
    try:
        booking = await use_cases.create_booking(user=user, draft=draft)
    except BusinessRuleError as error:
        raise _business_http_error(error) from error
    except UserFlowError as error:
        raise _flow_http_error(error) from error
    return MiniAppBookingDetailResponse(booking=_booking_response(booking))


@router.get("/bookings", response_model=MiniAppBookingsResponse)
async def mini_app_list_bookings(
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
    use_cases: Annotated[UserBookingUseCases, Depends(get_user_booking_use_cases)],
) -> MiniAppBookingsResponse:
    bookings = await use_cases.list_user_bookings(user)
    return MiniAppBookingsResponse(items=[_booking_response(booking) for booking in bookings])


@router.get("/bookings/{booking_id}", response_model=MiniAppBookingDetailResponse)
async def mini_app_get_booking(
    booking_id: UUID,
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
    use_cases: Annotated[UserBookingUseCases, Depends(get_user_booking_use_cases)],
) -> MiniAppBookingDetailResponse:
    try:
        booking = await use_cases.get_user_booking(user=user, booking_id=booking_id)
    except BusinessRuleError as error:
        raise _business_http_error(error) from error
    return MiniAppBookingDetailResponse(booking=_booking_response(booking))


@router.post("/bookings/{booking_id}/cancel", response_model=MiniAppBookingDetailResponse)
async def mini_app_cancel_booking(
    booking_id: UUID,
    payload: MiniAppBookingCancelRequest,
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
    use_cases: Annotated[UserBookingUseCases, Depends(get_user_booking_use_cases)],
) -> MiniAppBookingDetailResponse:
    try:
        booking = await use_cases.cancel_user_booking(
            user=user,
            booking_id=booking_id,
            reason=payload.reason,
        )
    except BusinessRuleError as error:
        raise _business_http_error(error) from error
    return MiniAppBookingDetailResponse(booking=_booking_response(booking))


@router.post(
    "/bookings/{booking_id}/reschedule/prepare",
    response_model=MiniAppBookingDetailResponse,
)
async def mini_app_prepare_reschedule(
    booking_id: UUID,
    user: Annotated[UserProfile, Depends(get_current_mini_app_user)],
    use_cases: Annotated[UserBookingUseCases, Depends(get_user_booking_use_cases)],
) -> MiniAppBookingDetailResponse:
    try:
        booking = await use_cases.prepare_reschedule(user=user, booking_id=booking_id)
    except BusinessRuleError as error:
        raise _business_http_error(error) from error
    return MiniAppBookingDetailResponse(booking=_booking_response(booking))


def _user_response(user: UserProfile) -> MiniAppUserResponse:
    settings = get_settings()
    return MiniAppUserResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        full_name=user.full_name,
        email=user.email,
        has_consent=user.has_personal_data_consent,
        is_blocked=user.is_blocked,
        is_admin=settings.telegram_admin_id is not None
        and user.telegram_id == settings.telegram_admin_id,
    )


def _booking_response(booking: BookingRecord) -> MiniAppBookingResponse:
    return MiniAppBookingResponse(
        id=booking.id,
        display_number=booking.display_number,
        status=booking.status.value,
        meeting_type_id=booking.meeting_type_id,
        duration_minutes=booking.duration_minutes,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        user_comment=booking.user_comment,
        rejection_reason=booking.rejection_reason,
        cancellation_reason=booking.cancellation_reason,
        reserved_until=booking.reserved_until,
        meeting_url=booking.meeting_url,
        is_reschedule_request=booking.is_reschedule_request,
        previous_booking_id=booking.previous_booking_id,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )


def _flow_http_error(error: UserFlowError) -> HTTPException:
    return _http_error(status.HTTP_422_UNPROCESSABLE_ENTITY, error.code, str(error))


def _business_http_error(error: BusinessRuleError) -> HTTPException:
    status_code = status.HTTP_409_CONFLICT
    if error.rule in {"booking_not_found", "previous_booking_not_found"}:
        status_code = status.HTTP_404_NOT_FOUND
    elif error.rule in {"user_blocked", "personal_data_consent_required"}:
        status_code = status.HTTP_403_FORBIDDEN
    return _http_error(status_code, error.rule, str(error))


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
