from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.booking import (
    ACTIVE_BOOKING_STATUSES,
    AuditEntry,
    BookingCreationResult,
    BookingRecord,
    BookingStatus,
    MeetingType,
    SlotReservation,
    UserProfile,
)
from app.core.scheduling import (
    BusyInterval,
    BusySource,
    ScheduleRestriction,
    WorkingHoursRule,
)
from app.core.scheduling import (
    RestrictionType as CoreRestrictionType,
)
from app.core.scheduling import (
    ScheduleSettings as CoreScheduleSettings,
)
from app.core.user_flow import FlowScheduleContext
from app.integrations.telegram.ports import (
    AdminMeetingType,
    AdminScheduleRestriction,
    AdminScheduleSettings,
    AdminWorkingHoursRule,
)
from app.persistence.models import (
    AuditLog,
    Booking,
    User,
    WorkingHours,
)
from app.persistence.models import (
    MeetingType as MeetingTypeModel,
)
from app.persistence.models import (
    ScheduleRestriction as ScheduleRestrictionModel,
)
from app.persistence.models import (
    ScheduleSettings as ScheduleSettingsModel,
)
from app.persistence.models import (
    SlotReservation as SlotReservationModel,
)
from app.settings.config import Settings

SessionFactory = Callable[[], Any]


