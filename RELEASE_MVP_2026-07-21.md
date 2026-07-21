# Финальный статус MVP на 21.07.2026

## Результат

Проект доведен до рабочего MVP и проверен в Telegram.

Mini App работает как дополнение к действующему Telegram-боту, а не заменяет его. Основной бот, заявки, согласования, Google Calendar и Mini App проверены на production.

## Production

- Mini App: `https://calendar.finforbiz.pro/miniapp/`
- Health: `https://calendar.finforbiz.pro/health`
- VPS project dir: `/home/irina/meeting_assistant`
- Compose files: `docker-compose.prod.yml` + `docker-compose.system-caddy.yml`
- App binding: `127.0.0.1:8010 -> container 8000`
- Production branch: `master`
- Working branch: `dev`
- Финальный runtime commit: `0b4a476 Archive cancelled mini app bookings`

## Что реализовано

- Пользовательская запись через Telegram-бота.
- Пользовательская запись через Telegram Mini App.
- Согласие на обработку персональных данных перед отправкой заявки.
- Пошаговый выбор: данные, месяц/дата, время, проверка заявки.
- Запрет перехода на следующие шаги без выполнения предыдущих условий.
- Админка Mini App для заявок, расписания и типов встреч.
- Закрытые дни и закрытые часы.
- Скрытие недоступных дней и слотов.
- Подтверждение, отклонение и отмена заявок.
- Отмена пользователем и администратором не позднее чем за 2 часа до встречи.
- Архив для прошедших, отклоненных и отмененных заявок.
- Простая нумерация заявок.
- Google OAuth status в Mini App: кнопка `OAuth` с зеленым/красным статусом.
- Создание и отмена событий Google Calendar.
- Ссылки на видеовстречу в подтвержденных заявках.
- Telegram flow сохранен и проверен после добавления Mini App.

## Проверки

Локально перед финальным закрытием проходили:

- `frontend tsc -b`
- `frontend vite build`
- `pytest tests/test_miniapp_frontend_static.py tests/test_miniapp_admin_api.py tests/test_miniapp_user_api.py`
- профильные тесты Telegram router/menu на предыдущих этапах Mini App

Production-проверки:

- `/health` возвращает `{"status":"ok","service":"meeting-assistant","environment":"production"}`
- `/miniapp/` возвращает актуальный Mini App frontend
- контейнер `app` в статусе `healthy`
- контейнер `worker` в статусе `Up`
- в логах есть `worker_started` и `healthcheck_ok`
- ручная проверка в Telegram пройдена пользователем

## Ручная проверка после будущих изменений

1. Открыть Telegram-бота и выполнить `/start`.
2. Проверить кнопку `Открыть`.
3. Открыть Mini App.
4. Создать заявку: `Запись` -> согласие -> данные -> месяц -> день -> время -> отправка.
5. Проверить заявку во вкладке `Заявки`.
6. Подтвердить заявку в `Админ`.
7. Проверить ссылку на видеовстречу.
8. Проверить событие в Google Calendar.
9. Проверить отмену пользователем.
10. Проверить отмену администратором.
11. Проверить, что отмененные и отклоненные заявки уходят в архив.
12. Проверить Telegram-бот без Mini App: заявки, согласования, отклонения, отмены.

## Production-команды проверки

```bash
cd /home/irina/meeting_assistant
docker compose -f docker-compose.prod.yml -f docker-compose.system-caddy.yml --env-file .env.production ps app worker
curl -fsS http://127.0.0.1:8010/health
docker compose -f docker-compose.prod.yml -f docker-compose.system-caddy.yml --env-file .env.production logs --tail=100 app worker
```

Публичные URL:

```text
https://calendar.finforbiz.pro/health
https://calendar.finforbiz.pro/miniapp/
```

## Переменные окружения

Значения не хранить в коде, документах и логах.

Основные имена переменных:

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
- `MINI_APP_ENABLED`
- `MINI_APP_FRONTEND_DIST_PATH`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `GOOGLE_CALENDAR_ID`

## Что обязательно сделать после закрытия

1. Сменить root-пароль на VPS.
2. Сохранить резервную копию `.env.production` в защищенном хранилище.
3. Сделать резервную копию PostgreSQL.
4. По возможности перейти на SSH-ключи и отключить парольный вход root.

## Backlog после MVP

- Настроить полностью автоматический deploy через GitHub Actions.
- Добавить регулярный backup PostgreSQL.
- Добавить мониторинг ошибок Google Calendar и Telegram без входа по SSH.
- Сделать отдельную админскую авторизацию для Mini App.
- Добавить audit/report экран для истории действий администратора.
