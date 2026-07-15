# Проектирование API и shared use-cases для Telegram Mini App

Дата: 2026-07-14  
Этап: 1. Проектирование API и shared use-cases  
Основание: `ТЗ_Telegram_Mini_App_ассистент_по_встречам.md`

## 1. Цель документа

Этот документ фиксирует технический дизайн этапа 1 перед написанием кода.

Главная задача этапа: спроектировать Mini App API так, чтобы Telegram Mini App и существующий Telegram-бот использовали одно backend-ядро и одни application use-cases, а не две независимые реализации бизнес-сценариев.

Код на этом этапе не пишется.

## 2. Текущее состояние

### 2.1. Что уже хорошо подходит для Mini App

В проекте уже есть UI-независимые core-сервисы:

1. `app/core/booking` - заявки, статусы, резервы, отмена, перенос.
2. `app/core/scheduling` - расчет доступных слотов.
3. `app/core/user_flow` - пользовательские операции без привязки к aiogram.
4. `app/core/admin_flow` - админские операции без прямой привязки к UI.
5. `app/integrations/google_calendar` - Google Calendar gateway.
6. `app/worker` - TTL, напоминания, retry, cleanup.
7. `app/persistence/repositories/telegram_runtime.py` - SQLAlchemy-backed store, который уже реализует большинство нужных портов.

### 2.2. Что нельзя копировать в Mini App API

В текущих Telegram routers есть orchestration, которую нужно вынести в shared application services:

1. Создание заявки:
   - `UserFlowService.create_booking_from_draft`;
   - сохранение пользователя;
   - сохранение booking result;
   - постановка worker jobs;
   - отправка Telegram-уведомления администратору.
2. Отмена заявки:
   - `BookingService.cancel_booking_by_user`;
   - сохранение booking;
   - audit-log;
   - отмена Google Calendar event;
   - уведомления.
3. Подтверждение заявки:
   - Google Calendar confirmation gateway;
   - `AdminFlowService.confirm_booking`;
   - сохранение booking;
   - завершение переноса старой заявки;
   - audit-log;
   - постановка reminder jobs;
   - уведомление пользователя.
4. Отклонение заявки:
   - `AdminFlowService.reject_booking`;
   - освобождение резерва;
   - audit-log;
   - уведомление пользователя.

Если оставить эту orchestration в aiogram routers и повторить ее в FastAPI routes, бот и Mini App быстро начнут расходиться.

## 3. Предлагаемая архитектура

### 3.1. Новый application layer

Добавить слой:

`app/application`

Назначение:

1. Хранить shared use-cases для Telegram bot-flow и Mini App API.
2. Хранить общие ports/dependencies без привязки к aiogram.
3. Быть тонким orchestration-слоем над `app/core`.

Предлагаемая структура:

```text
app/application/
  __init__.py
  deps.py
  ports.py
  sources.py
  user_booking_use_cases.py
  admin_booking_use_cases.py
  admin_settings_use_cases.py
  mini_app_auth.py
  mini_app_analytics.py
```

### 3.2. Почему не хранить это в `app/integrations/telegram`

Сейчас `UserFlowDependencies`, `AdminFlowDependencies` и ports лежат в `app/integrations/telegram/ports.py`. Для Mini App это имя становится неверным, потому что зависимости уже нужны не только Telegram-интеграции.

Рекомендуемый план:

1. Перенести общие protocols/dataclasses в `app/application/ports.py` и `app/application/deps.py`.
2. В `app/integrations/telegram/ports.py` временно оставить re-export для обратной совместимости.
3. Telegram routers продолжат работать, но будут зависеть от общего application layer.

### 3.3. Источники действий

Добавить enum/константы:

```text
ActionSource:
  telegram_bot
  mini_app
  system
  worker
```

Использование:

1. В audit-log payload или отдельном поле.
2. В `bookings.created_source`.
3. В analytics events.

## 4. Shared use-cases

### 4.1. UserBookingUseCases

Файл:

`app/application/user_booking_use_cases.py`

Назначение:

Общий пользовательский application service для Telegram bot-flow и Mini App.

Методы:

1. `ensure_user_from_telegram(...)`
   - создать или обновить пользователя по Telegram ID;
   - обновить username;
   - сохранить пользователя.
2. `accept_consent(...)`
   - принять согласие;
   - сохранить пользователя;
   - записать audit source.
3. `list_meeting_types()`
   - вернуть активные типы встреч.
4. `available_dates(...)`
   - вернуть доступные даты по настройкам расписания.
