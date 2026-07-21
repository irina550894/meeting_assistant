from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application import (
    AdminBookingUseCases,
    AdminSettingsUseCaseError,
    AdminSettingsUseCases,
)
from app.core.admin_flow import AdminBookingCard
from app.core.booking import BookingStatus, UserProfile
from app.core.booking.errors import BusinessRuleError
from app.integrations.google_calendar import GoogleCalendarError
from app.interfaces.http.dependencies import (
    get_admin_booking_use_cases,
    get_admin_settings_use_cases,
    get_current_mini_app_admin,
)
from app.interfaces.http.routes.miniapp_user import _booking_response, _user_response
from app.interfaces.http.schemas.miniapp import (
    MiniAppAdminBookingCardResponse,
    MiniAppAdminBookingsResponse,
    MiniAppAdminConfirmRequest,
    MiniAppAdminDashboardMetricsResponse,
    MiniAppAdminDashboardResponse,
    MiniAppAdminMeetingTypeResponse,
    MiniAppAdminMeetingTypesResponse,
    MiniAppAdminRejectRequest,
    MiniAppBookingCancelRequest,
    MiniAppBookingResponse,
    MiniAppClosedDayRestrictionCreateRequest,
    MiniAppMeetingTypeCreateRequest,
    MiniAppMeetingTypeResponse,
    MiniAppMeetingTypeUpdateRequest,
    MiniAppOkResponse,
    MiniAppScheduleRestrictionResponse,
    MiniAppScheduleRestrictionsResponse,
    MiniAppScheduleSettingsResponse,
    MiniAppScheduleSettingsUpdateRequest,
    MiniAppTimeIntervalRestrictionCreateRequest,
    MiniAppWorkingHoursListResponse,
    MiniAppWorkingHoursResponse,
    MiniAppWorkingHoursUpdateRequest,
)
from app.settings.config import get_settings

router = APIRouter(prefix="/api/miniapp/admin", tags=["miniapp-admin"])


@router.get("/dashboard", response_model=MiniAppAdminDashboardResponse)
async def mini_app_admin_dashboard(
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminBookingUseCases, Depends(get_admin_booking_use_cases)],
) -> MiniAppAdminDashboardResponse:
    del admin
    dashboard = await use_cases.dashboard()
    return MiniAppAdminDashboardResponse(
        metrics=MiniAppAdminDashboardMetricsResponse(
            pending=dashboard.pending,
            confirmed=dashboard.confirmed,
            reschedule_requested=dashboard.reschedule_requested,
            cancelled=dashboard.cancelled,
        ),
        upcoming=[_booking_response(booking) for booking in dashboard.upcoming],
        recent_pending=[_booking_response(booking) for booking in dashboard.recent_pending],
    )


@router.get("/bookings", response_model=MiniAppAdminBookingsResponse)
async def mini_app_admin_bookings(
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminBookingUseCases, Depends(get_admin_booking_use_cases)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> MiniAppAdminBookingsResponse:
    del admin
    try:
        status_value = BookingStatus(status_filter) if status_filter else None
    except ValueError as error:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_booking_status",
            "Booking status filter is invalid.",
        ) from error
    bookings = await use_cases.list_bookings(status=status_value)
    cards = [await use_cases.get_booking_card(booking.id) for booking in bookings]
    return MiniAppAdminBookingsResponse(items=[_admin_card_response(card) for card in cards])


@router.get("/bookings/{booking_id}", response_model=MiniAppAdminBookingCardResponse)
async def mini_app_admin_booking_card(
    booking_id: UUID,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminBookingUseCases, Depends(get_admin_booking_use_cases)],
) -> MiniAppAdminBookingCardResponse:
    del admin
    try:
        card = await use_cases.get_booking_card(booking_id)
    except BusinessRuleError as error:
        raise _business_http_error(error) from error
    return _admin_card_response(card)


@router.post("/bookings/{booking_id}/confirm", response_model=MiniAppAdminBookingCardResponse)
async def mini_app_admin_confirm_booking(
    booking_id: UUID,
    payload: MiniAppAdminConfirmRequest,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminBookingUseCases, Depends(get_admin_booking_use_cases)],
) -> MiniAppAdminBookingCardResponse:
    meeting_url = payload.meeting_url or get_settings().default_meeting_url
    if not meeting_url:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "meeting_url_required",
            "Meeting URL is required.",
        )
    try:
        card = await use_cases.confirm_booking(
            booking_id=booking_id,
            meeting_url=meeting_url,
            admin_telegram_id=admin.telegram_id,
        )
    except BusinessRuleError as error:
        raise _business_http_error(error) from error
    except GoogleCalendarError as error:
        raise _http_error(status.HTTP_503_SERVICE_UNAVAILABLE, error.code, str(error)) from error
    return _admin_card_response(card)


