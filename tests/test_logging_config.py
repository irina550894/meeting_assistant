import json
import logging

from app.logging.config import JsonFormatter, reset_operation_id, set_operation_id


def formatted_record(**extra) -> dict:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="User email is irina@example.com",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_json_formatter_adds_operation_id_from_context() -> None:
    token = set_operation_id("op-test")
    try:
        payload = formatted_record()
    finally:
        reset_operation_id(token)

    assert payload["operation_id"] == "op-test"


def test_json_formatter_masks_email_and_redacts_secret_keys() -> None:
    payload = formatted_record(
        email="admin@example.com",
        telegram_bot_token="123:secret",
        nested={"client_secret": "secret-value", "owner": "user@example.com"},
    )

    rendered = json.dumps(payload)
    assert "admin@example.com" not in rendered
    assert "user@example.com" not in rendered
    assert "123:secret" not in rendered
    assert "secret-value" not in rendered
    assert payload["telegram_bot_token"] == "***"
    assert payload["nested"]["client_secret"] == "***"