5. `available_slots(...)`
   - вернуть слоты для даты, типа и длительности.
6. `create_booking(...)`
   - проверить draft;
   - создать заявку;
   - сохранить пользователя;
   - сохранить заявку и резерв;
   - добавить audit source;
   - поставить worker job;
   - отправить уведомление администратору;
   - вернуть созданную заявку.
7. `list_user_bookings(...)`
   - вернуть заявки текущего пользователя.
8. `get_user_booking(...)`
   - вернуть заявку пользователя или ошибку доступа.
9. `cancel_user_booking(...)`
   - отменить pending или confirmed booking;
   - сохранить booking;
   - записать audit source;
   - отменить Google Calendar event, если есть;
   - отправить уведомление.
10. `prepare_reschedule(...)`
   - проверить, что заявка принадлежит пользователю;
   - вернуть данные старой заявки для формы переноса.
11. `create_reschedule_booking(...)`
   - создать новую pending-заявку с `previous_booking_id`;
   - старая заявка получает `reschedule_requested` через существующую core-логику.

### 4.2. AdminBookingUseCases

Файл:

`app/application/admin_booking_use_cases.py`

Назначение:

Общий админский application service для Telegram admin-flow и Mini App admin API.

Методы:

1. `ensure_admin(...)`
   - проверить Telegram ID администратора.
2. `dashboard(...)`
   - вернуть агрегаты по заявкам.
3. `list_bookings(...)`
   - список заявок с фильтрами.
4. `get_booking_card(...)`
   - заявка + пользователь + тип встречи.
5. `confirm_booking(...)`
   - подтвердить pending booking;
   - создать Google Calendar event;
   - сохранить booking;
   - завершить перенос старой заявки, если нужно;
   - сохранить audit;
   - поставить reminder jobs;
   - уведомить пользователя.
6. `reject_booking(...)`
   - отклонить pending booking;
   - освободить резерв;
   - сохранить audit;
   - уведомить пользователя.
7. `cancel_confirmed_booking(...)`
   - админская отмена confirmed-встречи;
   - отменить Google Calendar event;
   - уведомить пользователя.
8. `calendar_plan(...)`
   - вернуть ближайшие встречи для календарного блока.

### 4.3. AdminSettingsUseCases

Файл:

`app/application/admin_settings_use_cases.py`

Назначение:

Общий application service для управления расписанием, ограничениями и типами встреч из Telegram-бота и Mini App.

Методы:

1. `get_schedule_settings(...)`
   - вернуть timezone, lead time, horizon, slot step, buffer, cancellation deadline.
2. `list_working_hours(...)`
   - вернуть рабочие часы по дням недели.
3. `update_working_hours(...)`
   - изменить рабочие часы, если persistence layer будет расширен под это действие.
4. `list_restrictions(...)`
   - вернуть ближайшие ограничения расписания.
5. `add_closed_day_restriction(...)`
   - добавить закрытый день.
6. `delete_restriction(...)`
   - удалить ограничение.
7. `list_meeting_types_admin(...)`
   - вернуть активные и неактивные типы встреч.
8. `add_meeting_type(...)`
   - добавить тип встречи.
9. `set_meeting_type_active(...)`
   - включить или отключить тип встречи.

Примечание:

Часть методов уже поддерживается текущим `AdminSettingsStore`. Если для Mini App потребуется редактирование рабочих часов, нужно отдельно расширить store и добавить миграционно безопасные тесты.

### 4.4. MiniAppAuthService

Файл:

`app/application/mini_app_auth.py`

Назначение:

1. Проверка Telegram WebApp `initData`.
2. Проверка `auth_date`.
3. Создание/обновление пользователя.
4. Создание session cookie через session store.

Методы:

1. `validate_init_data(raw_init_data: str)`.
2. `authenticate(raw_init_data: str)`.
3. `create_session(user, telegram_auth_date)`.
4. `get_current_session(session_token)`.
5. `revoke_session(session_token)`.

### 4.5. MiniAppAnalyticsService

Файл:

`app/application/mini_app_analytics.py`

Назначение:

1. Записывать события Mini App.
2. Не ломать основной сценарий при ошибке записи analytics.
3. Минимизировать персональные данные.

Методы:

1. `track_event(...)`.
2. Специализированные helpers вроде `track_opened(...)`, `track_booking_form_abandoned(...)`, `track_admin_action(...)` можно добавить позже поверх общего `track_event(...)`, если frontend начнет активно переиспользовать одинаковые события.

