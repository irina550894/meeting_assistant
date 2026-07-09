class GoogleCalendarError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GoogleCalendarNotConnectedError(GoogleCalendarError):
    def __init__(self) -> None:
        super().__init__("google_calendar_not_connected", "Google Calendar is not connected.")


class GoogleCalendarAccessLostError(GoogleCalendarError):
    def __init__(self) -> None:
        super().__init__("google_calendar_access_lost", "Google Calendar access is lost.")


class GoogleCalendarApiError(GoogleCalendarError):
    def __init__(self, operation: str) -> None:
        super().__init__("google_calendar_api_error", f"Google Calendar failed: {operation}.")
        self.operation = operation


class GoogleCalendarEventMissingError(GoogleCalendarError):
    def __init__(self) -> None:
        super().__init__("google_calendar_event_missing", "Google Calendar event is missing.")
