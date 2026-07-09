from __future__ import annotations

import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import Flow

from app.integrations.google_calendar import CALENDAR_SCOPES
from app.settings.config import get_settings

ENV_PATH = Path(".env")
REFRESH_TOKEN_KEY = "GOOGLE_OAUTH_REFRESH_TOKEN"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        OAuthCallbackHandler.code = query.get("code", [None])[0]
        OAuthCallbackHandler.state = query.get("state", [None])[0]
        OAuthCallbackHandler.error = query.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        if OAuthCallbackHandler.error:
            self.wfile.write(b"Google OAuth failed. You can close this tab.")
        else:
            self.wfile.write(b"Google OAuth finished. You can close this tab.")

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    settings = get_settings()
    redirect_uri = settings.google_oauth_redirect_uri
    if not (
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and redirect_uri
    ):
        print("google_oauth_configured: false")
        print(
            "Fill GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET "
            "and GOOGLE_OAUTH_REDIRECT_URI."
        )
        return 1

    parsed_redirect = urlparse(redirect_uri)
    if parsed_redirect.scheme != "http" or parsed_redirect.hostname not in {
        "localhost",
        "127.0.0.1",
    }:
        print("google_redirect_uri_is_supported_local_callback: false")
        print("Use http://localhost:8000/oauth/google/callback for local token setup.")
        return 1
    if parsed_redirect.port is None:
        print("google_redirect_uri_has_port: false")
        return 1

    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret.get_secret_value(),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=list(CALENDAR_SCOPES),
        redirect_uri=redirect_uri,
    )
    authorization_url, expected_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    server_address = (parsed_redirect.hostname, parsed_redirect.port)
    try:
        httpd = HTTPServer(server_address, OAuthCallbackHandler)
    except OSError:
        print("local_callback_port_available: false")
        print("Stop the process that uses port 8000 and run this script again.")
        return 1

    print("google_oauth_configured: true")
    print("local_callback_started: true")
    print("Opening Google authorization page in browser...")
    if not webbrowser.open(authorization_url):
        print("Open this authorization URL manually:")
        print(authorization_url)

    httpd.handle_request()
    httpd.server_close()

    if OAuthCallbackHandler.error:
        print("google_oauth_completed: false")
        print(f"google_oauth_error: {OAuthCallbackHandler.error}")
        return 1
    if OAuthCallbackHandler.state != expected_state:
        print("google_oauth_completed: false")
        print("google_oauth_state_valid: false")
        return 1
    if not OAuthCallbackHandler.code:
        print("google_oauth_completed: false")
        print("google_oauth_code_received: false")
        return 1

    flow.fetch_token(code=OAuthCallbackHandler.code)
    refresh_token = flow.credentials.refresh_token
    if not refresh_token:
        print("google_oauth_completed: true")
        print("google_refresh_token_received: false")
        print("Revoke app access in your Google Account and run this script again.")
        return 1

    _upsert_env_value(ENV_PATH, REFRESH_TOKEN_KEY, refresh_token)
    print("google_oauth_completed: true")
    print("google_refresh_token_configured: true")
    return 0


def _upsert_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    target_prefix = f"{key}="
    updated = False
    next_lines: list[str] = []
    for line in lines:
        if line.startswith(target_prefix):
            next_lines.append(f"{key}={value}")
            updated = True
        else:
            next_lines.append(line)
    if not updated:
        if next_lines and next_lines[-1] != "":
            next_lines.append("")
        next_lines.append(f"{key}={value}")
    path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
