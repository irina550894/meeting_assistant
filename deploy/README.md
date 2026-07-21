# Production deployment on VPS

Инструкция для production-схемы MVP Telegram-бота "Ассистент по встречам".

## Current production topology

- VPS project directory: `/home/irina/meeting_assistant`
- Domain: `calendar.finforbiz.pro`
- Docker services: `postgres`, `app`, `worker`
- App binding: `127.0.0.1:8010 -> container 8000`
- HTTPS reverse proxy: system Caddy on VPS
- Mini App frontend: `https://calendar.finforbiz.pro/miniapp/`
- Mini App API: `https://calendar.finforbiz.pro/api/miniapp/...`
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
- `MINI_APP_FRONTEND_DIST_PATH`
- Google OAuth and Calendar values.
- SMTP values for user email notifications, if email delivery is enabled.

Mini App button in Telegram is enabled only when `MINI_APP_ENABLED=true` and
`PUBLIC_BASE_URL` starts with `https://`.

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

No separate Caddy route is required for `/miniapp/`: system Caddy proxies the
whole domain to FastAPI, and FastAPI serves the built Vite files from
`MINI_APP_FRONTEND_DIST_PATH`.

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
https://calendar.finforbiz.pro/miniapp/
```

Expected response:

```json
{"status":"ok","service":"meeting-assistant","environment":"production"}
```

Then write `/start` to the Telegram bot and check the full user/admin flow.

Expected Mini App response: HTML page with the Mini App shell.

Detailed manual UAT checklist: `UAT_Telegram_Mini_App.md`.

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
- `mini_app_menu_button_configured`
- `mini_app_menu_button_failed`
- `mini_app_frontend_mounted`
- `mini_app_frontend_dist_missing`
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
5. Open `https://calendar.finforbiz.pro/miniapp/`.
6. Confirm the Mini App shell opens.
7. Write `/start` to the bot.
8. Confirm the `Открыть Mini App` button is visible.
9. Create a booking as a user.
10. Confirm it as admin.
11. Check Telegram notifications for user and admin.
12. Check Google Calendar event.
13. Check Google Calendar email invitation, including spam.
14. Cancel the meeting and confirm the calendar event is cancelled.

## Notes

- PostgreSQL has no public port in `docker-compose.prod.yml`; it is available only
  inside the Docker network.
- Telegram runs through HTTPS webhook in production.
- Caddy obtains and renews HTTPS certificates automatically.
- Google Calendar invitations/cancellations are still created for calendar events.
- Optional SMTP delivery sends additional status emails to the user's email address only.

## Automatic GitHub Actions deploy

Automatic deploy after code push is described in `deploy/GITHUB_ACTIONS_DEPLOY.md`.
