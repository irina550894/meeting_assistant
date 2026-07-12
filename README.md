# Telegram-бот "Ассистент по встречам"

MVP Telegram-бота для записи пользователей на онлайн-встречи с Ириной Бирюковой.
Пользователь выбирает тип встречи, дату и свободный слот, оставляет имя, email и
комментарий. Администратор получает заявку в Telegram, подтверждает, отклоняет,
переносит или блокирует пользователя. После подтверждения создается событие в
Google Calendar.

## Статус MVP

- Этапы 1-10 реализованы и развернуты на production VPS.
- Этап 11: сквозной UAT пройден, найденные дефекты исправлены и задеплоены.
- Этап 12: финальная приемка, инструкции и ограничения зафиксированы.
- Production URL: `https://calendar.finforbiz.pro/health`.

## Стек

- Python 3.12
- aiogram 3.x
- FastAPI + Uvicorn
- PostgreSQL 16
- SQLAlchemy 2.x + Alembic
- PostgreSQL-backed worker без Redis/Celery
- Docker Compose
- Caddy HTTPS
- Google Calendar API

## Локальный запуск

1. Создать и активировать Python 3.12 virtual environment.
2. Установить зависимости:

```powershell
pip install -e ".[dev]"
```

3. Заполнить локальный `.env`. Реальные значения не коммитить.
4. Настроить локальную PostgreSQL без вывода пароля:

```powershell
.\.venv\Scripts\python.exe scripts\configure_local_postgres_env.py
```

5. Применить миграции:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

6. Проверить локальную БД и worker diagnostics:

```powershell
.\.venv\Scripts\python.exe scripts\check_local_runtime.py
```

7. Запустить FastAPI:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

8. Открыть healthcheck:

```text
http://127.0.0.1:8000/health
```

9. Запустить worker:

```powershell
.\.venv\Scripts\python.exe -m app.worker.main
```

10. Для ручной Telegram-проверки локально запустить polling:

```powershell
.\.venv\Scripts\python.exe -m app.integrations.telegram.run_polling
```

Для persistence в polling:

```dotenv
TELEGRAM_STORAGE=postgres
```

Если `TELEGRAM_STORAGE` не задан или равен `memory`, polling использует память
процесса, и данные пропадают после остановки.

## Проверки

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m compileall app tests scripts
.\.venv\Scripts\python.exe -m pytest
```

Финальный статус на 12.07.2026:

- `ruff`: passed.
- `compileall`: passed.
- `pytest`: 84 passed, 1 warning.
- Production healthcheck: HTTP 200.
- Production containers: `app` healthy, `postgres` healthy, `worker` up.

## Инструкция администратора

1. Откройте Telegram-бота и используйте `/admin`.
2. Раздел с заявками показывает ожидающие и активные заявки.
3. В карточке заявки проверьте имя, Telegram username, email, тип встречи,
   длительность, дату, время `МСК`, комментарий.
4. Если заявка корректна, нажмите подтверждение. Бот создаст событие в Google
   Calendar, а пользователь получит Telegram-уведомление.
5. Если заявка не подходит, отклоните ее с причиной. Внутренний резерв слота
   будет снят.
6. Если пользователь отменил или администратор отменил подтвержденную встречу,
   событие Google Calendar отменяется, а слот снова становится свободным.
7. Для переноса пользователь создает новую заявку. После подтверждения новой
   заявки старая встреча переводится в статус перенесенной, старое событие
   Google Calendar отменяется.
8. Для блокировки используйте админ-действие блокировки. Активные подтвержденные
   встречи пользователя отменяются в календаре.
9. Для диагностики используйте `/diag`. Вывод показывает только безопасные
   configured true/false флаги и не раскрывает секреты.

Доступные admin-разделы:

- `/admin` - заявки, фильтры, пользователи.
- `Расписание` - рабочие часы и настройки расписания.
- `Ограничения` - закрытые дни.
- `Типы встреч` - включение, отключение и добавление типов встреч.
- `Фильтры заявок` - просмотр заявок по статусам.

## Production эксплуатация

Фактическая production-схема:

- VPS folder: `/home/irina/meeting_assistant`
- Docker services: `postgres`, `app`, `worker`
- App port: `127.0.0.1:8010 -> container 8000`
- HTTPS reverse proxy: системный Caddy на VPS
- Domain: `calendar.finforbiz.pro`

Основная команда запуска на VPS:

```bash
cd /home/irina/meeting_assistant
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  up -d --build postgres app worker
```

Перезапуск app и worker:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  restart app worker
```

Проверка контейнеров:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  ps
```

## Логи и диагностика

App logs:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  logs -f app
```

Worker logs:

```bash
sudo docker compose --project-directory /home/irina/meeting_assistant \
  -f /home/irina/meeting_assistant/docker-compose.prod.yml \
  -f /home/irina/meeting_assistant/docker-compose.system-caddy.yml \
  --env-file /home/irina/meeting_assistant/.env.production \
  logs -f worker
```

Полезные события:

- `healthcheck_ok` - приложение отвечает.
- `telegram_webhook_configured` - Telegram webhook установлен.
- `worker_started` - worker запущен.
- `background_jobs_recovered` - фоновые задачи восстановлены.
- `job_started`, `job_succeeded`, `job_failed` - выполнение фоновых задач.
- `google_event_created` - создано событие Google Calendar.
- `google_event_cancelled` - событие Google Calendar отменено.
- `google_api_error` - ошибка Google API.
- `telegram_api_error` - ошибка Telegram API.

Признаки проблем:

- Google Calendar недоступен: в логах появляются `google_api_error`, событие
  календаря не создается или не отменяется.
- Telegram webhook не работает: нет входящих webhook-событий, есть ошибки
  Telegram API, healthcheck при этом может оставаться зеленым.
- Worker не выполняет задачи: нет `worker_started`, `job_started` или
  `job_succeeded`, либо контейнер `worker` не в статусе `Up`.

## Известные ограничения MVP

- Email-уведомления реализованы через Google Calendar invitations/cancellations.
  Отдельного SMTP/email-провайдера в утвержденном стеке MVP нет.
- До отправки письма нельзя надежно доказать существование конкретного mailbox
  без внешнего email-verification сервиса. Текущая проверка валидирует формат и
  доменную доставляемость.
- Резервные копии базы данных не входят в MVP.
- Лимит встреч в день в MVP выключен, но модель допускает будущую настройку.
- Telegram Mini App не входит в MVP; backend подготовлен к будущему API.
- Production использует системный Caddy VPS, потому что на сервере уже работают
  другие домены. Caddy-контейнер из `docker-compose.prod.yml` в текущей схеме не
  запускается.

## Backlog

### v1.1

- Отдельный email-провайдер или SMTP для уведомлений вне Google Calendar.
- Email-verification сервис для более строгой проверки mailbox.
- Telegram Mini App поверх текущего FastAPI/backend-ядра.
- Админ-экран для просмотра audit-log и ошибок без SSH.
- Настраиваемый дневной лимит встреч из админ-интерфейса.

### v2

- Мультиадминность и несколько календарей.
- Резервные копии PostgreSQL и регламент восстановления.
- Расширенная аналитика заявок и конверсий.
- Очередь фоновых задач с отдельной инфраструктурой, если нагрузка превысит MVP.
