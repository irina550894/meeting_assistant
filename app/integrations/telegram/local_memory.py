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
    RestrictionType,
    ScheduleRestriction,
    ScheduleSettings,
    WorkingHoursRule,
)
from app.core.user_flow import FlowScheduleContext
from app.integrations.telegram.ports import (
    AdminMeetingType,
    AdminScheduleRestriction,
    AdminScheduleSettings,
    AdminWorkingHoursRule,
)
from app.settings.config import Settings


class InMemoryRuntimeStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users_by_id: dict[UUID, UserProfile] = {}
        self.users_by_telegram_id: dict[int, UserProfile] = {}
        self.bookings: dict[UUID, BookingRecord] = {}
        self.audit_entries: list[AuditEntry] = []
        self.meeting_types: dict[UUID, MeetingType] = {}
        self.restrictions: dict[UUID, AdminScheduleRestriction] = {}
        self.next_booking_display_number = 1
        self.schedule_settings = AdminScheduleSettings(
            timezone=self.settings.app_timezone,
            min_booking_lead_days=self.settings.min_booking_lead_days,
            booking_horizon_days=self.settings.booking_horizon_days,
            slot_step_minutes=self.settings.slot_step_minutes,
            meeting_buffer_minutes=self.settings.meeting_buffer_minutes,
        )
        self.working_hours = {
            rule.weekday: rule for rule in self._default_working_hours()
        }
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
        self._ensure_booking_display_number(result.booking)
        self.bookings[result.booking.id] = result.booking
        self.audit_entries.extend(result.audit_entries)

    async def save_booking(self, booking: BookingRecord) -> None:
        self._ensure_booking_display_number(booking)
        self.bookings[booking.id] = booking

    async def save_audit_entries(self, entries: list[AuditEntry]) -> None:
        self.audit_entries.extend(entries)

    def _ensure_booking_display_number(self, booking: BookingRecord) -> None:
        if booking.display_number is not None:
            self.next_booking_display_number = max(
                self.next_booking_display_number,
                booking.display_number + 1,
            )
            return
        booking.display_number = self.next_booking_display_number
        self.next_booking_display_number += 1

    async def context_for_date(self, target_date: date) -> FlowScheduleContext:
        return FlowScheduleContext(
            settings=ScheduleSettings(
                timezone=self.schedule_settings.timezone,
                min_booking_lead_days=self.schedule_settings.min_booking_lead_days,
                booking_horizon_days=self.schedule_settings.booking_horizon_days,
                slot_step_minutes=self.schedule_settings.slot_step_minutes,
                meeting_buffer_minutes=self.schedule_settings.meeting_buffer_minutes,
            ),
            working_hours=list(self.working_hours.values()),
            restrictions=[
                ScheduleRestriction(
                    restriction_date=restriction.restriction_date,
                    restriction_type=RestrictionType(restriction.restriction_type),
                    start_time=restriction.start_time,
                    end_time=restriction.end_time,
                )
                for restriction in self.restrictions.values()
                if restriction.restriction_date == target_date
            ],
            busy_intervals=self._busy_intervals_for_date(target_date),
        )

    async def get_schedule_settings(self) -> AdminScheduleSettings:
        return self.schedule_settings

    async def update_schedule_settings(
        self,
        *,
        booking_horizon_days: int,
        slot_step_minutes: int,
        meeting_buffer_minutes: int,
    ) -> AdminScheduleSettings:
        self.schedule_settings = AdminScheduleSettings(
            timezone=self.schedule_settings.timezone,
            min_booking_lead_days=self.schedule_settings.min_booking_lead_days,
            booking_horizon_days=booking_horizon_days,
            slot_step_minutes=slot_step_minutes,
            meeting_buffer_minutes=meeting_buffer_minutes,
        )
        return self.schedule_settings

    async def list_working_hours(self) -> list[AdminWorkingHoursRule]:
        return [
            AdminWorkingHoursRule(
                weekday=rule.weekday,
                is_working_day=rule.is_working_day,
                start_time=rule.start_time,
                end_time=rule.end_time,
            )
            for rule in sorted(self.working_hours.values(), key=lambda item: item.weekday)
        ]

    async def update_working_hours(
        self,
        *,
        weekday: int,
        is_working_day: bool,
        start_time: time | None,
        end_time: time | None,
    ) -> AdminWorkingHoursRule:
        row = AdminWorkingHoursRule(
            weekday=weekday,
            is_working_day=is_working_day,
            start_time=start_time,
            end_time=end_time,
        )
        self.working_hours[weekday] = row
        return row

    async def list_upcoming_restrictions(
        self,
        *,
        from_date: date,
    ) -> list[AdminScheduleRestriction]:
        return sorted(
            [
                restriction
                for restriction in self.restrictions.values()
                if restriction.restriction_date >= from_date
            ],
            key=lambda restriction: restriction.restriction_date,
        )

    async def add_closed_day_restriction(
        self,
        *,
        restriction_date: date,
        admin_comment: str | None,
    ) -> None:
        restriction = AdminScheduleRestriction(
            id=UUID(int=len(self.restrictions) + 1),
            restriction_date=restriction_date,
            restriction_type="closed_day",
            admin_comment=admin_comment,
        )
        self.restrictions[restriction.id] = restriction

    async def add_time_interval_restriction(
        self,
        *,
        restriction_date: date,
        start_time: time,
        end_time: time,
        admin_comment: str | None,
    ) -> None:
        restriction = AdminScheduleRestriction(
            id=UUID(int=len(self.restrictions) + 1),
            restriction_date=restriction_date,
            restriction_type="time_interval",
            start_time=start_time,
            end_time=end_time,
            admin_comment=admin_comment,
        )
        self.restrictions[restriction.id] = restriction

    async def delete_restriction(self, restriction_id: UUID) -> bool:
        return self.restrictions.pop(restriction_id, None) is not None

    async def list_meeting_types_admin(self) -> list[AdminMeetingType]:
        return [
            AdminMeetingType(
                id=meeting_type.id,
                name=meeting_type.name,
                allowed_durations_minutes=meeting_type.allowed_durations_minutes,
                is_fixed_duration=meeting_type.is_fixed_duration,
                is_active=meeting_type.is_active,
            )
            for meeting_type in sorted(self.meeting_types.values(), key=lambda item: item.name)
        ]

    async def add_meeting_type(
        self,
        *,
        name: str,
        allowed_durations_minutes: tuple[int, ...],
        is_fixed_duration: bool,
    ) -> AdminMeetingType | None:
        if any(item.name == name for item in self.meeting_types.values()):
            return None
        meeting_type = MeetingType(
            name=name,
            allowed_durations_minutes=allowed_durations_minutes,
            is_fixed_duration=is_fixed_duration,
        )
        self.meeting_types[meeting_type.id] = meeting_type
        return AdminMeetingType(
            id=meeting_type.id,
            name=meeting_type.name,
            allowed_durations_minutes=meeting_type.allowed_durations_minutes,
            is_fixed_duration=meeting_type.is_fixed_duration,
            is_active=meeting_type.is_active,
        )

    async def set_meeting_type_active(self, meeting_type_id: UUID, *, is_active: bool) -> bool:
        meeting_type = self.meeting_types.get(meeting_type_id)
        if meeting_type is None:
            return False
        self.meeting_types[meeting_type_id] = MeetingType(
            id=meeting_type.id,
            name=meeting_type.name,
            allowed_durations_minutes=meeting_type.allowed_durations_minutes,
            is_fixed_duration=meeting_type.is_fixed_duration,
            is_active=is_active,
        )
        return True

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
