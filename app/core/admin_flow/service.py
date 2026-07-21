from datetime import datetime
from uuid import UUID

from app.core.admin_flow.entities import AdminBookingCard, AdminConfirmationResult
from app.core.admin_flow.errors import AdminFlowError
from app.core.booking import (
    AuditEntry,
    BookingRecord,
    BookingService,
    MeetingType,
    UserProfile,
)
from app.logging.config import get_logger

logger = get_logger(__name__)


class AdminFlowService:
    def __init__(self, *, booking_service: BookingService | None = None) -> None:
        self.booking_service = booking_service or BookingService()

    def ensure_admin(self, *, telegram_id: int, configured_admin_id: int | None) -> None:
        if configured_admin_id is None:
            logger.warning(
                "Admin access denied",
                extra={"event": "admin_access_denied", "reason": "admin_not_configured"},
            )
            raise AdminFlowError("admin_not_configured", "Admin Telegram ID is not configured.")
        if telegram_id != configured_admin_id:
            logger.warning(
                "Admin access denied",
                extra={"event": "admin_access_denied", "telegram_id": telegram_id},
            )
            raise AdminFlowError("admin_access_denied", "Only administrator can use this action.")

    def build_booking_card(
        self,
        *,
        booking: BookingRecord,
        user: UserProfile,
        meeting_type: MeetingType,
    ) -> AdminBookingCard:
        return AdminBookingCard(booking=booking, user=user, meeting_type=meeting_type)

    def confirm_booking(
        self,
        *,
        booking: BookingRecord,
        confirmation: AdminConfirmationResult,
        now: datetime,
        admin_telegram_id: int,
    ) -> AuditEntry:
        audit = self.booking_service.confirm_booking(
            booking,
            google_calendar_event_id=confirmation.google_calendar_event_id,
            meeting_url=confirmation.meeting_url,
            now=now,
            admin_user_id=str(admin_telegram_id),
        )
        logger.info(
            "Admin confirmed booking",
            extra={
                "event": "admin_action",
                "action": "confirm_booking",
                "admin_id": admin_telegram_id,
                "booking_id": str(booking.id),
            },
        )
        return audit

    def reject_booking(
        self,
        *,
        booking: BookingRecord,
        now: datetime,
        admin_telegram_id: int,
        reason: str | None = None,
    ) -> AuditEntry:
        audit = self.booking_service.reject_booking(booking, now=now, reason=reason)
        logger.info(
            "Admin rejected booking",
            extra={
                "event": "admin_action",
                "action": "reject_booking",
                "admin_id": admin_telegram_id,
                "booking_id": str(booking.id),
                "has_reason": bool(reason),
            },
        )
        return audit

    def cancel_booking(
        self,
        *,
        booking: BookingRecord,
        now: datetime,
        admin_telegram_id: int,
        reason: str | None = None,
    ) -> AuditEntry:
        audit = self.booking_service.cancel_booking_by_admin(
            booking,
            now=now,
            admin_user_id=str(admin_telegram_id),
            reason=reason,
        )
        logger.info(
            "Admin cancelled booking",
            extra={
                "event": "admin_action",
                "action": "cancel_booking",
                "admin_id": admin_telegram_id,
                "booking_id": str(booking.id),
                "has_reason": bool(reason),
            },
        )
        return audit

    def complete_reschedule(
        self,
        *,
        previous_booking: BookingRecord,
        new_booking: BookingRecord,
        now: datetime,
    ) -> AuditEntry:
        audit = self.booking_service.complete_reschedule(
            previous_booking,
            now=now,
            new_booking_id=str(new_booking.id),
        )
        logger.info(
            "Admin confirmed reschedule",
            extra={
                "event": "admin_action",
                "action": "complete_reschedule",
                "previous_booking_id": str(previous_booking.id),
                "new_booking_id": str(new_booking.id),
            },
        )
        return audit

    def block_user(
        self,
        *,
        user: UserProfile,
        active_bookings: list[BookingRecord],
        now: datetime,
        admin_telegram_id: int,
    ):
        result = self.booking_service.block_user(
            user,
            active_bookings=active_bookings,
            now=now,
            admin_user_id=str(admin_telegram_id),
        )
        logger.info(
            "Admin blocked user",
            extra={
                "event": "admin_action",
                "action": "block_user",
                "admin_id": admin_telegram_id,
                "user_id": str(user.id),
                "closed_bookings_count": len(result.closed_bookings),
            },
        )
        return result

    def unblock_user(
        self,
        *,
        user: UserProfile,
        now: datetime,
        admin_telegram_id: int,
    ) -> AuditEntry:
        audit = self.booking_service.unblock_user(
            user,
            now=now,
            admin_user_id=str(admin_telegram_id),
        )
        logger.info(
            "Admin unblocked user",
            extra={
                "event": "admin_action",
                "action": "unblock_user",
                "admin_id": admin_telegram_id,
                "user_id": str(user.id),
            },
        )
        return audit

    def message_sent_audit(
        self,
        *,
        user_id: UUID,
        now: datetime,
        admin_telegram_id: int,
    ) -> AuditEntry:
        logger.info(
            "Admin message sent",
            extra={
                "event": "admin_message_sent",
                "admin_id": admin_telegram_id,
                "user_id": str(user_id),
            },
        )
        return AuditEntry(
            actor_type="admin",
            action="admin_message_sent",
            entity_type="user",
            entity_id=user_id,
            created_at=now,
            payload={"admin_user_id": str(admin_telegram_id)},
        )