## 5. Ports и dependencies

### 5.1. Переиспользуемые ports

Из текущего `app/integrations/telegram/ports.py` нужно перенести или переэкспортировать:

1. `UserStore`.
2. `MeetingTypeStore`.
3. `BookingStore`.
4. `ScheduleProvider`.
5. `UserFlowNotifier`.
6. `AdminNotifier`.
7. `CalendarConfirmationGateway`.
8. `CalendarEventGateway`.
9. `BackgroundJobSchedulerPort`.
10. `DiagnosticsProvider`.
11. `AdminSettingsStore`.

### 5.2. Новые ports

Добавить:

1. `MiniAppSessionStore`.
2. `MiniAppAnalyticsStore`.

`MiniAppSessionStore`:

```text
create_session(user_id, telegram_auth_date, expires_at) -> session token
get_session(session token hash) -> session record
touch_session(session id, now) -> None
revoke_session(session id, now) -> None
```

`MiniAppAnalyticsStore`:

```text
save_event(event) -> None
```

### 5.3. Dependency builder

Добавить общий builder:

`app/application/deps.py`

Назначение:

1. Собрать `BookingService`.
2. Собрать `UserFlowService`.
3. Собрать `AdminFlowService`.
4. Собрать SQL store.
5. Собрать Google Calendar gateways.
6. Собрать notifiers.
7. Собрать background job scheduler.
8. Вернуть application use-cases.

Важно:

1. Telegram runtime и FastAPI Mini App API должны использовать одинаковую сборку зависимостей.
2. Для локального режима допускается `InMemoryRuntimeStore`, но production Mini App должна работать только с PostgreSQL-backed storage.

## 6. FastAPI структура

Предлагаемая структура:

```text
app/interfaces/http/
  routes/
    miniapp_auth.py
    miniapp_user.py
    miniapp_admin.py
    miniapp_analytics.py
  schemas/
    miniapp.py
  dependencies/
    miniapp.py
```

Можно начать с одного router-файла `miniapp.py`, но для читаемости лучше разделить по зонам.

### 6.1. Общие HTTP dependencies

Файл:

`app/interfaces/http/dependencies/miniapp.py`

Dependencies:

1. `get_mini_app_deps`.
2. `get_current_mini_app_user`.
3. `get_current_mini_app_admin`.
4. `get_user_use_cases`.
5. `get_admin_use_cases`.
6. `get_analytics_service`.

## 7. API contracts

### 7.1. Auth

`POST /api/miniapp/auth/telegram`

Request:

```json
{
  "init_data": "query_id=..."
}
```

Response:

```json
{
  "user": {
    "id": "uuid",
    "telegram_id": 123456789,
    "telegram_username": "username",
    "full_name": "Имя",
    "email": "user@example.com",
    "has_consent": true,
    "is_blocked": false,
    "is_admin": false
  }
}
```

Cookie:

1. `MINI_APP_COOKIE_NAME`.
2. `HttpOnly`.
3. `Secure` в production.
4. `SameSite` уточнить при проверке в Telegram WebView.

### 7.2. Config

`GET /api/miniapp/config`

Response:

```json
{
  "timezone": "Europe/Moscow",
  "consent_url": "https://...",
  "policy_url": "https://...",
  "features": {
    "admin": true,
    "analytics": true
  }
}
```

### 7.3. Profile

`GET /api/miniapp/profile`

Response совпадает с `auth.user`.

`PATCH /api/miniapp/profile`

Request:

```json
{
  "full_name": "Имя",
  "email": "user@example.com"
}
```

Примечание:

Для MVP можно не делать отдельное обновление профиля, если имя/email обновляются при создании заявки.

### 7.4. Consent

`POST /api/miniapp/consent`

Request:

```json
{
  "accepted": true
}
```

Response:

```json
{
  "has_consent": true,
  "accepted_at": "2026-07-14T10:00:00+03:00"
}
```

### 7.5. Meeting types

