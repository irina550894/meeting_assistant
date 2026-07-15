from enum import StrEnum


class ActionSource(StrEnum):
    TELEGRAM_BOT = "telegram_bot"
    MINI_APP = "mini_app"
    SYSTEM = "system"
    WORKER = "worker"
