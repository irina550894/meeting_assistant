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

8. Run tests:

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
