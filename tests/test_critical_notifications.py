import pytest

from app.integrations.telegram.critical_notifications import notify_critical_admin
from app.settings.config import Settings


@pytest.mark.asyncio
async def test_critical_admin_notification_sends_safe_message() -> None:
    settings = Settings(
        telegram_bot_token="secret-token",
        telegram_admin_id="123",
    )
    bot = FakeBot()

    sent = await notify_critical_admin(
        settings,
        source="worker",
        error_type="RuntimeError",
        bot=bot,
    )

    assert sent is True
    assert bot.messages == [
        {
            "chat_id": 123,
            "text": (
                "Обнаружена критическая ошибка.\n"
                "Источник: worker\n"
                "Тип: RuntimeError\n"
                "Проверьте технические логи по operation_id и event=critical_error."
            ),
            "parse_mode": None,
        }
    ]
    assert "secret-token" not in bot.messages[0]["text"]


class FakeBot:
    def __init__(self) -> None:
        self.messages = []

    async def send_message(self, **kwargs) -> None:
        self.messages.append(kwargs)
