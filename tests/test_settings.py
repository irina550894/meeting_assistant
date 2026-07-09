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
