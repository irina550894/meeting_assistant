from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core.booking.entities import (
    ACTIVE_BOOKING_STATUSES,
    AuditEntry,
    BookingRecord,
    BookingStatus,
    MeetingType,
    SlotReservation,
    UserProfile,
)
from app.core.booking.errors import BusinessRuleError
from app.logging.config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BookingCreationResult:
    booking: BookingRecord
    reservation: SlotReservation
    audit_entries: list[AuditEntry] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BlockUserResult:
    user: UserProfile
    closed_bookings: list[BookingRecord]
    audit_entries: list[AuditEntry] = field(default_factory=list)


class BookingService:
    def __init__(
        self,
        *,
        max_active_bookings_per_user: int = 2,
        pending_booking_ttl: timedelta = timedelta(hours=48),
        cancellation_deadline: timedelta = timedelta(hours=2),
    ) -> None:
        self.max_active_bookings_per_user = max_active_bookings_per_user
        self.pending_booking_ttl = pending_booking_ttl
        self.cancellation_deadline = cancellation_deadline

    def create_or_update_user(
        self,
        *,
        telegram_id: int,
        telegram_username: str | None,
        now: datetime,
        existing_user: UserProfile | None = None,
    ) -> UserProfile:
        if existing_user is None:
            user = UserProfile(
                telegram_id=telegram_id,
                telegram_username=telegram_username,
                created_at=now,
                updated_at=now,
                telegram_username_updated_at=now if telegram_username else None,
            )
            logger.info("User created", extra={"event": "user_created", "user_id": str(user.id)})
            return user

        if existing_user.telegram_username != telegram_username:
            existing_user.telegram_username = telegram_username
            existing_user.telegram_username_updated_at = now
            logger.info(
                "Telegram username updated",
                extra={"event": "telegram_username_updated", "user_id": str(existing_user.id)},
            )

        existing_user.updated_at = now
        return existing_user

    def accept_personal_data_consent(
        self,
        user: UserProfile,
        *,
        consent_url: str,
        policy_url: str,
        now: datetime,
    ) -> AuditEntry:
        user.consent_accepted_at = now
        user.consent_url = consent_url
        user.policy_url = policy_url
        user.updated_at = now
        audit = self._audit(
            actor_type="user",
            action="personal_data_consent_accepted",
            entity_type="user",
            entity_id=user.id,
            created_at=now,
            actor_user_id=user.id,
        )
        logger.info(
            "Consent accepted",
            extra={"event": "consent_accepted", "user_id": str(user.id)},
        )
        return audit

    def ensure_user_can_start_booking(
        self,
        *,
        user: UserProfile,
        existing_bookings: Iterable[BookingRecord],
    ) -> None:
        if not user.has_personal_data_consent:
            self._raise_rule("personal_data_consent_required", "Personal data consent is required.")
        if user.is_blocked:
            self._raise_rule("user_blocked", "Blocked users cannot create bookings.")
        self._ensure_active_booking_limit(user=user, existing_bookings=existing_bookings)

    def create_booking(
        self,
        *,
        user: UserProfile,
        meeting_type: MeetingType,
        duration_minutes: int,
        starts_at: datetime,
        ends_at: datetime,
        now: datetime,
        existing_bookings: Iterable[BookingRecord],
        final_confirmation: bool,
        user_comment: str | None = None,
        meeting_url: str | None = None,
        previous_booking: BookingRecord | None = None,
    ) -> BookingCreationResult:
        self._ensure_booking_can_be_created(
            user=user,
            meeting_type=meeting_type,
            duration_minutes=duration_minutes,
            starts_at=starts_at,
            ends_at=ends_at,
            existing_bookings=existing_bookings,
            final_confirmation=final_confirmation,
        )

        reserved_until = now + self.pending_booking_ttl
        booking = BookingRecord(
            user_id=user.id,
            meeting_type_id=meeting_type.id,
            duration_minutes=duration_minutes,
            starts_at=starts_at,
            ends_at=ends_at,
            status=BookingStatus.PENDING,
            user_comment=user_comment,
            reserved_until=reserved_until,
            meeting_url=meeting_url,
            is_reschedule_request=previous_booking is not None,
            previous_booking_id=previous_booking.id if previous_booking else None,
            created_at=now,
            updated_at=now,
        )
        reservation = SlotReservation(
            booking_id=booking.id,
            starts_at=starts_at,
            ends_at=ends_at,
            expires_at=reserved_until,
        )
        booking.reservation = reservation

        audit_entries = [
            self._audit(
                actor_type="user",
                action="booking_created",
                entity_type="booking",
                entity_id=booking.id,
                created_at=now,
                actor_user_id=user.id,
            ),
            self._audit(
                actor_type="system",
                action="slot_reserved",
                entity_type="booking",
                entity_id=booking.id,
                created_at=now,
                payload={"reserved_until": reserved_until.isoformat()},
            ),
        ]

        if previous_booking is not None:
            self._change_status(
                previous_booking,
                BookingStatus.RESCHEDULE_REQUESTED,
                now=now,
                reason="reschedule_requested",
            )
            audit_entries.append(
                self._audit(
                    actor_type="user",
                    action="reschedule_requested",
                    entity_type="booking",
                    entity_id=previous_booking.id,
                    created_at=now,
                    actor_user_id=user.id,
                    payload={"new_booking_id": str(booking.id)},
                )
            )

        logger.info(
            "Booking created",
            extra={
                "event": "booking_created",
                "booking_id": str(booking.id),
                "user_id": str(user.id),
            },
        )
        logger.info(
            "Slot reserved",
            extra={"event": "slot_reserved", "booking_id": str(booking.id)},
        )
        return BookingCreationResult(
            booking=booking,
            reservation=reservation,
            audit_entries=audit_entries,
        )

    def confirm_booking(
        self,
        booking: BookingRecord,
        *,
        google_calendar_event_id: str,
        meeting_url: str,
        now: datetime,
        admin_user_id: str | None = None,
    ) -> AuditEntry:
        if booking.status != BookingStatus.PENDING:
            self._raise_rule("booking_not_pending", "Only pending bookings can be confirmed.")

        old_status = booking.status
        booking.google_calendar_event_id = google_calendar_event_id
        booking.meeting_url = meeting_url
        self._change_status(booking, BookingStatus.CONFIRMED, now=now)
        logger.info(
            "Booking status changed",
            extra={
                "event": "booking_status_changed",
                "booking_id": str(booking.id),
                "from": old_status.value,
                "to": booking.status.value,
            },
        )
        return self._audit(
            actor_type="admin",
            action="booking_confirmed",
            entity_type="booking",
            entity_id=booking.id,
            created_at=now,
            payload={"admin_user_id": admin_user_id},
        )

    def reject_booking(
        self,
        booking: BookingRecord,
        *,
        now: datetime,
        reason: str | None = None,
    ) -> AuditEntry:
        if booking.status != BookingStatus.PENDING:
            self._raise_rule("booking_not_pending", "Only pending bookings can be rejected.")

        booking.rejection_reason = reason
        self._release_reservation(booking, now)
        self._change_status(booking, BookingStatus.REJECTED, now=now, reason=reason)
        return self._audit(
            actor_type="admin",
            action="booking_rejected",
            entity_type="booking",
            entity_id=booking.id,
            created_at=now,
            payload={"reason": reason},
        )

    def complete_reschedule(
        self,
        previous_booking: BookingRecord,
        *,
        now: datetime,
        new_booking_id: str,
    ) -> AuditEntry:
        if previous_booking.status != BookingStatus.RESCHEDULE_REQUESTED:
            self._raise_rule(
                "booking_not_reschedule_requested",
                "Only reschedule-requested bookings can be completed.",
            )

        self._release_reservation(previous_booking, now)
        self._change_status(
            previous_booking,
            BookingStatus.RESCHEDULED,
            now=now,
            reason="reschedule_confirmed",
        )
        return self._audit(
            actor_type="system",
            action="booking_rescheduled",
            entity_type="booking",
            entity_id=previous_booking.id,
            created_at=now,
            payload={"new_booking_id": new_booking_id},
        )

    def cancel_booking_by_user(
        self,
        booking: BookingRecord,
        *,
        now: datetime,
        reason: str | None = None,
    ) -> AuditEntry:
        if booking.status == BookingStatus.PENDING:
            self._release_reservation(booking, now)
        elif booking.status == BookingStatus.CONFIRMED:
            self._ensure_before_deadline(booking, now)
        else:
            self._raise_rule("booking_not_cancellable", "Booking cannot be cancelled by user.")

        booking.cancellation_reason = reason
        self._change_status(booking, BookingStatus.CANCELLED_BY_USER, now=now, reason=reason)
        return self._audit(
            actor_type="user",
            action="booking_cancelled_by_user",
            entity_type="booking",
            entity_id=booking.id,
            created_at=now,
            actor_user_id=booking.user_id,
            payload={"reason": reason},
        )

    def block_user(
        self,
        user: UserProfile,
        *,
        active_bookings: Iterable[BookingRecord],
        now: datetime,
        admin_user_id: str | None = None,
    ) -> BlockUserResult:
        user.is_blocked = True
        user.updated_at = now
        closed: list[BookingRecord] = []
        audit_entries = [
            self._audit(
                actor_type="admin",
                action="user_blocked",
                entity_type="user",
                entity_id=user.id,
                created_at=now,
                payload={"admin_user_id": admin_user_id},
            )
        ]

        for booking in active_bookings:
            if booking.status in ACTIVE_BOOKING_STATUSES:
                self._release_reservation(booking, now)
                self._change_status(booking, BookingStatus.CLOSED_BY_BLOCK, now=now)
                closed.append(booking)
                audit_entries.append(
                    self._audit(
                        actor_type="system",
                        action="booking_closed_by_block",
                        entity_type="booking",
                        entity_id=booking.id,
                        created_at=now,
                    )
                )

        logger.info("User blocked", extra={"event": "user_blocked", "user_id": str(user.id)})
        return BlockUserResult(user=user, closed_bookings=closed, audit_entries=audit_entries)

    def unblock_user(
        self,
        user: UserProfile,
        *,
        now: datetime,
        admin_user_id: str | None = None,
    ) -> AuditEntry:
        user.is_blocked = False
        user.updated_at = now
        logger.info("User unblocked", extra={"event": "user_unblocked", "user_id": str(user.id)})
        return self._audit(
            actor_type="admin",
            action="user_unblocked",
            entity_type="user",
            entity_id=user.id,
            created_at=now,
            payload={"admin_user_id": admin_user_id},
        )

    def _ensure_booking_can_be_created(
        self,
        *,
        user: UserProfile,
        meeting_type: MeetingType,
        duration_minutes: int,
        starts_at: datetime,
        ends_at: datetime,
        existing_bookings: Iterable[BookingRecord],
        final_confirmation: bool,
    ) -> None:
        if not final_confirmation:
            self._raise_rule("final_confirmation_required", "Booking requires final confirmation.")
        self.ensure_user_can_start_booking(user=user, existing_bookings=existing_bookings)
        if not meeting_type.is_active:
            self._raise_rule("meeting_type_inactive", "Meeting type is inactive.")
        if duration_minutes not in meeting_type.allowed_durations_minutes:
            self._raise_rule("invalid_duration", "Duration is not allowed for meeting type.")
        if starts_at >= ends_at:
            self._raise_rule("invalid_time_range", "Booking start must be before end.")

    def _ensure_active_booking_limit(
        self,
        *,
        user: UserProfile,
        existing_bookings: Iterable[BookingRecord],
    ) -> None:
        active_count = sum(
            1 for booking in existing_bookings if booking.user_id == user.id and booking.is_active
        )
        if active_count >= self.max_active_bookings_per_user:
            self._raise_rule("max_active_bookings", "User cannot have more active bookings.")

    def _ensure_before_deadline(self, booking: BookingRecord, now: datetime) -> None:
        if now > booking.starts_at - self.cancellation_deadline:
            self._raise_rule("cancellation_deadline_passed", "Cancellation deadline has passed.")

    def _release_reservation(self, booking: BookingRecord, now: datetime) -> None:
        if booking.reservation and booking.reservation.released_at is None:
            booking.reservation.released_at = now
            logger.info(
                "Slot reservation released",
                extra={"event": "slot_reservation_released", "booking_id": str(booking.id)},
            )

    def _change_status(
        self,
        booking: BookingRecord,
        status: BookingStatus,
        *,
        now: datetime,
        reason: str | None = None,
    ) -> None:
        old_status = booking.status
        booking.status = status
        booking.updated_at = now
        logger.info(
            "Booking status changed",
            extra={
                "event": "booking_status_changed",
                "booking_id": str(booking.id),
                "from": old_status.value,
                "to": status.value,
                "reason": reason,
            },
        )

    def _audit(
        self,
        *,
        actor_type: str,
        action: str,
        entity_type: str | None,
        entity_id,
        created_at: datetime,
        actor_user_id=None,
        payload: dict[str, object] | None = None,
    ) -> AuditEntry:
        return AuditEntry(
            actor_type=actor_type,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            created_at=created_at,
            actor_user_id=actor_user_id,
            payload=payload or {},
        )

    def _raise_rule(self, rule: str, message: str) -> None:
        logger.warning(
            "Business rule failed",
            extra={"event": "business_rule_failed", "rule": rule},
        )
        raise BusinessRuleError(rule, message)
