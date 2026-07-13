#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/home/irina/meeting_assistant}"
ARCHIVE_PATH="${ARCHIVE_PATH:?ARCHIVE_PATH is required}"
COMMIT_SHA="${COMMIT_SHA:-unknown}"
ENV_FILE="${DEPLOY_DIR}/.env.production"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://127.0.0.1:8010/health}"

COMPOSE_ARGS=(
  --project-directory "${DEPLOY_DIR}"
  -f "${DEPLOY_DIR}/docker-compose.prod.yml"
  -f "${DEPLOY_DIR}/docker-compose.system-caddy.yml"
  --env-file "${ENV_FILE}"
)

echo "deploy_started commit=${COMMIT_SHA}"

if [ ! -f "${ARCHIVE_PATH}" ]; then
  echo "deploy_failed reason=archive_not_found"
  exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
  echo "deploy_failed reason=env_file_not_found"
  exit 1
fi

install -d "${DEPLOY_DIR}"
tar -xf "${ARCHIVE_PATH}" -C "${DEPLOY_DIR}"

cd "${DEPLOY_DIR}"

sudo docker compose "${COMPOSE_ARGS[@]}" up -d --build postgres app worker
sudo docker compose "${COMPOSE_ARGS[@]}" ps

if command -v curl >/dev/null 2>&1; then
  curl --fail --silent --show-error --retry 12 --retry-delay 5 "${LOCAL_HEALTH_URL}"
  echo
else
  echo "deploy_warning reason=curl_not_found healthcheck_skipped"
fi

sudo docker compose "${COMPOSE_ARGS[@]}" logs --tail=80 app worker

rm -f "${ARCHIVE_PATH}" /tmp/deploy_production.sh

echo "deploy_finished commit=${COMMIT_SHA}"