@router.post("/bookings/{booking_id}/reject", response_model=MiniAppAdminBookingCardResponse)
async def mini_app_admin_reject_booking(
    booking_id: UUID,
    payload: MiniAppAdminRejectRequest,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminBookingUseCases, Depends(get_admin_booking_use_cases)],
) -> MiniAppAdminBookingCardResponse:
    try:
        card = await use_cases.reject_booking(
            booking_id=booking_id,
            admin_telegram_id=admin.telegram_id,
            reason=payload.reason,
        )
    except BusinessRuleError as error:
        raise _business_http_error(error) from error
    return _admin_card_response(card)


@router.post("/bookings/{booking_id}/cancel", response_model=MiniAppAdminBookingCardResponse)
async def mini_app_admin_cancel_booking(
    booking_id: UUID,
    payload: MiniAppBookingCancelRequest,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminBookingUseCases, Depends(get_admin_booking_use_cases)],
) -> MiniAppAdminBookingCardResponse:
    try:
        card = await use_cases.cancel_booking(
            booking_id=booking_id,
            admin_telegram_id=admin.telegram_id,
            reason=payload.reason,
        )
    except BusinessRuleError as error:
        raise _business_http_error(error) from error
    return _admin_card_response(card)


@router.get("/calendar", response_model=list[MiniAppBookingResponse])
async def mini_app_admin_calendar(
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminBookingUseCases, Depends(get_admin_booking_use_cases)],
) -> list[MiniAppBookingResponse]:
    del admin
    bookings = await use_cases.list_bookings(status=BookingStatus.CONFIRMED)
    return [_booking_response(booking) for booking in bookings]


