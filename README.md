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
4. For the current local stages 8-9, use a locally installed PostgreSQL 16 on Windows.
   Do not use Docker on a low-RAM local machine. After PostgreSQL is installed, apply
   migrations. To configure local database credentials without printing the password:

```powershell
.\.venv\Scripts\python.exe scripts\configure_local_postgres_env.py
```

Apply migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Check local database and worker diagnostics:

```powershell
.\.venv\Scripts\python.exe scripts\check_local_runtime.py
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
.\.venv\Scripts\python.exe -m app.worker.main
```

8. Run the local Telegram bot polling mode for manual checks:

```powershell
.\.venv\Scripts\python.exe -m app.integrations.telegram.run_polling
```

Local polling can use persistent PostgreSQL storage:

```dotenv
TELEGRAM_STORAGE=postgres
```

If `TELEGRAM_STORAGE` is omitted or set to `memory`, polling uses in-memory storage. That
mode is useful for quick checks, but data is lost when the process stops.

Admin sections available in local polling:

- `/admin` opens pending bookings, all bookings and blocked users.
- `Расписание` shows schedule settings and working hours.
- `Ограничения` shows upcoming restrictions and can add/delete a closed day.
- `Типы встреч` shows meeting types, can add a new meeting type and can enable/disable them.
- `Фильтры заявок` shows bookings by status with Russian status labels.

Required `.env` values for local Telegram check:

```dotenv
TELEGRAM_BOT_TOKEN=<token from BotFather>
TELEGRAM_ADMIN_ID=<your numeric Telegram ID>
PERSONAL_DATA_CONSENT_URL=https://example.com/consent
PERSONAL_DATA_POLICY_URL=https://example.com/policy
DEFAULT_MEETING_URL=https://telemost.yandex.ru/j/75500242705811
```

9. Optional Google Calendar local check:

```dotenv
GOOGLE_OAUTH_CLIENT_ID=<Google OAuth client ID>
GOOGLE_OAUTH_CLIENT_SECRET=<Google OAuth client secret>
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/oauth/google/callback
GOOGLE_OAUTH_REFRESH_TOKEN=<refresh token for local polling, do not commit>
GOOGLE_CALENDAR_ID=primary
GOOGLE_ADMIN_EMAIL=<admin email for calendar invites>
```

Start the FastAPI app and open `/oauth/google/start` to get the authorization URL. The
current local callback stores tokens in process memory; for Telegram polling checks use
`GOOGLE_OAUTH_REFRESH_TOKEN` in the local `.env`. Do not commit real Google secrets.

10. Run tests:

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

## Production VPS Deployment

Stage 10 production files:

- `Dockerfile`
- `docker-compose.prod.yml`
- `deploy/caddy/Caddyfile`
- `.env.production.example`
- `deploy/README.md`

Production uses Docker Compose with four services: `app`, `worker`, `postgres` and
`caddy`. Telegram runs through HTTPS webhook; local long polling remains for local checks.

On the VPS, create `.env.production` from `.env.production.example`, fill real values there
and run:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Detailed commands and the beginner checklist are in `deploy/README.md`.

## Logs And Diagnostics

Application logs are JSON lines. Useful fields:

- `timestamp`: UTC log time.
- `level`: `debug`, `info`, `warning`, `error`, or `critical`.
- `event`: machine-readable event name.
- `operation_id`: request or scenario correlation id.
- `service`: `app`, `worker`, or another component name when provided.

Useful searches:

```powershell
Select-String -Path .logs\*.log -Pattern '"level": "error"'
Select-String -Path .logs\*.log -Pattern 'google_api_error'
Select-String -Path .logs\*.log -Pattern 'telegram_api_error'
Select-String -Path .logs\*.log -Pattern 'operation_id'
```

Telegram admin diagnostics:

```text
/diag
```

The diagnostics output uses only safe configured true/false flags and does not print
tokens, passwords, OAuth client secrets, refresh tokens, or real values from `.env`.
