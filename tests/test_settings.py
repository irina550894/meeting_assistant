from app.settings.config import Settings


def test_settings_convert_blank_optional_values_to_none() -> None:
    settings = Settings(telegram_bot_token="", telegram_admin_id="", default_meeting_url="")

    assert settings.telegram_bot_token is None
    assert settings.telegram_admin_id is None
    assert settings.default_meeting_url is None


def test_settings_safe_summary_does_not_expose_secrets() -> None:
    settings = Settings(telegram_bot_token="secret-token", telegram_admin_id="123")

    summary = settings.safe_summary

    assert "secret-token" not in str(summary)
    assert summary["telegram_bot_token_configured"] is True
    assert summary["telegram_admin_id_configured"] is True


def test_settings_expose_storage_mode_without_secrets() -> None:
    settings = Settings(telegram_storage="postgres")

    assert settings.telegram_storage == "postgres"
    assert settings.safe_summary["telegram_storage"] == "postgres"


def test_settings_expose_mini_app_public_flags_without_secrets() -> None:
    settings = Settings(
        mini_app_enabled=True,
        mini_app_public_path="/miniapp",
        mini_app_frontend_dist_path="frontend/dist",
    )

    assert settings.mini_app_enabled is True
    assert settings.mini_app_public_path == "/miniapp"
    assert settings.mini_app_frontend_dist_path == "frontend/dist"
    assert settings.safe_summary["mini_app_enabled"] is True
    assert settings.safe_summary["mini_app_public_path"] == "/miniapp"
    assert settings.safe_summary["mini_app_frontend_dist_path"] == "frontend/dist"
