from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Protocol
from uuid import UUID

from app.core.admin_flow import AdminConfirmationResult, AdminFlowService
from app.core.booking import (
    AuditEntry,
    BookingCreationResult,
    BookingRecord,
    BookingService,
    MeetingType,
    UserProfile,
)
from app.core.user_flow import FlowScheduleContext, UserFlowService
from app.settings.config import Settings


class UserStore(Protocol):
    async def get_by_telegram_id(self, telegram_id: int) -> UserProfile | None: ...

    async def get(self, user_id: UUID) -> UserProfile | None: ...

    async def list_blocked(self) -> list[UserProfile]: ...

    async def save(self, user: UserProfile) -> None: ...


class MeetingTypeStore(Protocol):
    async def list_active(self) -> list[MeetingType]: ...

    async def get(self, meeting_type_id: UUID) -> MeetingType | None: ...


class BookingStore(Protocol):
    async def list_all(self) -> list[BookingRecord]: ...

    async def list_pending(self) -> list[BookingRecord]: ...

    async def list_by_user(self, user_id: UUID) -> list[BookingRecord]: ...

    async def get(self, booking_id: UUID) -> BookingRecord | None: ...

    async def get_for_user(self, booking_id: UUID, user_id: UUID) -> BookingRecord | None: ...

    async def save_booking_result(self, result: BookingCreationResult) -> None: ...

    async def save_booking(self, booking: BookingRecord) -> None: ...

    async def save_audit_entries(self, entries: list[AuditEntry]) -> None: ...


class ScheduleProvider(Protocol):
    async def context_for_date(self, target_date: date) -> FlowScheduleContext: ...


class UserFlowNotifier(Protocol):
    async def booking_created(self, booking: BookingRecord) -> None: ...

    async def booking_cancelled_by_user(self, booking: BookingRecord) -> None: ...

    async def reschedule_requested(self, booking: BookingRecord) -> None: ...


class AdminNotifier(Protocol):
    async def booking_confirmed(self, booking: BookingRecord) -> None: ...

    async def booking_rejected(self, booking: BookingRecord, reason: str | None) -> None: ...

    async def user_blocked(self, user: UserProfile) -> None: ...

    async def send_user_message(self, user: UserProfile, text: str) -> None: ...


class CalendarConfirmationGateway(Protocol):
    async def confirm_booking(
        self,
        *,
        booking: BookingRecord,
        user: UserProfile,
        meeting_type: MeetingType,
        meeting_url: str,
    ) -> AdminConfirmationResult: ...


class CalendarEventGateway(Protocol):
    async def cancel_event(self, event_id: str) -> None: ...


class BackgroundJobSchedulerPort(Protocol):
    async def schedule_booking_created(
        self,
        booking: BookingRecord,
        *,
        now: datetime,
    ) -> None: ...

    async def schedule_booking_confirmed(
        self,
        booking: BookingRecord,
        *,
        now: datetime,
    ) -> None: ...


class DiagnosticsProvider(Protocol):
    async def build_report(self): ...


@dataclass(frozen=True, slots=True)
class AdminScheduleSettings:
    timezone: str
    min_booking_lead_days: int
    booking_horizon_days: int
    slot_step_minutes: int
    meeting_buffer_minutes: int


@dataclass(frozen=True, slots=True)
class AdminWorkingHoursRule:
    weekday: int
    is_working_day: bool
    start_time: time | None = None
    end_time: time | None = None


@dataclass(frozen=True, slots=True)
class AdminScheduleRestriction:
    id: UUID
    restriction_date: date
    restriction_type: str
    start_time: time | None = None
    end_time: time | None = None
    admin_comment: str | None = None


@dataclass(frozen=True, slots=True)
class AdminMeetingType:
    id: UUID
    name: str
    allowed_durations_minutes: tuple[int, ...]
    is_fixed_duration: bool
    is_active: bool


class AdminSettingsStore(Protocol):
    async def get_schedule_settings(self) -> AdminScheduleSettings: ...

    async def list_working_hours(self) -> list[AdminWorkingHoursRule]: ...

    async def list_upcoming_restrictions(
        self,
        *,
        from_date: date,
    ) -> list[AdminScheduleRestriction]: ...

    async def add_closed_day_restriction(
        self,
        *,
        restriction_date: date,
        admin_comment: str | None,
    ) -> None: ...

    async def delete_restriction(self, restriction_id: UUID) -> bool: ...

    async def list_meeting_types_admin(self) -> list[AdminMeetingType]: ...

    async def add_meeting_type(
        self,
        *,
        name: str,
        allowed_durations_minutes: tuple[int, ...],
        is_fixed_duration: bool,
    ) -> AdminMeetingType | None: ...

    async def set_meeting_type_active(self, meeting_type_id: UUID, *, is_active: bool) -> bool:
        ...


@dataclass(slots=True)
class UserFlowDependencies:
    settings: Settings
    users: UserStore
    meeting_types: MeetingTypeStore
    bookings: BookingStore
    schedule: ScheduleProvider
    flow: UserFlowService
    booking_service: BookingService
    clock: Callable[[], datetime]
    notifier: UserFlowNotifier | None = None
    calendar_events: CalendarEventGateway | None = None
    background_jobs: BackgroundJobSchedulerPort | None = None


@dataclass(slots=True)
class AdminFlowDependencies:
    settings: Settings
    users: UserStore
    meeting_types: MeetingTypeStore
    bookings: BookingStore
    admin_flow: AdminFlowService
    calendar: CalendarConfirmationGateway
    clock: Callable[[], datetime]
    notifier: AdminNotifier | None = None
    calendar_events: CalendarEventGateway | None = None
    background_jobs: BackgroundJobSchedulerPort | None = None
    diagnostics: DiagnosticsProvider | None = None
    admin_settings: AdminSettingsStore | None = None
