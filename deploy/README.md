# Production deployment on VPS

This deployment is for stage 10: Docker Compose, Caddy HTTPS and Telegram webhook.

## Required VPS prerequisites

1. A VPS with Docker Engine and Docker Compose plugin installed.
2. A domain or subdomain.
3. DNS `A` record pointing the domain to the VPS public IP.
4. Open inbound ports `80` and `443`.
5. Repository files copied or pulled to the VPS.

## Required secrets

Create `.env.production` from `.env.production.example` on the VPS and fill real values.
Do not commit `.env.production`.

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
- Google OAuth and Calendar values, if Google Calendar is enabled.

## Commands

Build and start:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Show containers:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```

Show app logs:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f app
```

Show worker logs:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f worker
```

Show Caddy logs:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f caddy
```

Restart app and worker:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production restart app worker
```

Stop:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production down
```

## Checks

Open in a browser:

```text
https://YOUR_DOMAIN/health
```

Expected response:

```json
{"status":"ok","service":"meeting-assistant"}
```

Then write `/start` to the Telegram bot.

## Notes

- PostgreSQL has no public port in `docker-compose.prod.yml`; it is available only inside
  the Docker network.
- The app installs Telegram webhook on startup when `TELEGRAM_USE_WEBHOOK=true`.
- Caddy obtains HTTPS certificates automatically after DNS points to the VPS.
