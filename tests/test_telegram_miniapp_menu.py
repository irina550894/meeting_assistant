import pytest

from app.integrations.telegram.keyboards import MINI_APP_BUTTON_TEXT
from app.integrations.telegram.runtime import _configure_mini_app_menu_button
from app.settings.config import Settings


class FakeBot:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.menu_buttons = []

    async def set_chat_menu_button(self, **kwargs) -> None:
        if self.should_fail:
            raise RuntimeError("telegram unavailable")
        self.menu_buttons.append(kwargs["menu_button"])


@pytest.mark.asyncio
async def test_configure_mini_app_menu_button_sets_webapp_button() -> None:
    bot = FakeBot()

    await _configure_mini_app_menu_button(
        bot,
        Settings(
            mini_app_enabled=True,
            public_base_url="https://calendar.finforbiz.pro",
            mini_app_public_path="/miniapp",
        ),
    )

    assert len(bot.menu_buttons) == 1
    assert bot.menu_buttons[0].text == MINI_APP_BUTTON_TEXT
    assert bot.menu_buttons[0].web_app.url == "https://calendar.finforbiz.pro/miniapp/"


@pytest.mark.asyncio
async def test_configure_mini_app_menu_button_skips_non_https_url() -> None:
    bot = FakeBot()

    await _configure_mini_app_menu_button(
        bot,
        Settings(
            mini_app_enabled=True,
            public_base_url="http://localhost:8000",
            mini_app_public_path="/miniapp",
        ),
    )

    assert bot.menu_buttons == []


@pytest.mark.asyncio
async def test_configure_mini_app_menu_button_does_not_fail_bot_startup() -> None:
    bot = FakeBot(should_fail=True)

    await _configure_mini_app_menu_button(
        bot,
        Settings(
            mini_app_enabled=True,
            public_base_url="https://calendar.finforbiz.pro",
            mini_app_public_path="/miniapp",
        ),
    )

    assert bot.menu_buttons == []
