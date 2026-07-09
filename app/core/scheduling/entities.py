from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum


class RestrictionType(StrEnum):
    CLOSED_DAY = "closed_day"
    TIME_INTERVAL = "time_interval"


class BusySource(StrEnum):
    CALENDAR = "calendar"
    RESERVATION = "reservation"
    CONFIRMED_BOOKING = "confirmed_booking"


class SlotExclusionReason(StrEnum):
    OUT_OF_BOOKING_RANGE = "out_of_booking_range"
    NON_WORKING_DAY = "non_working_day"
    CLOSED_DAY = "closed_day"
    OUTSIDE_WORKING_HOURS = "outside_working_hours"
    MANUAL_RESTRICTION = "manual_restriction"
    CALENDAR_BUSY = "calendar_busy"
    ACTIVE_RESERVATION = "active_reservation"
    CONFIRMED_BOOKING = "confirmed_booking"
    INVALID_DURATION = "invalid_duration"
    INVALID_SETTINGS = "invalid_settings"


@dataclass(frozen=True, slots=True)
class ScheduleSettings:
    timezone: str = "Europe/Moscow"
    min_booking_lead_days: int = 1
    booking_horizon_days: int = 30
    slot_step_minutes: int = 30
    meeting_buffer_minutes: int = 90


@dataclass(frozen=True, slots=True)
class WorkingHoursRule:
    weekday: int
    is_working_day: bool
    start_time: time | None = None
    end_time: time | None = None


@dataclass(frozen=True, slots=True)
class ScheduleRestriction:
    restriction_date: date
    restriction_type: RestrictionType
    start_time: time | None = None
    end_time: time | None = None


@dataclass(frozen=True, slots=True)
class BusyInterval:
    starts_at: datetime
    ends_at: datetime
    source: BusySource
    all_day: bool = False


@dataclass(frozen=True, slots=True)
class AvailableSlot:
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class SlotCalculationResult:
    slots: list[AvailableSlot]
    exclusion_counts: dict[SlotExclusionReason, int] = field(default_factory=dict)

    @property
    def public_slots(self) -> list[AvailableSlot]:
        return self.slots
