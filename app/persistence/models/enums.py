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


class RestrictionType(StrEnum):
    CLOSED_DAY = "closed_day"
    TIME_INTERVAL = "time_interval"


class BackgroundJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundJobType(StrEnum):
    BOOKING_TTL = "booking_ttl"
    TELEGRAM_REMINDER = "telegram_reminder"
    INTEGRATION_RETRY = "integration_retry"
    AUDIT_LOG_CLEANUP = "audit_log_cleanup"
    GOOGLE_EVENT_CHECK = "google_event_check"


class NotificationChannel(StrEnum):
    TELEGRAM = "telegram"
    GOOGLE_CALENDAR_EMAIL = "google_calendar_email"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class AuditActorType(StrEnum):
    ADMIN = "admin"
    USER = "user"
    SYSTEM = "system"