`GET /api/miniapp/meeting-types`

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Консультация",
      "allowed_durations_minutes": [30, 60, 90],
      "is_fixed_duration": false
    }
  ]
}
```

### 7.6. Available dates

`GET /api/miniapp/available-dates?meeting_type_id={uuid}&duration_minutes=60`

Response:

```json
{
  "items": [
    {
      "date": "2026-07-20",
      "is_available": true
    }
  ]
}
```

Примечание:

В текущем `UserFlowService.available_dates` даты считаются без проверки наличия слотов. Для календаря Mini App лучше возвращать `is_available`, но это может потребовать расчета слотов по датам. Если это дорого, в MVP можно вернуть только список дат, а слоты грузить после выбора даты.

### 7.7. Slots

`GET /api/miniapp/slots?date=2026-07-20&meeting_type_id={uuid}&duration_minutes=60`

Response:

```json
{
  "items": [
    {
      "starts_at": "2026-07-20T10:00:00+03:00",
      "ends_at": "2026-07-20T11:00:00+03:00",
      "label": "10:00"
    }
  ]
}
```

### 7.8. Create booking

`POST /api/miniapp/bookings`

Request:

```json
{
  "full_name": "Имя",
  "email": "user@example.com",
  "meeting_type_id": "uuid",
  "duration_minutes": 60,
  "starts_at": "2026-07-20T10:00:00+03:00",
  "ends_at": "2026-07-20T11:00:00+03:00",
  "user_comment": "Комментарий",
  "previous_booking_id": null
}
```

Response:

```json
{
  "booking": {
    "id": "uuid",
    "status": "pending",
    "starts_at": "2026-07-20T10:00:00+03:00",
    "ends_at": "2026-07-20T11:00:00+03:00",
    "meeting_type_id": "uuid",
    "duration_minutes": 60,
    "is_reschedule_request": false,
    "previous_booking_id": null
  }
}
```

### 7.9. User bookings

`GET /api/miniapp/bookings?status=confirmed`

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "status": "confirmed",
      "meeting_type_name": "Консультация",
      "starts_at": "2026-07-20T10:00:00+03:00",
      "ends_at": "2026-07-20T11:00:00+03:00",
      "duration_minutes": 60,
      "meeting_url": "https://..."
    }
  ]
}
```

`GET /api/miniapp/bookings/{booking_id}`

Возвращает детальную карточку заявки текущего пользователя.

### 7.10. Cancel booking

`POST /api/miniapp/bookings/{booking_id}/cancel`

Request:

```json
{
  "reason": "Не смогу присутствовать"
}
```

Response:

```json
{
  "booking": {
    "id": "uuid",
    "status": "cancelled_by_user"
  }
}
```

### 7.11. Prepare reschedule

`POST /api/miniapp/bookings/{booking_id}/reschedule/prepare`

Response:

```json
{
  "previous_booking": {
    "id": "uuid",
    "starts_at": "2026-07-20T10:00:00+03:00",
    "meeting_type_id": "uuid",
    "duration_minutes": 60
  }
}
```

Создание новой заявки на перенос выполняется через `POST /api/miniapp/bookings` с `previous_booking_id`.

## 8. Admin API contracts

### 8.1. Dashboard

`GET /api/miniapp/admin/dashboard`

Response:

```json
{
  "metrics": {
    "pending": 3,
    "confirmed": 5,
    "reschedule_requested": 1,
    "cancelled": 2
  },
  "upcoming": [],
  "recent_pending": []
}
```

### 8.2. List bookings

`GET /api/miniapp/admin/bookings?status=pending`

Response:

```json
{
  "items": []
}
```

На этапе 4 pagination не добавлялась. Если список станет большим, добавить `limit`, `offset` или cursor отдельно.

### 8.3. Booking card

`GET /api/miniapp/admin/bookings/{booking_id}`

Response:

```json
{
  "booking": {},
  "user": {},
  "meeting_type": {}
}
```

Для MVP audit в карточке не возвращается. Источник действия и расширенный audit-log добавляются отдельным этапом.

### 8.4. Confirm booking

`POST /api/miniapp/admin/bookings/{booking_id}/confirm`

Request:

```json
{
  "meeting_url": "https://..."
}
```

Если `meeting_url` не передан, backend использует `DEFAULT_MEETING_URL`, если он настроен.

### 8.5. Reject booking

`POST /api/miniapp/admin/bookings/{booking_id}/reject`

Request:

```json
{
  "reason": "Причина"
}
```

### 8.6. Admin cancellation

Отдельный endpoint админской отмены заявки/встречи на этапе 4 не реализован.

Причина:

1. В текущем ядре есть `cancel_booking_by_user`, но нет отдельного правила `cancel_booking_by_admin`.
2. Нельзя подменять админскую отмену пользовательской отменой, потому что это исказит audit-log и actor/action.
3. Перед реализацией нужно добавить бизнес-правило, audit action и правила уведомлений.

Ожидаемый будущий endpoint:

`POST /api/miniapp/admin/bookings/{booking_id}/cancel`

