from datetime import datetime
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.admin_flow import AdminBookingCard, AdminFlowError
from app.core.booking import AuditEntry, BookingRecord, BookingStatus, BusinessRuleError
from app.core.datetime_formatting import format_datetime_msk
from app.integrations.google_calendar import GoogleCalendarError, GoogleCalendarNotConnectedError
from app.integrations.telegram import admin_messages as messages
from app.integrations.telegram.admin_keyboards import (
    admin_booking_actions_keyboard,
    admin_bookings_keyboard,
    admin_menu_keyboard,
    approve_keyboard,
    back_to_admin_menu_keyboard,
    block_confirm_keyboard,
    blocked_users_keyboard,
    booking_filters_keyboard,
    meeting_types_admin_keyboard,
    reject_keyboard,
    restrictions_keyboard,
)
from app.integrations.telegram.admin_states import AdminStates
from app.integrations.telegram.ports import (
    AdminFlowDependencies,
    AdminScheduleSettings,
    AdminWorkingHoursRule,
)
from app.integrations.telegram.status_labels import booking_status_label
from app.logging.config import get_logger

logger = get_logger(__name__)


def create_admin_router(deps: AdminFlowDependencies) -> Router:
    router = Router(name=__name__)

    @router.message(Command("admin"))
    async def admin_menu(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_message(message, deps):
            return
        await state.clear()
        await message.answer(messages.ADMIN_MENU, reply_markup=admin_menu_keyboard())

    @router.message(Command("diag"))
    async def diagnostics_message(message: Message) -> None:
        if not await _ensure_admin_message(message, deps):
            return
        if deps.diagnostics is None:
            await message.answer("Diagnostics are not configured.")
            return
        report = await deps.diagnostics.build_report()
        await message.answer(_diagnostics_text(report), parse_mode=None)

    @router.callback_query(F.data == "adm:menu")
    async def admin_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        await state.clear()
        await callback.answer()
        await _answer(callback, messages.ADMIN_MENU, reply_markup=admin_menu_keyboard())

    @router.callback_query(F.data == "adm:pending")
    async def pending_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        await callback.answer()
        await _show_bookings(
            callback,
            await deps.bookings.list_pending(),
            empty_text=messages.PENDING_EMPTY,
        )

    @router.callback_query(F.data == "adm:bookings")
    async def bookings_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        await callback.answer()
        await _show_bookings(
            callback,
            await deps.bookings.list_all(),
            empty_text=messages.BOOKINGS_EMPTY,
        )

    @router.callback_query(F.data.startswith("adm:booking:"))
    async def booking_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        booking_id = UUID((callback.data or "").removeprefix("adm:booking:"))
        card = await _booking_card(booking_id, deps)
        if not card:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        await callback.answer()
        await _answer(
            callback,
            _booking_card_text(card),
            reply_markup=admin_booking_actions_keyboard(card.booking),
        )

    @router.callback_query(F.data.startswith("adm:approve:"))
    async def approve_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        booking_id = UUID((callback.data or "").removeprefix("adm:approve:"))
        await callback.answer()
        await _answer(
            callback,
            _approve_text(deps.settings.default_meeting_url),
            reply_markup=approve_keyboard(booking_id),
        )

    @router.callback_query(F.data.startswith("adm:approve_default:"))
    async def approve_default_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        booking_id = UUID((callback.data or "").removeprefix("adm:approve_default:"))
        meeting_url = deps.settings.default_meeting_url
        if not meeting_url:
            await callback.answer(messages.DEFAULT_MEETING_URL_MISSING, show_alert=True)
            return
        await _confirm_booking(callback, deps, booking_id=booking_id, meeting_url=meeting_url)

    @router.callback_query(F.data.startswith("adm:approve_custom:"))
    async def approve_custom_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        booking_id = UUID((callback.data or "").removeprefix("adm:approve_custom:"))
        await state.set_state(AdminStates.custom_meeting_url)
        await state.update_data(booking_id=str(booking_id))
        await callback.answer()
        await _answer(callback, messages.CUSTOM_MEETING_URL_PROMPT)

    @router.message(AdminStates.custom_meeting_url)
    async def custom_meeting_url_message(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_message(message, deps):
            return
        data = await state.get_data()
        booking_id = UUID(data["booking_id"])
        await _confirm_booking_message(
            message,
            deps,
            booking_id=booking_id,
            meeting_url=(message.text or "").strip(),
        )
        await state.clear()

    @router.callback_query(F.data.startswith("adm:reject:"))
    async def reject_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        booking_id = UUID((callback.data or "").removeprefix("adm:reject:"))
        await callback.answer()
        await _answer(
            callback,
            messages.REJECTION_REASON_PROMPT,
            reply_markup=reject_keyboard(booking_id),
        )

    @router.callback_query(F.data.startswith("adm:reject_no_reason:"))
    async def reject_no_reason_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        booking_id = UUID((callback.data or "").removeprefix("adm:reject_no_reason:"))
        await _reject_booking(callback, deps, booking_id=booking_id, reason=None)

    @router.callback_query(F.data.startswith("adm:reject_reason:"))
    async def reject_reason_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        booking_id = UUID((callback.data or "").removeprefix("adm:reject_reason:"))
        await state.set_state(AdminStates.rejection_reason)
        await state.update_data(booking_id=str(booking_id))
        await callback.answer()
        await _answer(callback, messages.REJECTION_REASON_PROMPT)

    @router.message(AdminStates.rejection_reason)
    async def rejection_reason_message(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_message(message, deps):
            return
        data = await state.get_data()
        booking_id = UUID(data["booking_id"])
        await _reject_booking_message(
            message,
            deps,
            booking_id=booking_id,
            reason=(message.text or "").strip() or None,
        )
        await state.clear()

    @router.callback_query(F.data.startswith("adm:block:"))
    async def block_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        user_id = UUID((callback.data or "").removeprefix("adm:block:"))
        await callback.answer()
        await _answer(
            callback,
            messages.USER_BLOCK_CONFIRM,
            reply_markup=block_confirm_keyboard(user_id),
        )

    @router.callback_query(F.data.startswith("adm:block_confirm:"))
    async def block_confirm_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        user_id = UUID((callback.data or "").removeprefix("adm:block_confirm:"))
        user = await deps.users.get(user_id)
        if not user:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        result = deps.admin_flow.block_user(
            user=user,
            active_bookings=await deps.bookings.list_by_user(user.id),
            now=deps.clock(),
            admin_telegram_id=callback.from_user.id,
        )
        await deps.users.save(user)
        for booking in result.closed_bookings:
            await _cancel_calendar_event_if_needed(
                deps,
                booking,
                operation="admin_block_user",
            )
            await deps.bookings.save_booking(booking)
        await deps.bookings.save_audit_entries(result.audit_entries)
        if deps.notifier:
            await deps.notifier.user_blocked(user)
        await callback.answer()
        await _answer(callback, messages.USER_BLOCKED, reply_markup=admin_menu_keyboard())

    @router.callback_query(F.data == "adm:blocked")
    async def blocked_users_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        users = await deps.users.list_blocked()
        await callback.answer()
        if not users:
            await _answer(
                callback,
                messages.BLOCKED_EMPTY,
                reply_markup=back_to_admin_menu_keyboard(),
            )
            return
        await _answer(
            callback,
            "Заблокированные пользователи:",
            reply_markup=blocked_users_keyboard(users),
        )

    @router.callback_query(F.data.startswith("adm:unblock:"))
    async def unblock_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        user_id = UUID((callback.data or "").removeprefix("adm:unblock:"))
        user = await deps.users.get(user_id)
        if not user:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        audit = deps.admin_flow.unblock_user(
            user=user,
            now=deps.clock(),
            admin_telegram_id=callback.from_user.id,
        )
        await deps.users.save(user)
        await deps.bookings.save_audit_entries([audit])
        await callback.answer()
        await _answer(callback, messages.USER_UNBLOCKED, reply_markup=admin_menu_keyboard())

    @router.callback_query(F.data.startswith("adm:message:"))
    async def message_user_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        booking_id = UUID((callback.data or "").removeprefix("adm:message:"))
        await state.set_state(AdminStates.user_message)
        await state.update_data(booking_id=str(booking_id))
        await callback.answer()
        await _answer(callback, messages.USER_MESSAGE_PROMPT)

    @router.message(AdminStates.user_message)
    async def user_message_text(message: Message, state: FSMContext, bot: Bot) -> None:
        if not await _ensure_admin_message(message, deps):
            return
        data = await state.get_data()
        booking = await deps.bookings.get(UUID(data["booking_id"]))
        if not booking:
            await message.answer(messages.ACTION_UNAVAILABLE)
            return
        user = await deps.users.get(booking.user_id)
        if not user:
            await message.answer(messages.ACTION_UNAVAILABLE)
            return
        text = (message.text or "").strip()
        if not text:
            await message.answer(messages.ACTION_UNAVAILABLE)
            return
        try:
            await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode=None)
        except Exception as error:
            logger.error(
                "Telegram message delivery failed",
                extra={
                    "event": "telegram_api_error",
                    "operation": "admin_send_user_message",
                    "error_type": type(error).__name__,
                },
            )
            raise
        audit = deps.admin_flow.message_sent_audit(
            user_id=user.id,
            now=deps.clock(),
            admin_telegram_id=message.from_user.id,
        )
        await deps.bookings.save_audit_entries([audit])
        await state.clear()
        await message.answer(messages.USER_MESSAGE_SENT, reply_markup=admin_menu_keyboard())

    @router.callback_query(F.data == "adm:schedule")
    async def schedule_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        await callback.answer()
        if deps.admin_settings is None:
            await _answer(
                callback,
                messages.ACTION_UNAVAILABLE,
                reply_markup=back_to_admin_menu_keyboard(),
            )
            return
        settings = await deps.admin_settings.get_schedule_settings()
        working_hours = await deps.admin_settings.list_working_hours()
        await _answer(
            callback,
            _schedule_text(settings, working_hours),
            reply_markup=back_to_admin_menu_keyboard(),
        )

    @router.callback_query(F.data == "adm:restrictions")
    async def restrictions_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        await callback.answer()
        await _show_restrictions(callback, deps)

    @router.callback_query(F.data == "adm:restriction_add")
    async def restriction_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        await state.set_state(AdminStates.closed_day_date)
        await callback.answer()
        await _answer(
            callback,
            "Введите дату закрытого дня в формате ДД.ММ.ГГГГ.",
            reply_markup=back_to_admin_menu_keyboard(),
        )

    @router.message(AdminStates.closed_day_date)
    async def closed_day_date_message(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_message(message, deps):
            return
        if deps.admin_settings is None:
            await message.answer(messages.ACTION_UNAVAILABLE)
            await state.clear()
            return
        try:
            restriction_date = datetime.strptime((message.text or "").strip(), "%d.%m.%Y").date()
        except ValueError:
            await message.answer("Дата должна быть в формате ДД.ММ.ГГГГ.")
            return
        await deps.admin_settings.add_closed_day_restriction(
            restriction_date=restriction_date,
            admin_comment=f"created_by_admin:{message.from_user.id}",
        )
        await state.clear()
        await message.answer(
            f"Закрытый день добавлен: {restriction_date:%d.%m.%Y}.",
            reply_markup=admin_menu_keyboard(),
        )

    @router.callback_query(F.data.startswith("adm:restriction_delete:"))
    async def restriction_delete_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        if deps.admin_settings is None:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        restriction_id = UUID((callback.data or "").removeprefix("adm:restriction_delete:"))
        deleted = await deps.admin_settings.delete_restriction(restriction_id)
        await callback.answer("Удалено" if deleted else messages.ACTION_UNAVAILABLE)
        await _show_restrictions(callback, deps)

    @router.callback_query(F.data == "adm:meeting_types")
    async def meeting_types_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        await callback.answer()
        await _show_meeting_types(callback, deps)

    @router.callback_query(F.data == "adm:meeting_type_add")
    async def meeting_type_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        if deps.admin_settings is None:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        await state.set_state(AdminStates.meeting_type_name)
        await callback.answer()
        await _answer(callback, "Введите название нового типа встречи.")

    @router.message(AdminStates.meeting_type_name)
    async def meeting_type_name_message(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_message(message, deps):
            return
        name = (message.text or "").strip()
        if not name or len(name) > 255:
            await message.answer("Название должно быть от 1 до 255 символов.")
            return
        await state.update_data(meeting_type_name=name)
        await state.set_state(AdminStates.meeting_type_durations)
        await message.answer("Введите длительности через запятую: 30, 60 или 90.")

    @router.message(AdminStates.meeting_type_durations)
    async def meeting_type_durations_message(message: Message, state: FSMContext) -> None:
        if not await _ensure_admin_message(message, deps):
            return
        if deps.admin_settings is None:
            await message.answer(messages.ACTION_UNAVAILABLE)
            await state.clear()
            return
        durations = _parse_meeting_type_durations(message.text or "")
        if durations is None:
            await message.answer("Длительности должны быть числами 30, 60 или 90 через запятую.")
            return
        data = await state.get_data()
        added = await deps.admin_settings.add_meeting_type(
            name=data["meeting_type_name"],
            allowed_durations_minutes=durations,
            is_fixed_duration=len(durations) == 1,
        )
        await state.clear()
        if added is None:
            await message.answer(
                "Тип встречи с таким названием уже есть.",
                reply_markup=admin_menu_keyboard(),
            )
            return
        await message.answer(
            f"Тип встречи добавлен: {added.name}.",
            reply_markup=admin_menu_keyboard(),
        )

    @router.callback_query(F.data.startswith("adm:meeting_type_toggle:"))
    async def meeting_type_toggle_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        if deps.admin_settings is None:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        raw_id, raw_active = (callback.data or "").removeprefix(
            "adm:meeting_type_toggle:"
        ).rsplit(":", 1)
        updated = await deps.admin_settings.set_meeting_type_active(
            UUID(raw_id),
            is_active=raw_active == "1",
        )
        await callback.answer("Обновлено" if updated else messages.ACTION_UNAVAILABLE)
        await _show_meeting_types(callback, deps)

    @router.callback_query(F.data == "adm:filters")
    async def filters_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        await callback.answer()
        await _answer(callback, "Выберите статус заявок.", reply_markup=booking_filters_keyboard())

    @router.callback_query(F.data.startswith("adm:filter:"))
    async def filter_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        raw_status = (callback.data or "").removeprefix("adm:filter:")
        try:
            status = BookingStatus(raw_status)
        except ValueError:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        bookings = [
            booking for booking in await deps.bookings.list_all() if booking.status == status
        ]
        await callback.answer()
        await _show_bookings(
            callback,
            bookings,
            empty_text=f"Заявок со статусом «{booking_status_label(status)}» нет.",
        )

    return router


async def _show_restrictions(callback: CallbackQuery, deps: AdminFlowDependencies) -> None:
    if deps.admin_settings is None:
        await _answer(
            callback,
            messages.ACTION_UNAVAILABLE,
            reply_markup=back_to_admin_menu_keyboard(),
        )
        return
    restrictions = await deps.admin_settings.list_upcoming_restrictions(
        from_date=deps.clock().date()
    )
    lines = ["Ограничения расписания:"]
    if restrictions:
        for restriction in restrictions:
            if restriction.restriction_type == "closed_day":
                title = f"{restriction.restriction_date:%d.%m.%Y}: закрытый день"
            else:
                title = (
                    f"{restriction.restriction_date:%d.%m.%Y}: "
                    f"{restriction.start_time or '-'}-{restriction.end_time or '-'}"
                )
            if restriction.admin_comment:
                title = f"{title} ({restriction.admin_comment})"
            lines.append(title)
    else:
        lines.append("Будущих ограничений нет.")
    await _answer(
        callback,
        "\n".join(lines),
        reply_markup=restrictions_keyboard(restrictions),
    )


async def _show_meeting_types(callback: CallbackQuery, deps: AdminFlowDependencies) -> None:
    if deps.admin_settings is None:
        await _answer(
            callback,
            messages.ACTION_UNAVAILABLE,
            reply_markup=back_to_admin_menu_keyboard(),
        )
        return
    meeting_types = await deps.admin_settings.list_meeting_types_admin()
    lines = ["Типы встреч:"]
    for meeting_type in meeting_types:
        status = "активен" if meeting_type.is_active else "отключен"
        fixed = ", фиксированная длительность" if meeting_type.is_fixed_duration else ""
        durations = "/".join(str(item) for item in meeting_type.allowed_durations_minutes)
        lines.append(f"{meeting_type.name}: {status}, {durations} мин{fixed}")
    await _answer(
        callback,
        "\n".join(lines),
        reply_markup=meeting_types_admin_keyboard(meeting_types),
    )


async def _show_bookings(
    callback: CallbackQuery,
    bookings: list[BookingRecord],
    *,
    empty_text: str,
) -> None:
    if not bookings:
        await _answer(callback, empty_text, reply_markup=back_to_admin_menu_keyboard())
        return
    await _answer(callback, "Заявки:", reply_markup=admin_bookings_keyboard(bookings))


def _schedule_text(
    settings: AdminScheduleSettings,
    working_hours: list[AdminWorkingHoursRule],
) -> str:
    lines = [
        "Расписание:",
        f"Часовой пояс: {settings.timezone}",
        f"Минимальный срок записи: {settings.min_booking_lead_days} дн.",
        f"Горизонт записи: {settings.booking_horizon_days} дн.",
        f"Шаг слотов: {settings.slot_step_minutes} мин.",
        f"Буфер вокруг встреч: {settings.meeting_buffer_minutes} мин.",
        "",
        "Рабочие часы:",
    ]
    names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    for rule in working_hours:
        if rule.is_working_day and rule.start_time and rule.end_time:
            lines.append(f"{names[rule.weekday]}: {rule.start_time:%H:%M}-{rule.end_time:%H:%M}")
        else:
            lines.append(f"{names[rule.weekday]}: выходной")
    return "\n".join(lines)


def _parse_meeting_type_durations(raw_value: str) -> tuple[int, ...] | None:
    try:
        durations = tuple(
            sorted({int(item.strip()) for item in raw_value.split(",") if item.strip()})
        )
    except ValueError:
        return None
    if not durations or any(item not in {30, 60, 90} for item in durations):
        return None
    return durations


async def _confirm_booking(
    callback: CallbackQuery,
    deps: AdminFlowDependencies,
    *,
    booking_id: UUID,
    meeting_url: str,
) -> None:
    card = await _booking_card(booking_id, deps)
    if not card:
        await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
        return
    try:
        confirmation = await deps.calendar.confirm_booking(
            booking=card.booking,
            user=card.user,
            meeting_type=card.meeting_type,
            meeting_url=meeting_url,
        )
        audit = deps.admin_flow.confirm_booking(
            booking=card.booking,
            confirmation=confirmation,
            now=deps.clock(),
            admin_telegram_id=callback.from_user.id,
        )
    except BusinessRuleError as error:
        await callback.answer(error.rule, show_alert=True)
        return
    except GoogleCalendarNotConnectedError as error:
        _log_google_calendar_error(error, operation="admin_confirm_booking")
        await callback.answer(messages.GOOGLE_CALENDAR_NOT_CONNECTED, show_alert=True)
        return
    except GoogleCalendarError as error:
        _log_google_calendar_error(error, operation="admin_confirm_booking")
        await callback.answer(messages.GOOGLE_CALENDAR_ERROR, show_alert=True)
        return
    await deps.bookings.save_booking(card.booking)
    audit_entries = [audit]
    reschedule_audit = await _complete_previous_reschedule_if_needed(card.booking, deps)
    if reschedule_audit:
        audit_entries.append(reschedule_audit)
    await deps.bookings.save_audit_entries(audit_entries)
    if deps.background_jobs:
        await deps.background_jobs.schedule_booking_confirmed(card.booking, now=deps.clock())
    if deps.notifier:
        await deps.notifier.booking_confirmed(card.booking)
    await callback.answer()
    await _answer(callback, messages.BOOKING_CONFIRMED, reply_markup=admin_menu_keyboard())


async def _confirm_booking_message(
    message: Message,
    deps: AdminFlowDependencies,
    *,
    booking_id: UUID,
    meeting_url: str,
) -> None:
    card = await _booking_card(booking_id, deps)
    if not card:
        await message.answer(messages.ACTION_UNAVAILABLE)
        return
    if not meeting_url:
        await message.answer(messages.ACTION_UNAVAILABLE)
        return
    try:
        confirmation = await deps.calendar.confirm_booking(
            booking=card.booking,
            user=card.user,
            meeting_type=card.meeting_type,
            meeting_url=meeting_url,
        )
        audit = deps.admin_flow.confirm_booking(
            booking=card.booking,
            confirmation=confirmation,
            now=deps.clock(),
            admin_telegram_id=message.from_user.id,
        )
    except BusinessRuleError as error:
        await message.answer(error.rule)
        return
    except GoogleCalendarNotConnectedError as error:
        _log_google_calendar_error(error, operation="admin_confirm_booking_message")
        await message.answer(messages.GOOGLE_CALENDAR_NOT_CONNECTED)
        return
    except GoogleCalendarError as error:
        _log_google_calendar_error(error, operation="admin_confirm_booking_message")
        await message.answer(messages.GOOGLE_CALENDAR_ERROR)
        return
    await deps.bookings.save_booking(card.booking)
    audit_entries = [audit]
    reschedule_audit = await _complete_previous_reschedule_if_needed(card.booking, deps)
    if reschedule_audit:
        audit_entries.append(reschedule_audit)
    await deps.bookings.save_audit_entries(audit_entries)
    if deps.background_jobs:
        await deps.background_jobs.schedule_booking_confirmed(card.booking, now=deps.clock())
    if deps.notifier:
        await deps.notifier.booking_confirmed(card.booking)
    await message.answer(messages.BOOKING_CONFIRMED, reply_markup=admin_menu_keyboard())


async def _reject_booking(
    callback: CallbackQuery,
    deps: AdminFlowDependencies,
    *,
    booking_id: UUID,
    reason: str | None,
) -> None:
    card = await _booking_card(booking_id, deps)
    if not card:
        await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
        return
    try:
        audit = deps.admin_flow.reject_booking(
            booking=card.booking,
            now=deps.clock(),
            admin_telegram_id=callback.from_user.id,
            reason=reason,
        )
    except BusinessRuleError as error:
        await callback.answer(error.rule, show_alert=True)
        return
    await deps.bookings.save_booking(card.booking)
    await deps.bookings.save_audit_entries([audit])
    if deps.notifier:
        await deps.notifier.booking_rejected(card.booking, reason)
    await callback.answer()
    await _answer(callback, messages.BOOKING_REJECTED, reply_markup=admin_menu_keyboard())


async def _reject_booking_message(
    message: Message,
    deps: AdminFlowDependencies,
    *,
    booking_id: UUID,
    reason: str | None,
) -> None:
    card = await _booking_card(booking_id, deps)
    if not card:
        await message.answer(messages.ACTION_UNAVAILABLE)
        return
    try:
        audit = deps.admin_flow.reject_booking(
            booking=card.booking,
            now=deps.clock(),
            admin_telegram_id=message.from_user.id,
            reason=reason,
        )
    except BusinessRuleError as error:
        await message.answer(error.rule)
        return
    await deps.bookings.save_booking(card.booking)
    await deps.bookings.save_audit_entries([audit])
    if deps.notifier:
        await deps.notifier.booking_rejected(card.booking, reason)
    await message.answer(messages.BOOKING_REJECTED, reply_markup=admin_menu_keyboard())


async def _booking_card(
    booking_id: UUID,
    deps: AdminFlowDependencies,
) -> AdminBookingCard | None:
    booking = await deps.bookings.get(booking_id)
    if not booking:
        return None
    user = await deps.users.get(booking.user_id)
    meeting_type = await deps.meeting_types.get(booking.meeting_type_id)
    if not user or not meeting_type:
        return None
    return deps.admin_flow.build_booking_card(
        booking=booking,
        user=user,
        meeting_type=meeting_type,
    )


async def _complete_previous_reschedule_if_needed(
    booking: BookingRecord,
    deps: AdminFlowDependencies,
) -> AuditEntry | None:
    if not booking.is_reschedule_request or not booking.previous_booking_id:
        return None
    previous = await deps.bookings.get(booking.previous_booking_id)
    if not previous:
        return None

    await _cancel_calendar_event_if_needed(
        deps,
        previous,
        operation="admin_confirm_reschedule",
    )
    audit = deps.admin_flow.complete_reschedule(
        previous_booking=previous,
        new_booking=booking,
        now=deps.clock(),
    )
    await deps.bookings.save_booking(previous)
    return audit


async def _cancel_calendar_event_if_needed(
    deps: AdminFlowDependencies,
    booking: BookingRecord,
    *,
    operation: str,
) -> None:
    if not deps.calendar_events or not booking.google_calendar_event_id:
        return
    try:
        await deps.calendar_events.cancel_event(booking.google_calendar_event_id)
    except GoogleCalendarError as error:
        logger.warning(
            "Google Calendar event cancellation failed",
            extra={
                "event": "google_api_error",
                "operation": operation,
                "booking_id": str(booking.id),
                "error_code": error.code,
                "error_type": type(error).__name__,
            },
        )


async def _ensure_admin_message(message: Message, deps: AdminFlowDependencies) -> bool:
    if not message.from_user:
        return False
    try:
        deps.admin_flow.ensure_admin(
            telegram_id=message.from_user.id,
            configured_admin_id=deps.settings.telegram_admin_id,
        )
    except AdminFlowError as error:
        await message.answer(_admin_access_error_text(error))
        return False
    return True


async def _ensure_admin_callback(callback: CallbackQuery, deps: AdminFlowDependencies) -> bool:
    try:
        deps.admin_flow.ensure_admin(
            telegram_id=callback.from_user.id,
            configured_admin_id=deps.settings.telegram_admin_id,
        )
    except AdminFlowError as error:
        await callback.answer(_admin_access_error_text(error), show_alert=True)
        return False
    return True


def _booking_card_text(card: AdminBookingCard) -> str:
    booking = card.booking
    user = card.user
    username = f"@{user.telegram_username}" if user.telegram_username else "username не указан"
    comment = booking.user_comment or "-"
    reserved_until = format_datetime_msk(booking.reserved_until) if booking.reserved_until else "-"
    return "\n".join(
        [
            "Заявка на встречу",
            f"Имя: {user.full_name or '-'}",
            f"Telegram: {username}",
            f"Email: {user.email or '-'}",
            f"Тип: {card.meeting_type.name}",
            f"Длительность: {booking.duration_minutes} минут",
            f"Дата и время: {format_datetime_msk(booking.starts_at)}",
            f"Комментарий: {comment}",
            f"Статус: {booking_status_label(booking.status)}",
            f"Резерв до: {reserved_until}",
        ]
    )


def _approve_text(default_meeting_url: str | None) -> str:
    if not default_meeting_url:
        return messages.DEFAULT_MEETING_URL_MISSING
    return f"Ссылка по умолчанию:\n{default_meeting_url}"


def _admin_access_error_text(error: AdminFlowError) -> str:
    if error.code == "admin_not_configured":
        return messages.ADMIN_NOT_CONFIGURED
    return messages.ADMIN_ACCESS_DENIED


def _diagnostics_text(report) -> str:
    lines = [f"Diagnostics: {report.status}"]
    for check in report.checks:
        lines.append(f"{check.name}: {check.status} - {check.message}")
        for key, value in check.details.items():
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def _log_google_calendar_error(error: GoogleCalendarError, *, operation: str) -> None:
    logger.error(
        "Google Calendar admin flow failed",
        extra={
            "event": "google_api_error",
            "operation": operation,
            "error_code": error.code,
            "error_type": type(error).__name__,
        },
    )


async def _answer(callback: CallbackQuery, text: str, **kwargs) -> None:
    if callback.message:
        await callback.message.answer(text, **kwargs)
