from __future__ import annotations

from getpass import getpass
from pathlib import Path
from urllib.parse import quote

ENV_PATH = Path(".env")


def main() -> None:
    if not ENV_PATH.exists():
        raise SystemExit(".env file was not found.")

    password = getpass("POSTGRES_PASSWORD for meeting_assistant: ")
    if not password:
        raise SystemExit("Password cannot be empty.")

    values = _read_env(ENV_PATH)
    host = values.get("POSTGRES_HOST") or "localhost"
    port = values.get("POSTGRES_PORT") or "5432"
    database = values.get("POSTGRES_DB") or "meeting_assistant"
    user = values.get("POSTGRES_USER") or "meeting_assistant"
    encoded_password = quote(password, safe="")
    values["POSTGRES_HOST"] = host
    values["POSTGRES_PORT"] = port
    values["POSTGRES_DB"] = database
    values["POSTGRES_USER"] = user
    values["POSTGRES_PASSWORD"] = password
    values["DATABASE_URL"] = (
        f"postgresql+asyncpg://{user}:{encoded_password}@{host}:{port}/{database}"
    )
    values["TELEGRAM_STORAGE"] = values.get("TELEGRAM_STORAGE") or "postgres"
    _write_env(ENV_PATH, values)
    print("local_postgres_env_configured True")


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _write_env(path: Path, values: dict[str, str]) -> None:
    lines: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key, _value = line.split("=", 1)
        if key in values:
            lines.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            lines.append(line)
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
