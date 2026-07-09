from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.admin_flow import AdminBookingCard, AdminFlowError
from app.core.booking import BookingRecord, BusinessRuleError
from app.integrations.telegram import admin_messages as messages
from app.integrations.telegram.admin_keyboards import (
    admin_booking_actions_keyboard,
    admin_bookings_keyboard,
    admin_menu_keyboard,
    approve_keyboard,
    back_to_admin_menu_keyboard,
    block_confirm_keyboard,
    blocked_users_keyboard,
    reject_keyboard,
)
from app.integrations.telegram.admin_states import AdminStates
from app.integrations.telegram.ports import AdminFlowDependencies
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
        await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode=None)
        audit = deps.admin_flow.message_sent_audit(
            user_id=user.id,
            now=deps.clock(),
            admin_telegram_id=message.from_user.id,
        )
        await deps.bookings.save_audit_entries([audit])
        await state.clear()
        await message.answer(messages.USER_MESSAGE_SENT, reply_markup=admin_menu_keyboard())

    @router.callback_query(
        F.data.in_({"adm:schedule", "adm:restrictions", "adm:meeting_types", "adm:filters"})
    )
    async def settings_placeholder_callback(callback: CallbackQuery) -> None:
        if not await _ensure_admin_callback(callback, deps):
            return
        logger.info(
            "Admin opened settings section",
            extra={
                "event": "admin_action",
                "action": callback.data,
                "admin_id": callback.from_user.id,
            },
        )
        await callback.answer()
        await _answer(
            callback,
            messages.SETTINGS_PLACEHOLDER,
            reply_markup=back_to_admin_menu_keyboard(),
        )

    return router


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
    await deps.bookings.save_booking(card.booking)
    await deps.bookings.save_audit_entries([audit])
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
    await deps.bookings.save_booking(card.booking)
    await deps.bookings.save_audit_entries([audit])
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
    reserved_until = (
        booking.reserved_until.strftime("%d.%m.%Y %H:%M") if booking.reserved_until else "-"
    )
    return "\n".join(
        [
            "Заявка на встречу",
            f"Имя: {user.full_name or '-'}",
            f"Telegram: {username}",
            f"Email: {user.email or '-'}",
            f"Тип: {card.meeting_type.name}",
            f"Длительность: {booking.duration_minutes} минут",
            f"Дата: {booking.starts_at:%d.%m.%Y}",
            f"Время: {booking.starts_at:%H:%M}",
            f"Комментарий: {comment}",
            f"Статус: {booking.status.value}",
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


async def _answer(callback: CallbackQuery, text: str, **kwargs) -> None:
    if callback.message:
        await callback.message.answer(text, **kwargs)
