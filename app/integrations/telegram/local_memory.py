from datetime import date, datetime, time
from uuid import UUID

from app.core.admin_flow import AdminConfirmationResult
from app.core.booking import (
    ACTIVE_BOOKING_STATUSES,
    AuditEntry,
    BookingCreationResult,
    BookingRecord,
    BookingStatus,
    MeetingType,
    UserProfile,
)
from app.core.scheduling import (
    BusyInterval,
    BusySource,
    ScheduleSettings,
    WorkingHoursRule,
)
from app.core.user_flow import FlowScheduleContext
from app.settings.config import Settings


class InMemoryRuntimeStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users_by_id: dict[UUID, UserProfile] = {}
        self.users_by_telegram_id: dict[int, UserProfile] = {}
        self.bookings: dict[UUID, BookingRecord] = {}
        self.audit_entries: list[AuditEntry] = []
        self.meeting_types: dict[UUID, MeetingType] = {}
        self._seed_meeting_types()

    async def get_by_telegram_id(self, telegram_id: int) -> UserProfile | None:
        return self.users_by_telegram_id.get(telegram_id)

    async def get(self, entity_id: UUID) -> UserProfile | BookingRecord | MeetingType | None:
        return (
            self.users_by_id.get(entity_id)
            or self.bookings.get(entity_id)
            or self.meeting_types.get(entity_id)
        )

    async def list_blocked(self) -> list[UserProfile]:
        return [user for user in self.users_by_id.values() if user.is_blocked]

    async def save(self, user: UserProfile) -> None:
        self.users_by_id[user.id] = user
        self.users_by_telegram_id[user.telegram_id] = user

    async def list_active(self) -> list[MeetingType]:
        return [item for item in self.meeting_types.values() if item.is_active]

    async def list_all(self) -> list[BookingRecord]:
        return sorted(
            self.bookings.values(),
            key=lambda booking: booking.created_at or datetime.min,
        )

    async def list_pending(self) -> list[BookingRecord]:
        return [
            booking
            for booking in await self.list_all()
            if booking.status == BookingStatus.PENDING
        ]

    async def list_by_user(self, user_id: UUID) -> list[BookingRecord]:
        return [
            booking
            for booking in await self.list_all()
            if booking.user_id == user_id
        ]

    async def get_for_user(self, booking_id: UUID, user_id: UUID) -> BookingRecord | None:
        booking = self.bookings.get(booking_id)
        if booking and booking.user_id == user_id:
            return booking
        return None

    async def save_booking_result(self, result: BookingCreationResult) -> None:
        self.bookings[result.booking.id] = result.booking
        self.audit_entries.extend(result.audit_entries)

    async def save_booking(self, booking: BookingRecord) -> None:
        self.bookings[booking.id] = booking

    async def save_audit_entries(self, entries: list[AuditEntry]) -> None:
        self.audit_entries.extend(entries)

    async def context_for_date(self, target_date: date) -> FlowScheduleContext:
        return FlowScheduleContext(
            settings=ScheduleSettings(
                timezone=self.settings.app_timezone,
                min_booking_lead_days=self.settings.min_booking_lead_days,
                booking_horizon_days=self.settings.booking_horizon_days,
                slot_step_minutes=self.settings.slot_step_minutes,
                meeting_buffer_minutes=self.settings.meeting_buffer_minutes,
            ),
            working_hours=self._default_working_hours(),
            restrictions=[],
            busy_intervals=self._busy_intervals_for_date(target_date),
        )

    def _seed_meeting_types(self) -> None:
        consultation = MeetingType(
            name="Консультация",
            allowed_durations_minutes=(30, 60, 90),
        )
        diagnostics = MeetingType(
            name="Диагностика",
            allowed_durations_minutes=(60,),
            is_fixed_duration=True,
        )
        self.meeting_types[consultation.id] = consultation
        self.meeting_types[diagnostics.id] = diagnostics

    def _default_working_hours(self) -> list[WorkingHoursRule]:
        return [
            WorkingHoursRule(
                weekday=weekday,
                is_working_day=weekday < 5,
                start_time=time(10, 0) if weekday < 5 else None,
                end_time=time(18, 0) if weekday < 5 else None,
            )
            for weekday in range(7)
        ]

    def _busy_intervals_for_date(self, target_date: date) -> list[BusyInterval]:
        intervals: list[BusyInterval] = []
        for booking in self.bookings.values():
            if booking.starts_at.date() != target_date:
                continue
            if booking.status == BookingStatus.CONFIRMED:
                intervals.append(
                    BusyInterval(
                        starts_at=booking.starts_at,
                        ends_at=booking.ends_at,
                        source=BusySource.CONFIRMED_BOOKING,
                    )
                )
            elif booking.status in ACTIVE_BOOKING_STATUSES and booking.reservation:
                intervals.append(
                    BusyInterval(
                        starts_at=booking.reservation.starts_at,
                        ends_at=booking.reservation.ends_at,
                        source=BusySource.RESERVATION,
                    )
                )
        return intervals


class LocalCalendarConfirmationGateway:
    async def confirm_booking(
        self,
        *,
        booking: BookingRecord,
        user: UserProfile,
        meeting_type: MeetingType,
        meeting_url: str,
    ) -> AdminConfirmationResult:
        return AdminConfirmationResult(
            google_calendar_event_id=f"local-{booking.id}",
            meeting_url=meeting_url,
        )
