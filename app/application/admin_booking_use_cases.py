from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from app.application.sources import ActionSource
from app.core.admin_flow import AdminBookingCard, AdminFlowService
from app.core.booking import BookingRecord, BookingStatus, MeetingType, UserProfile
from app.core.booking.errors import BusinessRuleError
from app.integrations.google_calendar import GoogleCalendarError
from app.integrations.telegram.ports import (
    AdminNotifier,
    BackgroundJobSchedulerPort,
    BookingStore,
    CalendarConfirmationGateway,
    CalendarEventGateway,
    MeetingTypeStore,
    UserStore,
)
from app.logging.config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AdminDashboard:
    pending: int
    confirmed: int
    reschedule_requested: int
    cancelled: int
    upcoming: list[BookingRecord]
    recent_pending: list[BookingRecord]


@dataclass(frozen=True, slots=True)
class AdminBookingUseCaseDeps:
    users: UserStore
    meeting_types: MeetingTypeStore
    bookings: BookingStore
    admin_flow: AdminFlowService
    calendar: CalendarConfirmationGateway
    clock: Callable[[], datetime]
    notifier: AdminNotifier | None = None
    calendar_events: CalendarEventGateway | None = None
    background_jobs: BackgroundJobSchedulerPort | None = None


class AdminBookingUseCases:
    def __init__(self, deps: AdminBookingUseCaseDeps) -> None:
        self.deps = deps

    async def dashboard(self) -> AdminDashboard:
        bookings = await self.deps.bookings.list_all()
        now = self.deps.clock()
        return AdminDashboard(
            pending=sum(1 for item in bookings if item.status == BookingStatus.PENDING),
            confirmed=sum(1 for item in bookings if item.status == BookingStatus.CONFIRMED),
            reschedule_requested=sum(
                1 for item in bookings if item.status == BookingStatus.RESCHEDULE_REQUESTED
            ),
            cancelled=sum(
                1 for item in bookings if item.status == BookingStatus.CANCELLED_BY_USER
            ),
            upcoming=sorted(
                [
                    item
                    for item in bookings
                    if item.status == BookingStatus.CONFIRMED and item.starts_at >= now
                ],
                key=lambda item: item.starts_at,
            )[:10],
            recent_pending=[
                item
                for item in sorted(bookings, key=lambda item: item.created_at or item.starts_at)
                if item.status == BookingStatus.PENDING
            ][:10],
        )

    async def list_bookings(self, *, status: BookingStatus | None = None) -> list[BookingRecord]:
        bookings = await self.deps.bookings.list_all()
        if status is not None:
            bookings = [item for item in bookings if item.status == status]
        return sorted(bookings, key=lambda item: item.created_at or item.starts_at)

    async def get_booking_card(self, booking_id: UUID) -> AdminBookingCard:
        booking = await self._booking(booking_id)
        user = await self._user(booking.user_id)
        meeting_type = await self._meeting_type(booking.meeting_type_id)
        return self.deps.admin_flow.build_booking_card(
            booking=booking,
            user=user,
            meeting_type=meeting_type,
        )

    async def confirm_booking(
        self,
        *,
        booking_id: UUID,
        meeting_url: str,
        admin_telegram_id: int,
    ) -> AdminBookingCard:
        card = await self.get_booking_card(booking_id)
        confirmation = await self.deps.calendar.confirm_booking(
            booking=card.booking,
            user=card.user,
            meeting_type=card.meeting_type,
            meeting_url=meeting_url,
        )
        audit = self.deps.admin_flow.confirm_booking(
            booking=card.booking,
            confirmation=confirmation,
            now=self.deps.clock(),
            admin_telegram_id=admin_telegram_id,
        )
        audit = _with_mini_app_source(audit)
        await self.deps.bookings.save_booking(card.booking)
        audit_entries = [audit]
        reschedule_audit = await self._complete_previous_reschedule_if_needed(card.booking)
        if reschedule_audit is not None:
            audit_entries.append(reschedule_audit)
        await self.deps.bookings.save_audit_entries(audit_entries)
        if self.deps.background_jobs:
            await self.deps.background_jobs.schedule_booking_confirmed(
                card.booking,
                now=self.deps.clock(),
            )
        if self.deps.notifier:
            await self.deps.notifier.booking_confirmed(card.booking)
        return card

    async def reject_booking(
        self,
        *,
        booking_id: UUID,
        admin_telegram_id: int,
        reason: str | None = None,
    ) -> AdminBookingCard:
        card = await self.get_booking_card(booking_id)
        audit = self.deps.admin_flow.reject_booking(
            booking=card.booking,
            now=self.deps.clock(),
            admin_telegram_id=admin_telegram_id,
            reason=reason,
        )
        audit = _with_mini_app_source(audit)
        await self.deps.bookings.save_booking(card.booking)
        await self.deps.bookings.save_audit_entries([audit])
        if self.deps.notifier:
            await self.deps.notifier.booking_rejected(card.booking, reason)
        return card

    async def cancel_booking(
        self,
        *,
        booking_id: UUID,
        admin_telegram_id: int,
        reason: str | None = None,
    ) -> AdminBookingCard:
        card = await self.get_booking_card(booking_id)
        audit = self.deps.admin_flow.cancel_booking(
            booking=card.booking,
            now=self.deps.clock(),
            admin_telegram_id=admin_telegram_id,
            reason=reason,
        )
        audit = _with_mini_app_source(audit)
        await self._cancel_calendar_event_if_needed(
            card.booking,
            operation="miniapp_admin_cancel_booking",
        )
        await self.deps.bookings.save_booking(card.booking)
        await self.deps.bookings.save_audit_entries([audit])
        if self.deps.notifier:
            await self.deps.notifier.booking_cancelled_by_admin(card.booking, reason)
        return card

    async def _complete_previous_reschedule_if_needed(self, booking: BookingRecord):
        if not booking.is_reschedule_request or not booking.previous_booking_id:
            return None
        previous = await self.deps.bookings.get(booking.previous_booking_id)
        if previous is None:
            return None
        await self._cancel_calendar_event_if_needed(
            previous,
            operation="miniapp_admin_confirm_reschedule",
        )
        audit = self.deps.admin_flow.complete_reschedule(
            previous_booking=previous,
            new_booking=booking,
            now=self.deps.clock(),
        )
        audit = _with_mini_app_source(audit)
        await self.deps.bookings.save_booking(previous)
        return audit

    async def _cancel_calendar_event_if_needed(
        self,
        booking: BookingRecord,
        *,
        operation: str,
    ) -> None:
        if not self.deps.calendar_events or not booking.google_calendar_event_id:
            return
        try:
            await self.deps.calendar_events.cancel_event(booking.google_calendar_event_id)
        except GoogleCalendarError as error:
            logger.warning(
                "Google Calendar event cancellation failed",
                extra={
                    "event": "google_api_error",
                    "operation": operation,
                    "booking_id": str(booking.id),
                    "error_code": error.code,
                    "error_type": type(error).__name__,
                },
            )

    async def _booking(self, booking_id: UUID) -> BookingRecord:
        booking = await self.deps.bookings.get(booking_id)
        if not isinstance(booking, BookingRecord):
            raise BusinessRuleError("booking_not_found", "Booking was not found.")
        return booking

    async def _user(self, user_id: UUID) -> UserProfile:
        user = await self.deps.users.get(user_id)
        if not isinstance(user, UserProfile):
            raise BusinessRuleError("user_not_found", "User was not found.")
        return user

    async def _meeting_type(self, meeting_type_id: UUID) -> MeetingType:
        meeting_type = await self.deps.meeting_types.get(meeting_type_id)
        if not isinstance(meeting_type, MeetingType):
            raise BusinessRuleError("meeting_type_not_found", "Meeting type was not found.")
        return meeting_type


def _with_mini_app_source(audit):
    return replace(audit, source=ActionSource.MINI_APP.value)