class SqlAlchemyTelegramRuntimeStore:
    def __init__(self, *, session_factory: SessionFactory, settings: Settings) -> None:
        self.session_factory = session_factory
        self.settings = settings

    async def ensure_seed_data(self) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                if await session.scalar(select(MeetingTypeModel.id).limit(1)) is None:
                    session.add_all(
                        [
                            MeetingTypeModel(
                                name="Консультация",
                                slug="consultation",
                                allowed_durations_minutes=[30, 60, 90],
                                is_fixed_duration=False,
                            ),
                            MeetingTypeModel(
                                name="Диагностика",
                                slug="diagnostics",
                                allowed_durations_minutes=[60],
                                is_fixed_duration=True,
                            ),
                        ]
                    )

                if await session.scalar(select(ScheduleSettingsModel.id).limit(1)) is None:
                    session.add(
                        ScheduleSettingsModel(
                            timezone=self.settings.app_timezone,
                            min_booking_lead_days=self.settings.min_booking_lead_days,
                            booking_horizon_days=self.settings.booking_horizon_days,
                            slot_step_minutes=self.settings.slot_step_minutes,
                            meeting_buffer_minutes=self.settings.meeting_buffer_minutes,
                            default_meeting_url=self.settings.default_meeting_url,
                            personal_data_consent_url=self.settings.personal_data_consent_url,
                            personal_data_policy_url=self.settings.personal_data_policy_url,
                        )
                    )

                if await session.scalar(select(WorkingHours.id).limit(1)) is None:
                    session.add_all(_default_working_hours_models())

    async def get_by_telegram_id(self, telegram_id: int) -> UserProfile | None:
        async with self.session_factory() as session:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            return _user_profile(user) if user else None

    async def get(self, entity_id: UUID) -> UserProfile | BookingRecord | MeetingType | None:
        async with self.session_factory() as session:
            user = await session.get(User, entity_id)
            if user is not None:
                return _user_profile(user)

            booking = await _get_booking_model(session, entity_id)
            if booking is not None:
                return _booking_record(booking)

            meeting_type = await session.get(MeetingTypeModel, entity_id)
            if meeting_type is not None:
                return _meeting_type(meeting_type)
        return None

    async def list_blocked(self) -> list[UserProfile]:
        async with self.session_factory() as session:
            users = await session.scalars(
                select(User).where(User.is_blocked.is_(True)).order_by(User.created_at)
            )
            return [_user_profile(user) for user in users]

    async def save(self, user: UserProfile) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                model = await session.get(User, user.id)
                if model is None:
                    model = User(id=user.id, telegram_id=user.telegram_id)
                    session.add(model)
                _apply_user_fields(model, user)

    async def list_active(self) -> list[MeetingType]:
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(MeetingTypeModel)
                .where(MeetingTypeModel.is_active.is_(True))
                .order_by(MeetingTypeModel.name)
            )
            return [_meeting_type(row) for row in rows]

    async def list_all(self) -> list[BookingRecord]:
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(Booking)
                .options(selectinload(Booking.reservation))
                .order_by(Booking.created_at)
            )
            return [_booking_record(row) for row in rows]

    async def list_pending(self) -> list[BookingRecord]:
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(Booking)
                .options(selectinload(Booking.reservation))
                .where(Booking.status == BookingStatus.PENDING.value)
                .order_by(Booking.created_at)
            )
            return [_booking_record(row) for row in rows]

    async def list_by_user(self, user_id: UUID) -> list[BookingRecord]:
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(Booking)
                .options(selectinload(Booking.reservation))
                .where(Booking.user_id == user_id)
                .order_by(Booking.created_at)
            )
            return [_booking_record(row) for row in rows]

    async def get_for_user(self, booking_id: UUID, user_id: UUID) -> BookingRecord | None:
        booking = await self.get(booking_id)
        if isinstance(booking, BookingRecord) and booking.user_id == user_id:
            return booking
        return None

    async def save_booking_result(self, result: BookingCreationResult) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                if result.booking.previous_booking_id is not None:
                    await _mark_previous_booking_reschedule_requested(
                        session,
                        result.booking.previous_booking_id,
                        now=result.booking.updated_at or result.booking.created_at,
                    )
                model = await _upsert_booking(session, result.booking)
                await _upsert_reservation(session, result.reservation)
                await _insert_audit_entries(session, result.audit_entries)
                await session.flush()
                result.booking.display_number = model.display_number

    async def save_booking(self, booking: BookingRecord) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                model = await _upsert_booking(session, booking)
                if booking.reservation is not None:
                    await _upsert_reservation(session, booking.reservation)
                await session.flush()
                booking.display_number = model.display_number

    async def save_audit_entries(self, entries: list[AuditEntry]) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await _insert_audit_entries(session, entries)

    async def context_for_date(self, target_date: date) -> FlowScheduleContext:
        async with self.session_factory() as session:
            settings = await _schedule_settings(session, self.settings)
            working_hours = await _working_hours(session)
            restrictions = await _schedule_restrictions(session, target_date)
            busy_intervals = await _busy_intervals(session, settings, target_date)
        return FlowScheduleContext(
            settings=settings,
            working_hours=working_hours,
            restrictions=restrictions,
            busy_intervals=busy_intervals,
        )

    async def get_schedule_settings(self) -> AdminScheduleSettings:
        async with self.session_factory() as session:
            settings = await _schedule_settings(session, self.settings)
        return AdminScheduleSettings(
            timezone=settings.timezone,
            min_booking_lead_days=settings.min_booking_lead_days,
            booking_horizon_days=settings.booking_horizon_days,
            slot_step_minutes=settings.slot_step_minutes,
            meeting_buffer_minutes=settings.meeting_buffer_minutes,
        )

    async def list_working_hours(self) -> list[AdminWorkingHoursRule]:
        async with self.session_factory() as session:
            rows = await _working_hours(session)
        return [
            AdminWorkingHoursRule(
                weekday=row.weekday,
                is_working_day=row.is_working_day,
                start_time=row.start_time,
                end_time=row.end_time,
            )
            for row in rows
        ]

    async def list_upcoming_restrictions(
        self,
        *,
        from_date: date,
    ) -> list[AdminScheduleRestriction]:
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(ScheduleRestrictionModel)
                .where(ScheduleRestrictionModel.restriction_date >= from_date)
                .order_by(ScheduleRestrictionModel.restriction_date)
                .limit(20)
            )
            return [_admin_restriction(row) for row in rows]

    async def add_closed_day_restriction(
        self,
        *,
        restriction_date: date,
        admin_comment: str | None,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                session.add(
                    ScheduleRestrictionModel(
                        restriction_type=CoreRestrictionType.CLOSED_DAY.value,
                        restriction_date=restriction_date,
                        admin_comment=admin_comment,
                    )
                )

    async def add_time_interval_restriction(
        self,
        *,
        restriction_date: date,
        start_time: time,
        end_time: time,
        admin_comment: str | None,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                session.add(
                    ScheduleRestrictionModel(
                        restriction_type=CoreRestrictionType.TIME_INTERVAL.value,
                        restriction_date=restriction_date,
                        start_time=start_time,
                        end_time=end_time,
                        admin_comment=admin_comment,
                    )
                )

    async def delete_restriction(self, restriction_id: UUID) -> bool:
        async with self.session_factory() as session:
            async with session.begin():
                restriction = await session.get(ScheduleRestrictionModel, restriction_id)
                if restriction is None:
                    return False
                await session.delete(restriction)
                return True

    async def list_meeting_types_admin(self) -> list[AdminMeetingType]:
        async with self.session_factory() as session:
            rows = await session.scalars(select(MeetingTypeModel).order_by(MeetingTypeModel.name))
            return [_admin_meeting_type(row) for row in rows]

    async def add_meeting_type(
        self,
        *,
        name: str,
        allowed_durations_minutes: tuple[int, ...],
        is_fixed_duration: bool,
    ) -> AdminMeetingType | None:
        async with self.session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(MeetingTypeModel).where(MeetingTypeModel.name == name)
                )
                if existing is not None:
                    return None
                meeting_type = MeetingTypeModel(
                    name=name,
                    slug=f"custom-{uuid4().hex[:16]}",
                    allowed_durations_minutes=list(allowed_durations_minutes),
                    is_fixed_duration=is_fixed_duration,
                    is_active=True,
                )
                session.add(meeting_type)
            return _admin_meeting_type(meeting_type)

    async def set_meeting_type_active(self, meeting_type_id: UUID, *, is_active: bool) -> bool:
        async with self.session_factory() as session:
            async with session.begin():
                meeting_type = await session.get(MeetingTypeModel, meeting_type_id)
                if meeting_type is None:
                    return False
                meeting_type.is_active = is_active
                return True


async def _get_booking_model(session: AsyncSession, booking_id: UUID) -> Booking | None:
    return await session.scalar(
        select(Booking)
        .options(selectinload(Booking.reservation))
        .where(Booking.id == booking_id)
    )


def _apply_user_fields(model: User, user: UserProfile) -> None:
    model.telegram_id = user.telegram_id
    model.telegram_username = user.telegram_username
    model.full_name = user.full_name
    model.email = user.email
    model.is_blocked = user.is_blocked
    model.telegram_username_updated_at = user.telegram_username_updated_at
    model.consent_accepted_at = user.consent_accepted_at
    model.consent_url = user.consent_url
    model.policy_url = user.policy_url
    if user.created_at is not None:
        model.created_at = user.created_at
    if user.updated_at is not None:
        model.updated_at = user.updated_at


async def _upsert_booking(session: AsyncSession, booking: BookingRecord) -> Booking:
    model = await session.get(Booking, booking.id)
    if model is None:
        model = Booking(id=booking.id)
        session.add(model)
    if booking.display_number is not None:
        model.display_number = booking.display_number
    model.user_id = booking.user_id
    model.meeting_type_id = booking.meeting_type_id
    model.duration_minutes = booking.duration_minutes
    model.starts_at = booking.starts_at
    model.ends_at = booking.ends_at
    model.user_comment = booking.user_comment
    model.status = booking.status.value
    model.created_source = booking.created_source
    model.rejection_reason = booking.rejection_reason
    model.cancellation_reason = booking.cancellation_reason
    model.reserved_until = booking.reserved_until
    model.google_calendar_event_id = booking.google_calendar_event_id
    model.meeting_url = booking.meeting_url
    model.is_reschedule_request = booking.is_reschedule_request
    model.previous_booking_id = booking.previous_booking_id
    if booking.created_at is not None:
        model.created_at = booking.created_at
    if booking.updated_at is not None:
        model.updated_at = booking.updated_at
    return model


async def _upsert_reservation(session: AsyncSession, reservation: SlotReservation) -> None:
    model = await session.get(SlotReservationModel, reservation.id)
    if model is None:
        model = SlotReservationModel(id=reservation.id)
        session.add(model)
    model.booking_id = reservation.booking_id
    model.starts_at = reservation.starts_at
    model.ends_at = reservation.ends_at
    model.expires_at = reservation.expires_at
    model.released_at = reservation.released_at


async def _mark_previous_booking_reschedule_requested(
    session: AsyncSession,
    booking_id: UUID,
    *,
    now: datetime | None,
) -> None:
    previous = await session.get(Booking, booking_id)
    if previous is None:
        return
    previous.status = BookingStatus.RESCHEDULE_REQUESTED.value
    if now is not None:
        previous.updated_at = now


async def _insert_audit_entries(session: AsyncSession, entries: list[AuditEntry]) -> None:
    for entry in entries:
        session.add(
            AuditLog(
                actor_type=entry.actor_type,
                actor_user_id=entry.actor_user_id,
                action=entry.action,
                source=entry.source,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                payload=entry.payload,
                created_at=entry.created_at,
                error_type=entry.error_type,
                message=entry.message,
            )
        )


async def _schedule_settings(
    session: AsyncSession,
    settings: Settings,
) -> CoreScheduleSettings:
    row = await session.scalar(select(ScheduleSettingsModel).order_by(ScheduleSettingsModel.id))
    if row is None:
        return CoreScheduleSettings(
            timezone=settings.app_timezone,
            min_booking_lead_days=settings.min_booking_lead_days,
            booking_horizon_days=settings.booking_horizon_days,
            slot_step_minutes=settings.slot_step_minutes,
            meeting_buffer_minutes=settings.meeting_buffer_minutes,
        )
    return CoreScheduleSettings(
        timezone=row.timezone,
        min_booking_lead_days=row.min_booking_lead_days,
        booking_horizon_days=row.booking_horizon_days,
        slot_step_minutes=row.slot_step_minutes,
        meeting_buffer_minutes=row.meeting_buffer_minutes,
    )


async def _working_hours(session: AsyncSession) -> list[WorkingHoursRule]:
    rows = list(await session.scalars(select(WorkingHours).order_by(WorkingHours.weekday)))
    if not rows:
        return _default_working_hours_rules()
    return [
        WorkingHoursRule(
            weekday=row.weekday,
            is_working_day=row.is_working_day,
            start_time=row.start_time,
            end_time=row.end_time,
        )
        for row in rows
    ]


async def _schedule_restrictions(
    session: AsyncSession,
    target_date: date,
) -> list[ScheduleRestriction]:
    rows = await session.scalars(
        select(ScheduleRestrictionModel).where(
            ScheduleRestrictionModel.restriction_date == target_date
        )
    )
    return [
        ScheduleRestriction(
            restriction_date=row.restriction_date,
            restriction_type=CoreRestrictionType(row.restriction_type),
            start_time=row.start_time,
            end_time=row.end_time,
        )
        for row in rows
    ]


async def _busy_intervals(
    session: AsyncSession,
    settings: CoreScheduleSettings,
    target_date: date,
) -> list[BusyInterval]:
    timezone = ZoneInfo(settings.timezone)
    day_start = datetime.combine(target_date, time.min, tzinfo=timezone)
    day_end = datetime.combine(target_date, time.max, tzinfo=timezone)
    intervals: list[BusyInterval] = []

    confirmed = await session.scalars(
        select(Booking).where(
            Booking.status == BookingStatus.CONFIRMED.value,
            Booking.starts_at < day_end,
            Booking.ends_at > day_start,
        )
    )
    intervals.extend(
        BusyInterval(
            starts_at=booking.starts_at,
            ends_at=booking.ends_at,
            source=BusySource.CONFIRMED_BOOKING,
        )
        for booking in confirmed
    )

    reservations = await session.scalars(
        select(SlotReservationModel)
        .join(Booking, Booking.id == SlotReservationModel.booking_id)
        .where(
            Booking.status.in_([status.value for status in ACTIVE_BOOKING_STATUSES]),
            Booking.status != BookingStatus.CONFIRMED.value,
            SlotReservationModel.released_at.is_(None),
            SlotReservationModel.starts_at < day_end,
            SlotReservationModel.ends_at > day_start,
        )
    )
    intervals.extend(
        BusyInterval(
            starts_at=reservation.starts_at,
            ends_at=reservation.ends_at,
            source=BusySource.RESERVATION,
        )
        for reservation in reservations
    )
    return intervals


def _user_profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        full_name=user.full_name,
        email=user.email,
        is_blocked=user.is_blocked,
        created_at=user.created_at,
        updated_at=user.updated_at,
        telegram_username_updated_at=user.telegram_username_updated_at,
        consent_accepted_at=user.consent_accepted_at,
        consent_url=user.consent_url,
        policy_url=user.policy_url,
    )


