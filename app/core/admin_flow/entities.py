from dataclasses import dataclass

from app.core.booking import BookingRecord, MeetingType, UserProfile


@dataclass(frozen=True, slots=True)
class AdminBookingCard:
    booking: BookingRecord
    user: UserProfile
    meeting_type: MeetingType


@dataclass(frozen=True, slots=True)
class AdminConfirmationResult:
    google_calendar_event_id: str
    meeting_url: str
