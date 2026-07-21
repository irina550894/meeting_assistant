from collections.abc import Iterable

from app.core.booking import BookingRecord, UserProfile
from app.integrations.telegram.ports import AdminNotifier, UserFlowNotifier


class CompositeUserFlowNotifier:
    def __init__(self, notifiers: Iterable[UserFlowNotifier]) -> None:
        self.notifiers = tuple(notifiers)

    async def booking_created(self, booking: BookingRecord) -> None:
        for notifier in self.notifiers:
            await notifier.booking_created(booking)

    async def booking_cancelled_by_user(self, booking: BookingRecord) -> None:
        for notifier in self.notifiers:
            await notifier.booking_cancelled_by_user(booking)

    async def reschedule_requested(self, booking: BookingRecord) -> None:
        for notifier in self.notifiers:
            await notifier.reschedule_requested(booking)


class CompositeAdminNotifier:
    def __init__(self, notifiers: Iterable[AdminNotifier]) -> None:
        self.notifiers = tuple(notifiers)

    async def booking_confirmed(self, booking: BookingRecord) -> None:
        for notifier in self.notifiers:
            await notifier.booking_confirmed(booking)

    async def booking_rejected(self, booking: BookingRecord, reason: str | None) -> None:
        for notifier in self.notifiers:
            await notifier.booking_rejected(booking, reason)

    async def booking_cancelled_by_admin(
        self,
        booking: BookingRecord,
        reason: str | None,
    ) -> None:
        for notifier in self.notifiers:
            await notifier.booking_cancelled_by_admin(booking, reason)

    async def user_blocked(self, user: UserProfile) -> None:
        for notifier in self.notifiers:
            await notifier.user_blocked(user)

    async def send_user_message(self, user: UserProfile, text: str) -> None:
        for notifier in self.notifiers:
            await notifier.send_user_message(user, text)