### 8.7. Calendar plan

`GET /api/miniapp/admin/calendar`

Возвращает confirmed-встречи для календарного блока.

### 8.8. Schedule settings

`GET /api/miniapp/admin/schedule/settings`

Возвращает текущие настройки расписания:

```json
{
  "timezone": "Europe/Moscow",
  "min_booking_lead_days": 1,
  "booking_horizon_days": 30,
  "slot_step_minutes": 60,
  "meeting_buffer_minutes": 90
}
```

Изменение базовых настроек расписания на этапе 4 не реализовано и требует отдельного backend-контракта.

### 8.9. Working hours

`GET /api/miniapp/admin/schedule/working-hours`

Возвращает рабочие часы по дням недели.

Изменение рабочих часов на этапе 4 не реализовано. Если нужно редактирование из Mini App, добавить отдельный endpoint после согласования правил сохранения рабочих дней.

### 8.10. Schedule restrictions

`GET /api/miniapp/admin/schedule/restrictions?from=2026-07-14`

Возвращает ближайшие ограничения расписания.

`POST /api/miniapp/admin/schedule/restrictions/closed-day`

Добавляет закрытый день.

Request:

```json
{
  "restriction_date": "2026-07-20",
  "admin_comment": "Выходной"
}
```

`DELETE /api/miniapp/admin/schedule/restrictions/{restriction_id}`

Удаляет ограничение.

### 8.11. Meeting types admin

`GET /api/miniapp/admin/meeting-types`

Возвращает активные и неактивные типы встреч.

`POST /api/miniapp/admin/meeting-types`

Добавляет тип встречи.

Request:

```json
{
  "name": "Консультация",
  "allowed_durations_minutes": [30, 60],
  "is_fixed_duration": false
}
```

`PATCH /api/miniapp/admin/meeting-types/{meeting_type_id}`

Изменяет активность типа встречи.

Request:

```json
{
  "is_active": true
}
```

### 8.12. Mini App analytics

`POST /api/miniapp/analytics/event`

Endpoint требует Mini App session cookie.

Request:

```json
{
  "event_name": "booking_form_opened",
  "payload": {
    "screen": "booking"
  }
}
```

Response:

```json
{
  "ok": true
}
```

Правила:

1. Ошибка записи события логируется, но endpoint возвращает успешный ответ, чтобы analytics не ломала пользовательский сценарий.
2. В `payload` нельзя передавать секреты, Telegram `initData`, session token, email, телефон и текст комментария пользователя.
3. Для связи с пользователем backend использует текущую Mini App session.

## 9. Миграции

### 9.1. Рекомендуемые изменения

Добавить в `bookings`:

1. `created_source varchar(50) not null default 'telegram_bot'`.

Добавить таблицу `mini_app_sessions`:

1. `id uuid primary key`.
2. `user_id uuid not null references users(id)`.
3. `session_hash varchar(255) unique not null`.
4. `telegram_auth_date timestamptz not null`.
5. `expires_at timestamptz not null`.
6. `revoked_at timestamptz null`.
7. `last_seen_at timestamptz null`.
8. `created_at timestamptz not null`.
9. `updated_at timestamptz not null`.

Добавить таблицу `mini_app_events`:

1. `id uuid primary key`.
2. `user_id uuid null references users(id)`.
3. `event_name varchar(150) not null`.
4. `source varchar(50) not null default 'mini_app'`.
5. `payload jsonb not null default '{}'`.
6. `created_at timestamptz not null`.

`screen`, `booking_id` и другие технические детали передаются в `payload`, если они нужны для конкретного frontend event. `telegram_id`, email, телефон, session token и Telegram `initData` в analytics events не пишутся.

### 9.2. Audit source

Вариант A:

1. Не менять таблицу `audit_logs`.
2. Писать `source` в `audit_logs.payload.source`.

Плюсы:

1. Меньше миграций.
2. Уже есть `payload jsonb`.

Минусы:

1. Фильтровать по source менее удобно.

Вариант B:

1. Добавить `audit_logs.source varchar(50)`.

Плюсы:

1. Удобные индексы и фильтры.
2. Явная структура.

Минусы:

1. Дополнительная миграция и обновление маппинга.

Рекомендация для MVP:

1. Добавить `audit_logs.source varchar(50) not null default 'telegram_bot'`.
2. Для системных/worker действий использовать `system` или `worker`.
3. В `payload` оставить дополнительные детали.

## 10. Файлы по плану реализации

### 10.1. Application

