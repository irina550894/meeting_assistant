from app.core.booking import BookingStatus

BOOKING_STATUS_LABELS = {
    BookingStatus.PENDING: "ожидает подтверждения",
    BookingStatus.CONFIRMED: "подтверждена",
    BookingStatus.REJECTED: "отклонена",
    BookingStatus.CANCELLED_BY_USER: "отменена пользователем",
    BookingStatus.EXPIRED: "истекла",
    BookingStatus.RESCHEDULE_REQUESTED: "запрошен перенос",
    BookingStatus.RESCHEDULED: "перенесена",
    BookingStatus.CLOSED_BY_BLOCK: "закрыта из-за блокировки",
    BookingStatus.CALENDAR_CONFLICT: "конфликт календаря",
}


def booking_status_label(status: BookingStatus) -> str:
    return BOOKING_STATUS_LABELS.get(status, status.value)
