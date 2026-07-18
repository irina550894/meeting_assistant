from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field


class MiniAppAuthRequest(BaseModel):
    init_data: str


class MiniAppUserResponse(BaseModel):
    id: UUID
    telegram_id: int
    telegram_username: str | None
    full_name: str | None
    email: str | None
    has_consent: bool
    is_blocked: bool
    is_admin: bool


class MiniAppAuthResponse(BaseModel):
    user: MiniAppUserResponse
    session_expires_at: datetime


class MiniAppConfigResponse(BaseModel):
    timezone: str
    consent_url: str | None
    policy_url: str | None
    mini_app_public_path: str


class MiniAppConsentRequest(BaseModel):
    accepted: bool


class MiniAppConsentResponse(BaseModel):
    has_consent: bool
    accepted_at: datetime | None


class MiniAppMeetingTypeResponse(BaseModel):
    id: UUID
    name: str
    allowed_durations_minutes: list[int]
    is_fixed_duration: bool


class MiniAppMeetingTypesResponse(BaseModel):
    items: list[MiniAppMeetingTypeResponse]


class MiniAppAvailableDateResponse(BaseModel):
    date: date


class MiniAppAvailableDatesResponse(BaseModel):
    items: list[MiniAppAvailableDateResponse]


class MiniAppSlotResponse(BaseModel):
    starts_at: datetime
    ends_at: datetime
    label: str


class MiniAppSlotsResponse(BaseModel):
    items: list[MiniAppSlotResponse]


class MiniAppBookingCreateRequest(BaseModel):
    full_name: str
    email: str
    meeting_type_id: UUID
    duration_minutes: int
    starts_at: datetime
    ends_at: datetime
    user_comment: str | None = None
    previous_booking_id: UUID | None = None


class MiniAppBookingResponse(BaseModel):
    id: UUID
    display_number: int | None
    status: str
    meeting_type_id: UUID
    duration_minutes: int
    starts_at: datetime
    ends_at: datetime
    user_comment: str | None
    rejection_reason: str | None
    cancellation_reason: str | None
    reserved_until: datetime | None
    meeting_url: str | None
    is_reschedule_request: bool
    previous_booking_id: UUID | None
    created_at: datetime | None
    updated_at: datetime | None


class MiniAppBookingDetailResponse(BaseModel):
    booking: MiniAppBookingResponse


class MiniAppBookingsResponse(BaseModel):
    items: list[MiniAppBookingResponse]


class MiniAppBookingCancelRequest(BaseModel):
    reason: str | None = None


class MiniAppAdminBookingCardResponse(BaseModel):
    booking: MiniAppBookingResponse
    user: MiniAppUserResponse
    meeting_type: MiniAppMeetingTypeResponse


class MiniAppAdminBookingsResponse(BaseModel):
    items: list[MiniAppAdminBookingCardResponse]


class MiniAppAdminDashboardMetricsResponse(BaseModel):
    pending: int
    confirmed: int
    reschedule_requested: int
    cancelled: int


class MiniAppAdminDashboardResponse(BaseModel):
    metrics: MiniAppAdminDashboardMetricsResponse
    upcoming: list[MiniAppBookingResponse]
    recent_pending: list[MiniAppBookingResponse]


class MiniAppAdminConfirmRequest(BaseModel):
    meeting_url: str | None = None


class MiniAppAdminRejectRequest(BaseModel):
    reason: str | None = None


class MiniAppScheduleSettingsResponse(BaseModel):
    timezone: str
    min_booking_lead_days: int
    booking_horizon_days: int
    slot_step_minutes: int
    meeting_buffer_minutes: int


class MiniAppWorkingHoursResponse(BaseModel):
    weekday: int
    is_working_day: bool
    start_time: time | None
    end_time: time | None


class MiniAppWorkingHoursListResponse(BaseModel):
    items: list[MiniAppWorkingHoursResponse]


class MiniAppScheduleRestrictionResponse(BaseModel):
    id: UUID
    restriction_date: date
    restriction_type: str
    start_time: time | None
    end_time: time | None
    admin_comment: str | None


class MiniAppScheduleRestrictionsResponse(BaseModel):
    items: list[MiniAppScheduleRestrictionResponse]


class MiniAppClosedDayRestrictionCreateRequest(BaseModel):
    restriction_date: date
    admin_comment: str | None = None


class MiniAppTimeIntervalRestrictionCreateRequest(BaseModel):
    restriction_date: date
    start_time: time
    end_time: time
    admin_comment: str | None = None


class MiniAppAdminMeetingTypeResponse(BaseModel):
    id: UUID
    name: str
    allowed_durations_minutes: list[int]
    is_fixed_duration: bool
    is_active: bool


class MiniAppAdminMeetingTypesResponse(BaseModel):
    items: list[MiniAppAdminMeetingTypeResponse]


class MiniAppMeetingTypeCreateRequest(BaseModel):
    name: str
    allowed_durations_minutes: list[int]
    is_fixed_duration: bool = False


class MiniAppMeetingTypeUpdateRequest(BaseModel):
    is_active: bool


class MiniAppOkResponse(BaseModel):
    ok: bool = True


class MiniAppAnalyticsEventRequest(BaseModel):
    event_name: str
    payload: dict = Field(default_factory=dict)
