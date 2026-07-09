from __future__ import annotations

from app.integrations.google_calendar.calendar import GoogleCalendarClient
from app.integrations.google_calendar.errors import GoogleCalendarNotConnectedError
from app.worker.jobs import ReminderBooking


class GoogleCalendarEventChecker:
    def __init__(self, client: GoogleCalendarClient) -> None:
        self.client = client

    async def ensure_event_exists(self, booking: ReminderBooking) -> None:
        if not booking.google_calendar_event_id:
            raise GoogleCalendarNotConnectedError()
        self.client.ensure_event_exists(event_id=booking.google_calendar_event_id)
