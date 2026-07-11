from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "meeting-assistant"
    app_version: str = "0.1.0"
    app_env: str = "local"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_timezone: str = "Europe/Moscow"
    public_base_url: str | None = None
    webhook_secret: SecretStr | None = None

    telegram_bot_token: SecretStr | None = None
    telegram_admin_id: int | None = None
    telegram_use_webhook: bool = False
    telegram_request_timeout_seconds: int = 10
    telegram_storage: str = "memory"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "meeting_assistant"
    postgres_user: str = "meeting_assistant"
    postgres_password: SecretStr | None = None
    database_url: SecretStr = Field(
        default=SecretStr(
            "postgresql+asyncpg://meeting_assistant:password@localhost:5432/meeting_assistant"
        )
    )

    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    google_oauth_redirect_uri: str | None = None
    google_oauth_refresh_token: SecretStr | None = None
    google_calendar_id: str = "primary"
    google_admin_email: str | None = None

    default_meeting_url: str | None = None
    booking_horizon_days: int = 30
    min_booking_lead_days: int = 1
    slot_step_minutes: int = 60
    meeting_buffer_minutes: int = 90
    pending_booking_ttl_hours: int = 48
    cancellation_deadline_hours: int = 2
    max_active_bookings_per_user: int = 2

    personal_data_consent_url: str | None = None
    personal_data_policy_url: str | None = None

    worker_poll_interval_seconds: int = 30
    integration_max_retries: int = 3
    audit_log_retention_days: int = 30

    log_level: str = "INFO"
    log_format: str = "json"

    @field_validator(
        "public_base_url",
        "webhook_secret",
        "telegram_bot_token",
        "telegram_admin_id",
        "postgres_password",
        "google_oauth_client_id",
        "google_oauth_client_secret",
        "google_oauth_redirect_uri",
        "google_oauth_refresh_token",
        "google_admin_email",
        "default_meeting_url",
        "personal_data_consent_url",
        "personal_data_policy_url",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @property
    def safe_summary(self) -> dict[str, str | int | bool | None]:
        return {
            "app_env": self.app_env,
            "app_debug": self.app_debug,
            "app_host": self.app_host,
            "app_port": self.app_port,
            "app_timezone": self.app_timezone,
            "telegram_admin_id_configured": self.telegram_admin_id is not None,
            "telegram_bot_token_configured": self.telegram_bot_token is not None,
            "telegram_storage": self.telegram_storage,
            "database_configured": bool(self.database_url),
            "google_oauth_configured": bool(
                self.google_oauth_client_id and self.google_oauth_client_secret
            ),
            "google_refresh_token_configured": self.google_oauth_refresh_token is not None,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
