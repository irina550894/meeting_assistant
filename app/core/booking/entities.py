import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class BookingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED_BY_USER = "cancelled_by_user"
    EXPIRED = "expired"
    RESCHEDULE_REQUESTED = "reschedule_requested"
    RESCHEDULED = "rescheduled"
    CLOSED_BY_BLOCK = "closed_by_block"
    CALENDAR_CONFLICT = "calendar_conflict"


ACTIVE_BOOKING_STATUSES = {
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.RESCHEDULE_REQUESTED,
}


@dataclass(slots=True)
class UserProfile:
    telegram_id: int
    telegram_username: str | None = None
    full_name: str | None = None
    email: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    is_blocked: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    telegram_username_updated_at: datetime | None = None
    consent_accepted_at: datetime | None = None
    consent_url: str | None = None
    policy_url: str | None = None

    @property
    def has_personal_data_consent(self) -> bool:
        return bool(self.consent_accepted_at and self.consent_url and self.policy_url)


@dataclass(frozen=True, slots=True)
class MeetingType:
    name: str
    allowed_durations_minutes: tuple[int, ...]
    is_fixed_duration: bool = False
    is_active: bool = True
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass(slots=True)
class SlotReservation:
    booking_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    expires_at: datetime
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    released_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.released_at is None


@dataclass(slots=True)
class BookingRecord:
    user_id: uuid.UUID
    meeting_type_id: uuid.UUID
    duration_minutes: int
    starts_at: datetime
    ends_at: datetime
    status: BookingStatus
    created_source: str = "telegram_bot"
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    display_number: int | None = None
    user_comment: str | None = None
    rejection_reason: str | None = None
    cancellation_reason: str | None = None
    reserved_until: datetime | None = None
    google_calendar_event_id: str | None = None
    meeting_url: str | None = None
    is_reschedule_request: bool = False
    previous_booking_id: uuid.UUID | None = None
    reservation: SlotReservation | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_BOOKING_STATUSES


@dataclass(frozen=True, slots=True)
class AuditEntry:
    actor_type: str
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    created_at: datetime
    source: str = "telegram_bot"
    actor_user_id: uuid.UUID | None = None
    payload: dict[str, object] = field(default_factory=dict)
    error_type: str | None = None
    message: str | None = None
