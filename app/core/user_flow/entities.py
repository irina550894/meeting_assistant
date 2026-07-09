import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.core.scheduling import BusyInterval, ScheduleRestriction, ScheduleSettings, WorkingHoursRule


class UserFlowStep(StrEnum):
    CONSENT = "consent"
    MENU = "menu"
    NAME = "name"
    EMAIL = "email"
    MEETING_TYPE = "meeting_type"
    DURATION = "duration"
    DATE = "date"
    TIME = "time"
    COMMENT = "comment"
    REVIEW = "review"
    MY_BOOKINGS = "my_bookings"
    CANCEL_CONFIRMATION = "cancel_confirmation"


@dataclass(slots=True)
class BookingDraft:
    full_name: str | None = None
    email: str | None = None
    meeting_type_id: uuid.UUID | None = None
    duration_minutes: int | None = None
    selected_date: date | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    user_comment: str | None = None
    previous_booking_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class FlowScheduleContext:
    settings: ScheduleSettings
    working_hours: list[WorkingHoursRule]
    restrictions: list[ScheduleRestriction]
    busy_intervals: list[BusyInterval]
