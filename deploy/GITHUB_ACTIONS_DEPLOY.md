# Автоматический деплой через GitHub Actions

Документ описывает автоматическое обновление production-бота после отправки кода
в GitHub.

## 1. Что будет происходить автоматически

После push в ветку `master`, если изменились код, Docker/config-файлы, workflow,
миграции или тесты, GitHub Actions выполнит:

1. Заберет код из GitHub.
2. Установит Python 3.12.
3. Установит зависимости проекта.
4. Запустит проверки:
   - `ruff check app tests scripts`;
   - `compileall app tests scripts`;
   - `pytest`.
5. Проверит наличие deploy secrets.

Если GitHub Actions secrets еще не настроены, workflow завершит проверки и
пропустит deploy. После настройки secrets следующие push в `master` будут
деплоить production автоматически.

Если secrets настроены, workflow:

1. Создаст tar-архив из tracked-файлов Git.
2. Загрузит архив и deploy-скрипт на VPS в `/tmp`.
3. На VPS распакует архив в `/home/irina/meeting_assistant`.
4. Пересоберет и перезапустит production services:
   - `postgres`;
   - `app`;
   - `worker`.
5. Проверит локальный healthcheck `http://127.0.0.1:8010/health`.
6. Покажет состояние контейнеров и последние безопасные app/worker logs.

Документационные HTML/Markdown-файлы сами по себе не запускают production deploy.

## 2. Какие файлы добавлены

1. `.github/workflows/deploy-production.yml`
   - GitHub Actions workflow.
   - Запускает тесты и деплой на VPS.

2. `scripts/deploy_production.sh`
   - Скрипт, который выполняется на VPS.
   - Распаковывает архив, запускает Docker Compose, проверяет healthcheck.

3. `deploy/GITHUB_ACTIONS_DEPLOY.md`
   - Эта инструкция.

## 3. Что нужно настроить вручную в GitHub

Откройте репозиторий GitHub:

```text
https://github.com/irina550894/meeting_assistant
```

Перейдите:

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

Создайте secrets:

### Обязательные

1. `VPS_HOST`
   - Значение: IP или домен VPS.
   - Для текущего проекта: `83.222.26.253`.

2. `VPS_USER`
   - Значение: SSH user.
   - Для текущего проекта: `irina`.

3. `VPS_SSH_KEY`
   - Значение: приватный SSH-ключ, которым GitHub Actions будет заходить на VPS.
   - Не публиковать, не коммитить, не отправлять в чат.

### Рекомендуемые

4. `VPS_PORT`
   - Значение: SSH port.
   - Обычно: `22`.
   - Если secret не задан, workflow использует `22`.

5. `VPS_DEPLOY_PATH`
   - Значение: путь проекта на VPS.
   - Для текущего проекта: `/home/irina/meeting_assistant`.
   - Если secret не задан, workflow использует `/home/irina/meeting_assistant`.

6. `VPS_KNOWN_HOSTS`
   - Значение: строка known_hosts для VPS.
   - Рекомендуется для защиты от подмены SSH host.
   - Если secret не задан, workflow выполнит `ssh-keyscan`.

## 4. Как создать отдельный SSH-ключ для GitHub Actions

Рекомендуется использовать отдельный deploy-key, а не личный SSH-ключ.

На своем компьютере выполните:

```bash
ssh-keygen -t ed25519 -C "github-actions-meeting-assistant-deploy" -f ~/.ssh/meeting_assistant_github_actions
```

Будут созданы два файла:

```text
~/.ssh/meeting_assistant_github_actions
~/.ssh/meeting_assistant_github_actions.pub
```

Приватный ключ:

```text
~/.ssh/meeting_assistant_github_actions
```

нужно вставить в GitHub secret `VPS_SSH_KEY`.

Публичный ключ:

```text
~/.ssh/meeting_assistant_github_actions.pub
```

нужно добавить на VPS в:

```text
/home/irina/.ssh/authorized_keys
```

Права на VPS должны быть:

```bash
chmod 700 /home/irina/.ssh
chmod 600 /home/irina/.ssh/authorized_keys
```

## 5. Как получить VPS_KNOWN_HOSTS

На своем компьютере выполните:

```bash
ssh-keyscan -p 22 83.222.26.253
```

Скопируйте весь вывод команды в GitHub secret:

```text
VPS_KNOWN_HOSTS
```

Если SSH port отличается, замените `22` на фактический порт.

## 6. Что нужно проверить на VPS

### 6.1. Проект и env

На VPS должны существовать:

```text
/home/irina/meeting_assistant
/home/irina/meeting_assistant/.env.production
```

Права env-файла:

```bash
chmod 600 /home/irina/meeting_assistant/.env.production
```

Значения `.env.production` не выводить в терминал, логи и чат.

### 6.2. Docker Compose

Проверьте, что пользователь `irina` может запускать Docker Compose без ввода
пароля в non-interactive SSH-сессии:

```bash
ssh irina@83.222.26.253 "sudo -n docker ps"
```

Если команда просит пароль или завершается ошибкой, GitHub Actions deploy не
сможет выполнить `sudo docker compose`.

