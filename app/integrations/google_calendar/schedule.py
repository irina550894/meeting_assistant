from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.core.user_flow import FlowScheduleContext
from app.integrations.google_calendar.calendar import GoogleCalendarClient
from app.integrations.google_calendar.errors import GoogleCalendarError
from app.integrations.telegram.ports import ScheduleProvider
from app.logging.config import get_logger

logger = get_logger(__name__)


class GoogleCalendarScheduleProvider:
    def __init__(self, *, base: ScheduleProvider, client: GoogleCalendarClient) -> None:
        self.base = base
        self.client = client

    async def context_for_date(self, target_date: date) -> FlowScheduleContext:
        context = await self.base.context_for_date(target_date)
        timezone = ZoneInfo(context.settings.timezone)
        day_start = datetime.combine(target_date, time.min, tzinfo=timezone)
        day_end = datetime.combine(target_date, time.max, tzinfo=timezone)
        try:
            calendar_busy = self.client.list_busy_intervals(
                time_min=day_start,
                time_max=day_end,
            )
        except GoogleCalendarError as error:
            logger.warning(
                "Google Calendar busy lookup failed",
                extra={
                    "event": "google_api_error",
                    "operation": "freebusy",
                    "error_code": error.code,
                },
            )
            calendar_busy = []
        return FlowScheduleContext(
            settings=context.settings,
            working_hours=context.working_hours,
            restrictions=context.restrictions,
            busy_intervals=[*context.busy_intervals, *calendar_busy],
        )
