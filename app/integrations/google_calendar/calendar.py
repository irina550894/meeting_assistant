from collections.abc import Callable
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.booking import BookingRecord, MeetingType, UserProfile
from app.core.scheduling import BusyInterval, BusySource
from app.integrations.google_calendar.entities import GoogleOAuthTokens
from app.integrations.google_calendar.errors import (
    GoogleCalendarAccessLostError,
    GoogleCalendarApiError,
    GoogleCalendarEventMissingError,
    GoogleCalendarNotConnectedError,
)
from app.logging.config import get_logger
from app.settings.config import Settings

logger = get_logger(__name__)


class GoogleCalendarClient:
    def __init__(
        self,
        *,
        settings: Settings,
        token_provider: Callable[[], GoogleOAuthTokens | None],
        service_factory: Callable[[object], object] | None = None,
    ) -> None:
        self.settings = settings
        self.token_provider = token_provider
        self.service_factory = service_factory or self._build_service

    def list_busy_intervals(self, *, time_min: datetime, time_max: datetime) -> list[BusyInterval]:
        service = self._service()
        logger.info(
            "Google Calendar busy requested",
            extra={"event": "google_calendar_busy_requested"},
        )
        body = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": self.settings.google_calendar_id}],
        }
        try:
            response = service.freebusy().query(body=body).execute()
        except HttpError as error:
            self._raise_for_http_error(error, operation="freebusy")
        except Exception as error:
            logger.error(
                "Google Calendar API error",
                extra={"event": "google_api_error", "operation": "freebusy"},
            )
            raise GoogleCalendarApiError("freebusy") from error
        calendar_data = response.get("calendars", {}).get(self.settings.google_calendar_id, {})
        return [
            BusyInterval(
                starts_at=_parse_google_datetime(item["start"], self.settings.app_timezone),
                ends_at=_parse_google_datetime(item["end"], self.settings.app_timezone),
                source=BusySource.CALENDAR,
                all_day=False,
            )
            for item in calendar_data.get("busy", [])
            if item.get("start") and item.get("end")
        ]

    def create_event(
        self,
        *,
        booking: BookingRecord,
        user: UserProfile,
        meeting_type: MeetingType,
        meeting_url: str,
    ) -> str:
        service = self._service()
        body = self._event_body(
            booking=booking,
            user=user,
            meeting_type=meeting_type,
            meeting_url=meeting_url,
        )
        try:
            response = (
                service.events()
                .insert(calendarId=self.settings.google_calendar_id, body=body, sendUpdates="all")
                .execute()
            )
        except HttpError as error:
            self._raise_for_http_error(error, operation="create_event")
        except Exception as error:
            logger.error(
                "Google Calendar API error",
                extra={
                    "event": "google_api_error",
                    "operation": "create_event",
                    "booking_id": str(booking.id),
                },
            )
            raise GoogleCalendarApiError("create_event") from error
        event_id = response.get("id")
        if not event_id:
            raise GoogleCalendarApiError("create_event")
        logger.info(
            "Google Calendar event created",
            extra={
                "event": "google_event_created",
                "booking_id": str(booking.id),
                "calendar_event_id": event_id,
            },
        )
        return event_id

    def cancel_event(self, *, event_id: str) -> None:
        service = self._service()
        try:
            service.events().delete(
                calendarId=self.settings.google_calendar_id,
                eventId=event_id,
                sendUpdates="all",
            ).execute()
        except HttpError as error:
            if getattr(error.resp, "status", None) == 404:
                logger.warning(
                    "Google Calendar event missing",
                    extra={"event": "google_event_missing"},
                )
                raise GoogleCalendarEventMissingError() from error
            self._raise_for_http_error(error, operation="cancel_event")
        except Exception as error:
            logger.error(
                "Google Calendar API error",
                extra={"event": "google_api_error", "operation": "cancel_event"},
            )
            raise GoogleCalendarApiError("cancel_event") from error
        logger.info("Google Calendar event cancelled", extra={"event": "google_event_cancelled"})

    def ensure_event_exists(self, *, event_id: str) -> None:
        service = self._service()
        try:
            service.events().get(
                calendarId=self.settings.google_calendar_id,
                eventId=event_id,
            ).execute()
        except HttpError as error:
            if getattr(error.resp, "status", None) == 404:
                logger.warning(
                    "Google Calendar event missing",
                    extra={"event": "google_event_missing"},
                )
                raise GoogleCalendarEventMissingError() from error
            self._raise_for_http_error(error, operation="get_event")
        except Exception as error:
            logger.error(
                "Google Calendar API error",
                extra={"event": "google_api_error", "operation": "get_event"},
            )
            raise GoogleCalendarApiError("get_event") from error

    def _event_body(
        self,
        *,
        booking: BookingRecord,
        user: UserProfile,
        meeting_type: MeetingType,
        meeting_url: str,
    ) -> dict[str, object]:
        attendees = [{"email": user.email}] if user.email else []
        if self.settings.google_admin_email:
            attendees.append({"email": self.settings.google_admin_email})
        description_parts = [
            f"Заявка: {booking.id}",
            f"Тип встречи: {meeting_type.name}",
            f"Ссылка на онлайн-встречу: {meeting_url}",
        ]
        if booking.user_comment:
            description_parts.append(f"Комментарий пользователя: {booking.user_comment}")
        return {
            "summary": f"{meeting_type.name}: {user.full_name or 'пользователь'}",
            "description": "\n".join(description_parts),
            "location": meeting_url,
            "start": {
                "dateTime": booking.starts_at.isoformat(),
                "timeZone": self.settings.app_timezone,
            },
            "end": {
                "dateTime": booking.ends_at.isoformat(),
                "timeZone": self.settings.app_timezone,
            },
            "attendees": attendees,
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 60},
                ],
            },
        }

    def _service(self) -> object:
        tokens = self.token_provider()
        if tokens is None:
            raise GoogleCalendarNotConnectedError()
        return self.service_factory(tokens.to_credentials())

    @staticmethod
    def _build_service(credentials: object) -> object:
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    @staticmethod
    def _raise_for_http_error(error: HttpError, *, operation: str) -> None:
        status = getattr(error.resp, "status", None)
        if status in {401, 403}:
            logger.error(
                "Google Calendar access lost",
                extra={"event": "google_access_lost", "operation": operation},
            )
            raise GoogleCalendarAccessLostError() from error
        logger.error(
            "Google Calendar API error",
            extra={"event": "google_api_error", "operation": operation},
        )
        raise GoogleCalendarApiError(operation) from error


def _parse_google_datetime(value: str, timezone: str) -> datetime:
    if "T" not in value:
        return datetime.combine(
            date.fromisoformat(value),
            time.min,
            tzinfo=ZoneInfo(timezone),
        )
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
