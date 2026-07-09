from typing import Protocol

from app.integrations.google_calendar.entities import GoogleOAuthTokens


class GoogleOAuthTokenStore(Protocol):
    async def get(self) -> GoogleOAuthTokens | None: ...

    async def save(self, tokens: GoogleOAuthTokens) -> None: ...

    async def clear(self) -> None: ...


class InMemoryGoogleOAuthTokenStore:
    def __init__(self, initial_tokens: GoogleOAuthTokens | None = None) -> None:
        self._tokens = initial_tokens

    async def get(self) -> GoogleOAuthTokens | None:
        return self._tokens

    async def save(self, tokens: GoogleOAuthTokens) -> None:
        self._tokens = tokens

    async def clear(self) -> None:
        self._tokens = None
