# Telegram-бот "Ассистент по встречам"

MVP backend scaffold for a Telegram meeting assistant.

## Current Stage

Stage 1: project scaffold and local environment.

## Local Setup

1. Create and activate a Python 3.12 virtual environment.
2. Install dependencies:

```powershell
pip install -e ".[dev]"
```

3. Fill local `.env` values. Do not commit `.env`.
4. Start PostgreSQL:

```powershell
docker compose up -d postgres
```

5. Run the API:

```powershell
uvicorn app.main:app --reload
```

6. Open healthcheck:

```text
http://127.0.0.1:8000/health
```

7. Run worker stub:

```powershell
python -m app.worker.main
```

8. Run the local Telegram bot polling mode for manual checks:

```powershell
python -m app.integrations.telegram.run_polling
```

Local polling mode uses in-memory storage. It is useful for checking `/start`, consent,
booking creation, "My bookings", cancellation, and admin actions in Telegram. Data is lost
when the process stops.

Required `.env` values for local Telegram check:

```dotenv
TELEGRAM_BOT_TOKEN=<token from BotFather>
TELEGRAM_ADMIN_ID=<your numeric Telegram ID>
PERSONAL_DATA_CONSENT_URL=https://example.com/consent
PERSONAL_DATA_POLICY_URL=https://example.com/policy
DEFAULT_MEETING_URL=https://telemost.yandex.ru/j/75500242705811
```

9. Run tests:

```powershell
pytest
```

## Database Migrations

Apply migrations:

```powershell
alembic upgrade head
```

Rollback the last migration:

```powershell
alembic downgrade -1
```