1. `app/application/__init__.py`
2. `app/application/user_booking_use_cases.py`
3. `app/application/admin_booking_use_cases.py`
4. `app/application/admin_settings_use_cases.py`
5. `app/application/mini_app_auth.py`
6. `app/application/mini_app_analytics.py`
7. `app/application/sources.py`
8. `app/application/deps.py`, `app/application/ports.py` - будущий рефакторинг, если потребуется вынос общих портов из `app/integrations/telegram/ports.py`.

### 10.2. HTTP

1. `app/interfaces/http/dependencies/__init__.py`
2. `app/interfaces/http/dependencies/miniapp.py`
3. `app/interfaces/http/routes/miniapp_auth.py`
4. `app/interfaces/http/routes/miniapp_user.py`
5. `app/interfaces/http/routes/miniapp_admin.py`
6. `app/interfaces/http/routes/miniapp_analytics.py`
7. `app/interfaces/http/schemas/__init__.py`
8. `app/interfaces/http/schemas/miniapp.py`

### 10.3. Persistence

1. `app/persistence/models/mini_app.py`
2. `app/persistence/models/mini_app_event.py`
3. `app/persistence/repositories/mini_app.py`
4. `app/persistence/migrations/versions/20260714_0003_mini_app_sessions.py`
5. `app/persistence/migrations/versions/20260715_0004_mini_app_source_analytics.py`

### 10.4. Tests

1. `tests/test_miniapp_auth.py`
2. `tests/test_miniapp_user_api.py`
3. `tests/test_miniapp_admin_api.py`
4. `tests/test_miniapp_auth_route.py`
5. `tests/test_miniapp_user_use_cases.py`
6. `tests/test_miniapp_analytics.py`
7. `tests/test_miniapp_analytics_api.py`
8. `tests/test_miniapp_runtime_persistence.py` - будущий этап, если потребуется отдельное persistence-покрытие сверх текущих HTTP/use-case тестов.

## 11. Ошибки API

Рекомендуемый единый формат:

```json
{
  "error": {
    "code": "personal_data_consent_required",
    "message": "Personal data consent is required.",
    "operation_id": "..."
  }
}
```

HTTP status mapping:

1. `401` - нет Mini App session или auth failed.
2. `403` - пользователь заблокирован, нет admin access, чужая заявка.
3. `404` - заявка не найдена.
4. `409` - business rule conflict: слот недоступен, статус не подходит.
5. `422` - validation error.
6. `503` - Google Calendar недоступен или backend dependency unavailable.

## 12. План внедрения без поломки бота

1. Добавить application layer и тесты.
2. Перевести Telegram routers на shared use-cases постепенно.
3. Сохранить старые dependency dataclasses через re-export или compatibility wrapper.
4. Добавить Mini App routes после того, как use-cases покрыты тестами.
5. Проверить старые Telegram tests.
6. Только потом добавлять frontend.

## 13. Проверки этапа 1

На этапе 1 автотесты можно не запускать, потому что код приложения не меняется.

Нужно проверить:

1. Документ покрывает все MVP endpoints.
2. Документ не предлагает дублировать Telegram router-логику.
3. Admin MVP соответствует расширенному scope: заявки, расписание, ограничения, типы встреч.
4. Миграции не содержат секретов.
5. Новые env-переменные описываются без значений.

## 14. Ручная проверка пользователем

Пользователю нужно проверить:

1. Достаточен ли список пользовательских endpoints.
2. Достаточен ли список админских endpoints.
3. Подходит ли расширенный admin MVP с управлением расписанием, ограничениями и типами встреч.
4. Подходит ли рекомендация добавить `bookings.created_source`.
5. Подходит ли рекомендация добавить явное поле `audit_logs.source`.

Если эти пункты подтверждены, можно переходить к этапу 2: Auth Telegram WebApp.

## 15. Решения, которые считаются принятыми для следующего этапа

Если пользователь не попросит изменить проектирование, для этапа 2 считаются принятыми:

1. Добавляется application layer `app/application`.
2. Auth делается через проверку `initData` и backend session cookie.
3. Нужна таблица `mini_app_sessions`.
4. Нужна таблица `mini_app_events`.
5. В `bookings` добавляется `created_source`.
6. В `audit_logs` добавляется явное поле `source`.
7. Telegram bot-flow будет постепенно переведен на shared use-cases, чтобы не было двух реализаций одного сценария.
8. Админское управление расписанием, ограничениями и типами встреч проектируется и для Mini App, и для Telegram-бота.
