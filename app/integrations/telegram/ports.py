from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
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