Варианты решения:

1. Настроить passwordless sudo только для нужных docker-команд.
2. Добавить пользователя `irina` в docker group и убрать `sudo` из скрипта
   отдельной доработкой.

Для текущего проекта скрипт использует `sudo docker compose`, как и ручной deploy.

### 6.3. System Caddy

На VPS уже используется system Caddy. В `/etc/caddy/Caddyfile` должен быть блок:

```caddyfile
calendar.finforbiz.pro {
  encode zstd gzip
  reverse_proxy 127.0.0.1:8010
}
```

GitHub Actions не меняет системный Caddy.

## 7. Как запустить первый deploy

После добавления secrets:

1. Откройте GitHub repository.
2. Перейдите в `Actions`.
3. Выберите workflow `Deploy production`.
4. Нажмите `Run workflow`.
5. Выберите ветку `master`.
6. Запустите workflow.

Если все настроено правильно, workflow:

1. Пройдет тесты.
2. Подключится к VPS.
3. Соберет Mini App frontend.
4. Подключится к VPS.
5. Пересоберет `app` и `worker`.
6. Проверит healthcheck и `/miniapp/`.

## 8. Как понять, что deploy прошел успешно

Если secrets еще не настроены, workflow покажет:

```text
Deploy will be skipped because required secrets are missing.
Tests completed, deploy skipped. Configure GitHub Actions secrets to enable automatic VPS deploy.
```

Это не ошибка production. Это означает, что проверки прошли, но deploy еще не
включен.

Если secrets настроены, в GitHub Actions должны быть видны шаги:

1. `Run lint` - success.
2. `Run compile check` - success.
3. `Run tests` - success.
4. `Build Mini App frontend` - success.
5. `Upload archive and deploy script` - success.
6. `Deploy on VPS` - success.

В output deploy должно быть:

```text
deploy_started commit=<sha>
...
deploy_finished commit=<sha>
```

И healthcheck:

```json
{"status":"ok","service":"meeting-assistant","environment":"production"}
```

В output deploy также должно быть:

```text
miniapp_check_ok url=http://127.0.0.1:8010/miniapp/
```

## 9. Что делать при ошибке

### 9.1. Не настроен secret

Ошибка вида:

```text
VPS_HOST is not configured
VPS_USER is not configured
VPS_SSH_KEY is not configured
```

Решение: добавить недостающий secret в GitHub repository settings.

### 9.2. SSH не подключается

Проверить:

1. `VPS_HOST`.
2. `VPS_USER`.
3. `VPS_PORT`.
4. Приватный ключ в `VPS_SSH_KEY`.
5. Публичный ключ в `/home/irina/.ssh/authorized_keys`.
6. `VPS_KNOWN_HOSTS`.

### 9.3. Docker просит пароль

Проверить:

```bash
ssh irina@83.222.26.253 "sudo -n docker ps"
```

Если команда не проходит, настроить passwordless sudo для Docker.

### 9.4. Healthcheck не проходит

Проверить на VPS:

```bash
cd /home/irina/meeting_assistant
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  ps
```

И logs:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  logs --tail=100 app worker
```

Секреты из `.env.production` не выводить.

### 9.5. Mini App не открывается

Проверить на VPS:

```bash
curl --fail --silent --show-error http://127.0.0.1:8010/miniapp/ >/dev/null
```

Затем проверить app logs:

```bash
cd /home/irina/meeting_assistant
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  logs --tail=100 app
```

Ожидаемое событие: `mini_app_frontend_mounted`.

Если есть `mini_app_frontend_dist_missing`, проверить Docker build frontend stage
и значение `MINI_APP_FRONTEND_DIST_PATH`.

## 10. Важные ограничения

1. Workflow не хранит и не выводит `.env.production`.
2. Workflow не меняет system Caddy.
3. Workflow не запускает Caddy-контейнер.
4. Workflow не делает backup PostgreSQL.
5. Workflow деплоит tracked-файлы из Git, как ручной `git archive` deploy.
6. Frontend-зависимости устанавливаются в GitHub Actions и Docker build без
   записи секретов во frontend.
7. Если миграции Alembic есть в коде, app выполнит `alembic upgrade head` при
   запуске контейнера.
8. Если нужен rollback, его нужно делать отдельной процедурой.

## 11. Алгоритм rollback вручную

Если новый deploy сломал production:

1. Найти предыдущий рабочий commit hash в GitHub.
2. Локально выполнить:

```bash
git checkout <previous_commit>
git archive --format=tar -o rollback.tar HEAD
scp rollback.tar irina@83.222.26.253:/tmp/rollback.tar
ssh irina@83.222.26.253 "tar -xf /tmp/rollback.tar -C /home/irina/meeting_assistant"
```

3. На VPS перезапустить production services:

```bash
ssh irina@83.222.26.253 "sudo docker compose --project-directory /home/irina/meeting_assistant -f /home/irina/meeting_assistant/docker-compose.prod.yml -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml --env-file /home/irina/meeting_assistant/.env.production up -d --build postgres app worker"
```

4. Проверить healthcheck.

Rollback миграций БД требует отдельного анализа перед выполнением.