def _meeting_type(meeting_type: MeetingTypeModel) -> MeetingType:
    return MeetingType(
        id=meeting_type.id,
        name=meeting_type.name,
        allowed_durations_minutes=tuple(meeting_type.allowed_durations_minutes),
        is_fixed_duration=meeting_type.is_fixed_duration,
        is_active=meeting_type.is_active,
    )


def _admin_meeting_type(meeting_type: MeetingTypeModel) -> AdminMeetingType:
    return AdminMeetingType(
        id=meeting_type.id,
        name=meeting_type.name,
        allowed_durations_minutes=tuple(meeting_type.allowed_durations_minutes),
        is_fixed_duration=meeting_type.is_fixed_duration,
        is_active=meeting_type.is_active,
    )


def _admin_restriction(restriction: ScheduleRestrictionModel) -> AdminScheduleRestriction:
    return AdminScheduleRestriction(
        id=restriction.id,
        restriction_date=restriction.restriction_date,
        restriction_type=restriction.restriction_type,
        start_time=restriction.start_time,
        end_time=restriction.end_time,
        admin_comment=restriction.admin_comment,
    )


def _booking_record(booking: Booking) -> BookingRecord:
    reservation = _reservation_record(booking.reservation) if booking.reservation else None
    return BookingRecord(
        id=booking.id,
        display_number=booking.display_number,
        user_id=booking.user_id,
        meeting_type_id=booking.meeting_type_id,
        duration_minutes=booking.duration_minutes,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        status=BookingStatus(booking.status),
        created_source=booking.created_source,
        user_comment=booking.user_comment,
        rejection_reason=booking.rejection_reason,
        cancellation_reason=booking.cancellation_reason,
        reserved_until=booking.reserved_until,
        google_calendar_event_id=booking.google_calendar_event_id,
        meeting_url=booking.meeting_url,
        is_reschedule_request=booking.is_reschedule_request,
        previous_booking_id=booking.previous_booking_id,
        reservation=reservation,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )


def _reservation_record(reservation: SlotReservationModel) -> SlotReservation:
    return SlotReservation(
        id=reservation.id,
        booking_id=reservation.booking_id,
        starts_at=reservation.starts_at,
        ends_at=reservation.ends_at,
        expires_at=reservation.expires_at,
        released_at=reservation.released_at,
    )


def _default_working_hours_rules() -> list[WorkingHoursRule]:
    return [
        WorkingHoursRule(
            weekday=weekday,
            is_working_day=weekday < 5,
            start_time=time(10, 0) if weekday < 5 else None,
            end_time=time(18, 0) if weekday < 5 else None,
        )
        for weekday in range(7)
    ]


def _default_working_hours_models() -> list[WorkingHours]:
    return [
        WorkingHours(
            weekday=rule.weekday,
            is_working_day=rule.is_working_day,
            start_time=rule.start_time,
            end_time=rule.end_time,
        )
        for rule in _default_working_hours_rules()
    ]