@router.get("/schedule/settings", response_model=MiniAppScheduleSettingsResponse)
async def mini_app_admin_schedule_settings(
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppScheduleSettingsResponse:
    del admin
    settings = await use_cases.get_schedule_settings()
    return MiniAppScheduleSettingsResponse(
        timezone=settings.timezone,
        min_booking_lead_days=settings.min_booking_lead_days,
        booking_horizon_days=settings.booking_horizon_days,
        slot_step_minutes=settings.slot_step_minutes,
        meeting_buffer_minutes=settings.meeting_buffer_minutes,
    )


@router.patch("/schedule/settings", response_model=MiniAppScheduleSettingsResponse)
async def mini_app_admin_update_schedule_settings(
    payload: MiniAppScheduleSettingsUpdateRequest,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppScheduleSettingsResponse:
    del admin
    try:
        settings = await use_cases.update_schedule_settings(
            booking_horizon_days=payload.booking_horizon_days,
            slot_step_minutes=payload.slot_step_minutes,
            meeting_buffer_minutes=payload.meeting_buffer_minutes,
        )
    except AdminSettingsUseCaseError as error:
        raise _settings_http_error(error) from error
    return MiniAppScheduleSettingsResponse(
        timezone=settings.timezone,
        min_booking_lead_days=settings.min_booking_lead_days,
        booking_horizon_days=settings.booking_horizon_days,
        slot_step_minutes=settings.slot_step_minutes,
        meeting_buffer_minutes=settings.meeting_buffer_minutes,
    )


@router.get("/schedule/working-hours", response_model=MiniAppWorkingHoursListResponse)
async def mini_app_admin_working_hours(
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppWorkingHoursListResponse:
    del admin
    rows = await use_cases.list_working_hours()
    return MiniAppWorkingHoursListResponse(
        items=[
            MiniAppWorkingHoursResponse(
                weekday=row.weekday,
                is_working_day=row.is_working_day,
                start_time=row.start_time,
                end_time=row.end_time,
            )
            for row in rows
        ]
    )


@router.patch("/schedule/working-hours/{weekday}", response_model=MiniAppWorkingHoursResponse)
async def mini_app_admin_update_working_hours(
    weekday: int,
    payload: MiniAppWorkingHoursUpdateRequest,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppWorkingHoursResponse:
    del admin
    try:
        row = await use_cases.update_working_hours(
            weekday=weekday,
            is_working_day=payload.is_working_day,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
    except AdminSettingsUseCaseError as error:
        raise _settings_http_error(error) from error
    return MiniAppWorkingHoursResponse(
        weekday=row.weekday,
        is_working_day=row.is_working_day,
        start_time=row.start_time,
        end_time=row.end_time,
    )


@router.get("/schedule/restrictions", response_model=MiniAppScheduleRestrictionsResponse)
async def mini_app_admin_restrictions(
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
    from_date: Annotated[date, Query(alias="from")],
) -> MiniAppScheduleRestrictionsResponse:
    del admin
    rows = await use_cases.list_restrictions(from_date=from_date)
    return MiniAppScheduleRestrictionsResponse(
        items=[
            MiniAppScheduleRestrictionResponse(
                id=row.id,
                restriction_date=row.restriction_date,
                restriction_type=row.restriction_type,
                start_time=row.start_time,
                end_time=row.end_time,
                admin_comment=row.admin_comment,
            )
            for row in rows
        ]
    )


@router.post("/schedule/restrictions/closed-day", response_model=MiniAppOkResponse)
async def mini_app_admin_add_closed_day(
    payload: MiniAppClosedDayRestrictionCreateRequest,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppOkResponse:
    del admin
    await use_cases.add_closed_day_restriction(
        restriction_date=payload.restriction_date,
        admin_comment=payload.admin_comment,
    )
    return MiniAppOkResponse()


@router.post("/schedule/restrictions/time-interval", response_model=MiniAppOkResponse)
async def mini_app_admin_add_time_interval(
    payload: MiniAppTimeIntervalRestrictionCreateRequest,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppOkResponse:
    del admin
    if payload.start_time >= payload.end_time:
        raise _settings_http_error(
            AdminSettingsUseCaseError(
                "invalid_time_interval",
                "Restriction start time must be before end time.",
            )
        )
    try:
        await use_cases.add_time_interval_restriction(
            restriction_date=payload.restriction_date,
            start_time=payload.start_time,
            end_time=payload.end_time,
            admin_comment=payload.admin_comment,
        )
    except AdminSettingsUseCaseError as error:
        raise _settings_http_error(error) from error
    return MiniAppOkResponse()


@router.delete("/schedule/restrictions/{restriction_id}", response_model=MiniAppOkResponse)
async def mini_app_admin_delete_restriction(
    restriction_id: UUID,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppOkResponse:
    del admin
    try:
        await use_cases.delete_restriction(restriction_id)
    except AdminSettingsUseCaseError as error:
        raise _settings_http_error(error) from error
    return MiniAppOkResponse()


@router.get("/meeting-types", response_model=MiniAppAdminMeetingTypesResponse)
async def mini_app_admin_meeting_types(
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppAdminMeetingTypesResponse:
    del admin
    rows = await use_cases.list_meeting_types_admin()
    return MiniAppAdminMeetingTypesResponse(
        items=[_admin_meeting_type_response(row) for row in rows]
    )


@router.post("/meeting-types", response_model=MiniAppAdminMeetingTypeResponse)
async def mini_app_admin_add_meeting_type(
    payload: MiniAppMeetingTypeCreateRequest,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppAdminMeetingTypeResponse:
    del admin
    try:
        meeting_type = await use_cases.add_meeting_type(
            name=payload.name,
            allowed_durations_minutes=tuple(payload.allowed_durations_minutes),
            is_fixed_duration=payload.is_fixed_duration,
        )
    except AdminSettingsUseCaseError as error:
        raise _settings_http_error(error) from error
    return _admin_meeting_type_response(meeting_type)


@router.patch("/meeting-types/{meeting_type_id}", response_model=MiniAppOkResponse)
async def mini_app_admin_set_meeting_type_active(
    meeting_type_id: UUID,
    payload: MiniAppMeetingTypeUpdateRequest,
    admin: Annotated[UserProfile, Depends(get_current_mini_app_admin)],
    use_cases: Annotated[AdminSettingsUseCases, Depends(get_admin_settings_use_cases)],
) -> MiniAppOkResponse:
    del admin
    try:
        await use_cases.set_meeting_type_active(meeting_type_id, is_active=payload.is_active)
    except AdminSettingsUseCaseError as error:
        raise _settings_http_error(error) from error
    return MiniAppOkResponse()


def _admin_card_response(card: AdminBookingCard) -> MiniAppAdminBookingCardResponse:
    return MiniAppAdminBookingCardResponse(
        booking=_booking_response(card.booking),
        user=_user_response(card.user),
        meeting_type=MiniAppMeetingTypeResponse(
            id=card.meeting_type.id,
            name=card.meeting_type.name,
            allowed_durations_minutes=list(card.meeting_type.allowed_durations_minutes),
            is_fixed_duration=card.meeting_type.is_fixed_duration,
        ),
    )


def _admin_meeting_type_response(row) -> MiniAppAdminMeetingTypeResponse:
    return MiniAppAdminMeetingTypeResponse(
        id=row.id,
        name=row.name,
        allowed_durations_minutes=list(row.allowed_durations_minutes),
        is_fixed_duration=row.is_fixed_duration,
        is_active=row.is_active,
    )


def _business_http_error(error: BusinessRuleError) -> HTTPException:
    status_code = status.HTTP_409_CONFLICT
    if error.rule.endswith("_not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    return _http_error(status_code, error.rule, str(error))


def _settings_http_error(error: AdminSettingsUseCaseError) -> HTTPException:
    status_code = status.HTTP_409_CONFLICT
    if error.code.endswith("_not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    return _http_error(status_code, error.code, str(error))


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
