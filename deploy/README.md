# Production deployment on VPS

Инструкция для production-схемы MVP Telegram-бота "Ассистент по встречам".

## Current production topology

- VPS project directory: `/home/irina/meeting_assistant`
- Domain: `calendar.finforbiz.pro`
- Docker services: `postgres`, `app`, `worker`
- App binding: `127.0.0.1:8010 -> container 8000`
- HTTPS reverse proxy: system Caddy on VPS
- Compose files:
  - `docker-compose.prod.yml`
  - `docker-compose.system-caddy.yml`

The Caddy container from `docker-compose.prod.yml` is not used on the current VPS,
because a system Caddy already serves other domains.

## Required VPS prerequisites

1. Docker Engine and Docker Compose plugin installed.
2. DNS `A` record for `calendar.finforbiz.pro` points to the VPS public IP.
3. Inbound ports `80` and `443` are open.
4. System Caddy is installed and running.
5. Project files are present in `/home/irina/meeting_assistant`.
6. `/home/irina/meeting_assistant/.env.production` exists with permissions `600`.

Do not print `.env.production` values in logs, terminal output or documentation.

## Required secrets

Create `.env.production` from `.env.production.example` on the VPS and fill real
values there. Do not commit `.env.production`.

Required values:

- `DOMAIN`
- `PUBLIC_BASE_URL`
- `WEBHOOK_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_ID`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `DEFAULT_MEETING_URL`
- `PERSONAL_DATA_CONSENT_URL`
- `PERSONAL_DATA_POLICY_URL`
- Google OAuth and Calendar values.

If you need to verify environment readiness, report only configured true/false.

## Start or update production

```bash
cd /home/irina/meeting_assistant
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  up -d --build postgres app worker
```

## System Caddy config

The system Caddy `/etc/caddy/Caddyfile` must contain:

```caddyfile
calendar.finforbiz.pro {
  encode zstd gzip
  reverse_proxy 127.0.0.1:8010
}
```

Reload Caddy after changes:

```bash
sudo systemctl reload caddy
```

Check Caddy status:

```bash
sudo systemctl status caddy
```

## Checks

Show containers:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  ps
```

Expected:

- `app` is `Up` and `healthy`.
- `postgres` is `Up` and `healthy`.
- `worker` is `Up`.

Open:

```text
https://calendar.finforbiz.pro/health
```

Expected response:

```json
{"status":"ok","service":"meeting-assistant","environment":"production"}
```

Then write `/start` to the Telegram bot and check the full user/admin flow.

## Logs

Show app logs:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  logs -f app
```

Show worker logs:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  logs -f worker
```

Show last app and worker logs:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  logs --tail=100 app worker
```

Useful events:

- `production_app_started`
- `telegram_webhook_configured`
- `healthcheck_ok`
- `worker_started`
- `background_jobs_recovered`
- `job_started`
- `job_succeeded`
- `job_failed`
- `audit_log_cleanup_completed`
- `google_event_created`
- `google_event_cancelled`
- `google_api_error`
- `telegram_api_error`

## Restart

Restart app and worker:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  restart app worker
```

Restart all Docker services:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  restart postgres app worker
```

## Stop

Stop application services:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  down
```

Use stop commands carefully: while services are down, Telegram webhook cannot process
updates.

## Beginner production checklist

1. Open `https://calendar.finforbiz.pro/health`.
2. Confirm the response contains `"status":"ok"`.
3. Run `docker compose ps` command from this file.
4. Confirm `app`, `postgres`, `worker` are up.
5. Write `/start` to the bot.
6. Create a booking as a user.
7. Confirm it as admin.
8. Check Telegram notifications for user and admin.
9. Check Google Calendar event.
10. Check Google Calendar email invitation, including spam.
11. Cancel the meeting and confirm the calendar event is cancelled.

## Notes

- PostgreSQL has no public port in `docker-compose.prod.yml`; it is available only
  inside the Docker network.
- Telegram runs through HTTPS webhook in production.
- Caddy obtains and renews HTTPS certificates automatically.
- Email delivery is handled by Google Calendar invitations/cancellations. There is
  no separate SMTP service in MVP.
