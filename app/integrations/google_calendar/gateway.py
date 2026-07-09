from app.core.admin_flow import AdminConfirmationResult
from app.core.booking import BookingRecord, BusinessRuleError, MeetingType, UserProfile
from app.integrations.google_calendar.calendar import GoogleCalendarClient


class GoogleCalendarConfirmationGateway:
    def __init__(self, client: GoogleCalendarClient) -> None:
        self.client = client

    async def confirm_booking(
        self,
        *,
        booking: BookingRecord,
        user: UserProfile,
        meeting_type: MeetingType,
        meeting_url: str,
    ) -> AdminConfirmationResult:
        busy_intervals = self.client.list_busy_intervals(
            time_min=booking.starts_at,
            time_max=booking.ends_at,
        )
        if busy_intervals:
            raise BusinessRuleError(
                "calendar_conflict",
                "Selected slot is busy in Google Calendar.",
            )
        event_id = self.client.create_event(
            booking=booking,
            user=user,
            meeting_type=meeting_type,
            meeting_url=meeting_url,
        )
        return AdminConfirmationResult(
            google_calendar_event_id=event_id,
            meeting_url=meeting_url,
        )


class GoogleCalendarEventGateway:
    def __init__(self, client: GoogleCalendarClient) -> None:
        self.client = client

    async def cancel_event(self, event_id: str) -> None:
        self.client.cancel_event(event_id=event_id)
