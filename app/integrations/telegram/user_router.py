from datetime import date, datetime
from uuid import UUID

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.core.booking import BookingRecord, BusinessRuleError, MeetingType, UserProfile
from app.core.datetime_formatting import format_datetime_msk
from app.core.user_flow import BookingDraft, UserFlowError
from app.integrations.google_calendar import GoogleCalendarError
from app.integrations.telegram import messages
from app.integrations.telegram.keyboards import (
    BACK,
    CANCEL,
    MENU,
    booking_actions_keyboard,
    bookings_keyboard,
    comment_keyboard,
    confirm_cancel_keyboard,
    consent_keyboard,
    dates_keyboard,
    durations_keyboard,
    email_found_keyboard,
    main_menu_keyboard,
    meeting_types_keyboard,
    menu_reply_keyboard,
    review_keyboard,
    slots_keyboard,
    text_navigation_keyboard,
)
from app.integrations.telegram.ports import UserFlowDependencies
from app.integrations.telegram.states import UserBookingStates
from app.integrations.telegram.status_labels import booking_status_label
from app.logging.config import get_logger

logger = get_logger(__name__)


def create_user_router(deps: UserFlowDependencies) -> Router:
    router = Router(name=__name__)

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        user = await _ensure_user(message, deps)
        logger.info(
            "User flow started",
            extra={"event": "user_flow_started", "flow": "start", "user_id": str(user.id)},
        )
        if not user.has_personal_data_consent:
            await _show_consent(message, state, deps)
            return
        await _show_menu(message, state)

    @router.callback_query(F.data == "uf:menu")
    async def menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer()
        await _edit_or_answer(callback, messages.MAIN_MENU, reply_markup=main_menu_keyboard())

    @router.message(F.text == MENU)
    async def menu_message(message: Message, state: FSMContext) -> None:
        await _show_menu(message, state)

    @router.callback_query(F.data.startswith("uf:consent:"))
    async def consent_callback(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        personal = bool(data.get("personal_data_checked"))
        policy = bool(data.get("policy_checked"))
        action = (callback.data or "").removeprefix("uf:consent:")

        if action == "personal":
            personal = not personal
        elif action == "policy":
            policy = not policy
        elif action == "accept":
            user = await _ensure_user_from_callback(callback, deps)
            try:
                audit = deps.flow.accept_consent(
                    user=user,
                    personal_data_checked=personal,
                    policy_checked=policy,
                    consent_url=deps.settings.personal_data_consent_url,
                    policy_url=deps.settings.personal_data_policy_url,
                    now=deps.clock(),
                )
            except UserFlowError as error:
                text = (
                    messages.CONSENT_LINKS_MISSING
                    if error.code == "consent_urls_required"
                    else messages.CONSENT_REQUIRED
                )
                await callback.answer(text, show_alert=True)
                return
            await deps.users.save(user)
            await deps.bookings.save_audit_entries([audit])
            await state.clear()
            await callback.answer()
            await _edit_or_answer(callback, messages.MAIN_MENU, reply_markup=main_menu_keyboard())
            return

        await state.update_data(personal_data_checked=personal, policy_checked=policy)
        await callback.answer()
        await _edit_or_answer(
            callback,
            messages.CONSENT,
            reply_markup=consent_keyboard(
                personal_data_checked=personal,
                policy_checked=policy,
                consent_url=deps.settings.personal_data_consent_url,
                policy_url=deps.settings.personal_data_policy_url,
            ),
        )

    @router.callback_query(F.data == "uf:book")
    async def book_callback(callback: CallbackQuery, state: FSMContext) -> None:
        user = await _ensure_user_from_callback(callback, deps)
        await callback.answer()
        await _begin_booking(callback, state, deps, user=user)

    @router.message(UserBookingStates.name)
    async def name_message(message: Message, state: FSMContext) -> None:
        if await _handle_text_navigation(message, state, deps):
            return
        draft = _draft_from_data(await state.get_data())
        draft.full_name = (message.text or "").strip()
        await _save_draft(state, draft)
        user = await _ensure_user(message, deps)
        if user.email:
            await state.set_state(UserBookingStates.email)
            await message.answer(
                messages.EMAIL_FOUND.format(email=user.email),
                reply_markup=email_found_keyboard(),
            )
            return
        await state.set_state(UserBookingStates.email)
        await message.answer(messages.EMAIL, reply_markup=text_navigation_keyboard())

    @router.callback_query(F.data.startswith("uf:email:"))
    async def email_choice_callback(callback: CallbackQuery, state: FSMContext) -> None:
        user = await _ensure_user_from_callback(callback, deps)
        draft = _draft_from_data(await state.get_data())
        action = (callback.data or "").removeprefix("uf:email:")
        await callback.answer()
        if action == "keep" and user.email:
            draft.email = user.email
            await _save_draft(state, draft)
            await _show_meeting_types(callback, state, deps)
            return
        await state.set_state(UserBookingStates.email)
        await _edit_or_answer(callback, messages.EMAIL)

    @router.message(UserBookingStates.email)
    async def email_message(message: Message, state: FSMContext) -> None:
        if await _handle_text_navigation(message, state, deps):
            return
        try:
            email = deps.flow.validate_email(message.text or "")
        except UserFlowError:
            await message.answer(messages.INVALID_EMAIL, reply_markup=text_navigation_keyboard())
            return
        draft = _draft_from_data(await state.get_data())
        draft.email = email
        await _save_draft(state, draft)
        await _show_meeting_types(message, state, deps)

    @router.callback_query(F.data.startswith("uf:type:"))
    async def meeting_type_callback(callback: CallbackQuery, state: FSMContext) -> None:
        meeting_type_id = UUID((callback.data or "").removeprefix("uf:type:"))
        meeting_type = await deps.meeting_types.get(meeting_type_id)
        if not meeting_type:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        draft = _draft_from_data(await state.get_data())
        draft.meeting_type_id = meeting_type.id
        if meeting_type.is_fixed_duration:
            draft.duration_minutes = meeting_type.allowed_durations_minutes[0]
            await _save_draft(state, draft)
            await _show_dates(callback, state, deps)
            return
        await _save_draft(state, draft)
        await state.set_state(UserBookingStates.duration)
        await callback.answer()
        await _edit_or_answer(
            callback,
            "Выберите длительность встречи.",
            reply_markup=durations_keyboard(meeting_type),
        )

    @router.callback_query(F.data.startswith("uf:duration:"))
    async def duration_callback(callback: CallbackQuery, state: FSMContext) -> None:
        draft = _draft_from_data(await state.get_data())
        draft.duration_minutes = int((callback.data or "").removeprefix("uf:duration:"))
        await _save_draft(state, draft)
        await callback.answer()
        await _show_dates(callback, state, deps)

    @router.callback_query(F.data.startswith("uf:date_page:"))
    async def date_page_callback(callback: CallbackQuery, state: FSMContext) -> None:
        page = int((callback.data or "").removeprefix("uf:date_page:"))
        await callback.answer()
        await _show_dates(callback, state, deps, page=page)

    @router.callback_query(F.data.startswith("uf:date:"))
    async def date_callback(callback: CallbackQuery, state: FSMContext) -> None:
        selected = date.fromisoformat((callback.data or "").removeprefix("uf:date:"))
        draft = _draft_from_data(await state.get_data())
        meeting_type = await _meeting_type_for_draft(draft, deps)
        if not meeting_type or draft.duration_minutes is None:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        await callback.answer()
        schedule = await deps.schedule.context_for_date(selected)
        slots = deps.flow.public_slots(
            target_date=selected,
            meeting_type=meeting_type,
            duration_minutes=draft.duration_minutes,
            now=deps.clock(),
            schedule=schedule,
        )
        draft.selected_date = selected
        await _save_draft(state, draft)
        await state.update_data(
            slots=[(slot.starts_at.isoformat(), slot.ends_at.isoformat()) for slot in slots]
        )
        await state.set_state(UserBookingStates.time)
        if not slots:
            await _edit_or_answer(
                callback,
                messages.NO_SLOTS,
                reply_markup=dates_keyboard(
                    deps.flow.available_dates(now=deps.clock(), settings=schedule.settings)
                ),
            )
            return
        await _edit_or_answer(callback, messages.TIME, reply_markup=slots_keyboard(slots))

    @router.callback_query(F.data.startswith("uf:slot:"))
    async def slot_callback(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        index = int((callback.data or "").removeprefix("uf:slot:"))
        slots = data.get("slots") or []
        if index >= len(slots):
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        starts_at, ends_at = slots[index]
        draft = _draft_from_data(data)
        draft.starts_at = datetime.fromisoformat(starts_at)
        draft.ends_at = datetime.fromisoformat(ends_at)
        await _save_draft(state, draft)
        await state.set_state(UserBookingStates.comment)
        await callback.answer()
        await _edit_or_answer(callback, messages.COMMENT, reply_markup=comment_keyboard())

    @router.callback_query(F.data == "uf:comment:skip")
    async def skip_comment_callback(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await _show_review(callback, state, deps)

    @router.message(UserBookingStates.comment)
    async def comment_message(message: Message, state: FSMContext) -> None:
        if await _handle_text_navigation(message, state, deps):
            return
        draft = _draft_from_data(await state.get_data())
        draft.user_comment = (message.text or "").strip() or None
        await _save_draft(state, draft)
        await _show_review(message, state, deps)

    @router.callback_query(F.data == "uf:submit")
    async def submit_callback(callback: CallbackQuery, state: FSMContext) -> None:
        user = await _ensure_user_from_callback(callback, deps)
        draft = _draft_from_data(await state.get_data())
        meeting_type = await _meeting_type_for_draft(draft, deps)
        previous_booking = await _previous_booking_for_draft(draft, deps, user)
        if not meeting_type:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        try:
            result = deps.flow.create_booking_from_draft(
                user=user,
                draft=draft,
                meeting_type=meeting_type,
                now=deps.clock(),
                existing_bookings=await deps.bookings.list_by_user(user.id),
                previous_booking=previous_booking,
            )
        except (BusinessRuleError, UserFlowError) as error:
            await callback.answer(_business_error_text(error), show_alert=True)
            return
        await deps.users.save(user)
        await deps.bookings.save_booking_result(result)
        if deps.background_jobs:
            await deps.background_jobs.schedule_booking_created(
                result.booking,
                now=result.booking.created_at or deps.clock(),
            )
        if deps.notifier:
            if result.booking.is_reschedule_request:
                await deps.notifier.reschedule_requested(result.booking)
            else:
                await deps.notifier.booking_created(result.booking)
        await state.clear()
        await callback.answer()
        await _edit_or_answer(callback, messages.BOOKING_SENT, reply_markup=menu_reply_keyboard())

    @router.callback_query(F.data == "uf:my")
    async def my_bookings_callback(callback: CallbackQuery, state: FSMContext) -> None:
        user = await _ensure_user_from_callback(callback, deps)
        bookings = await deps.bookings.list_by_user(user.id)
        await state.set_state(UserBookingStates.my_bookings)
        await callback.answer()
        if not bookings:
            await _edit_or_answer(
                callback,
                messages.BOOKINGS_EMPTY,
                reply_markup=main_menu_keyboard(),
            )
            return
        await _edit_or_answer(
            callback,
            _bookings_text(bookings),
            reply_markup=bookings_keyboard(bookings),
        )

    @router.callback_query(F.data.startswith("uf:booking:"))
    async def booking_callback(callback: CallbackQuery) -> None:
        user = await _ensure_user_from_callback(callback, deps)
        booking_id = UUID((callback.data or "").removeprefix("uf:booking:"))
        booking = await deps.bookings.get_for_user(booking_id, user.id)
        if not booking:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        await callback.answer()
        await _edit_or_answer(
            callback,
            _booking_text(booking),
            reply_markup=booking_actions_keyboard(booking),
        )

    @router.callback_query(F.data.startswith("uf:cancel_booking:"))
    async def cancel_booking_callback(callback: CallbackQuery, state: FSMContext) -> None:
        user = await _ensure_user_from_callback(callback, deps)
        booking_id = UUID((callback.data or "").removeprefix("uf:cancel_booking:"))
        booking = await deps.bookings.get_for_user(booking_id, user.id)
        if not booking:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        await state.set_state(UserBookingStates.cancel_confirmation)
        await callback.answer()
        await _edit_or_answer(
            callback,
            messages.CONFIRM_CANCEL,
            reply_markup=confirm_cancel_keyboard(booking.id),
        )

    @router.callback_query(F.data.startswith("uf:cancel_confirm:"))
    async def cancel_confirm_callback(callback: CallbackQuery, state: FSMContext) -> None:
        user = await _ensure_user_from_callback(callback, deps)
        booking_id = UUID((callback.data or "").removeprefix("uf:cancel_confirm:"))
        booking = await deps.bookings.get_for_user(booking_id, user.id)
        if not booking:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        try:
            audit = deps.booking_service.cancel_booking_by_user(booking, now=deps.clock())
        except BusinessRuleError as error:
            await callback.answer(_business_error_text(error), show_alert=True)
            return
        await deps.bookings.save_booking(booking)
        await deps.bookings.save_audit_entries([audit])
        if deps.calendar_events and booking.google_calendar_event_id:
            try:
                await deps.calendar_events.cancel_event(booking.google_calendar_event_id)
            except GoogleCalendarError as error:
                logger.warning(
                    "Google Calendar event cancellation failed",
                    extra={
                        "event": "google_api_error",
                        "operation": "cancel_event",
                        "booking_id": str(booking.id),
                        "error_code": error.code,
                        "error_type": type(error).__name__,
                    },
                )
        if deps.notifier:
            await deps.notifier.booking_cancelled_by_user(booking)
        await state.clear()
        await callback.answer()
        await _edit_or_answer(callback, messages.USER_CANCELLED, reply_markup=menu_reply_keyboard())

    @router.callback_query(F.data.startswith("uf:reschedule:"))
    async def reschedule_callback(callback: CallbackQuery, state: FSMContext) -> None:
        user = await _ensure_user_from_callback(callback, deps)
        booking_id = UUID((callback.data or "").removeprefix("uf:reschedule:"))
        booking = await deps.bookings.get_for_user(booking_id, user.id)
        if not booking:
            await callback.answer(messages.ACTION_UNAVAILABLE, show_alert=True)
            return
        draft = BookingDraft(
            full_name=user.full_name,
            email=user.email,
            previous_booking_id=booking.id,
        )
        await _save_draft(state, draft)
        await callback.answer()
        await _edit_or_answer(callback, messages.RESCHEDULE)
        await _show_meeting_types(callback, state, deps)

    @router.callback_query(F.data == "uf:cancel")
    async def cancel_flow_callback(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        logger.info("User flow cancelled", extra={"event": "user_flow_cancelled"})
        await callback.answer()
        await _edit_or_answer(
            callback,
            messages.CANCELLED_FLOW,
            reply_markup=menu_reply_keyboard(),
        )

    @router.callback_query(F.data == "uf:back")
    async def back_callback(callback: CallbackQuery, state: FSMContext) -> None:
        logger.info("User flow back pressed", extra={"event": "user_flow_back"})
        await callback.answer()
        await _go_back(callback, state, deps)

    return router


async def _show_consent(message: Message, state: FSMContext, deps: UserFlowDependencies) -> None:
    await state.set_state(UserBookingStates.consent)
    await state.update_data(personal_data_checked=False, policy_checked=False)
    await message.answer(
        f"{messages.START}\n\n{messages.CONSENT}",
        reply_markup=consent_keyboard(
            personal_data_checked=False,
            policy_checked=False,
            consent_url=deps.settings.personal_data_consent_url,
            policy_url=deps.settings.personal_data_policy_url,
        ),
    )


async def _show_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(messages.MAIN_MENU, reply_markup=main_menu_keyboard())


async def _begin_booking(
    target: Message | CallbackQuery,
    state: FSMContext,
    deps: UserFlowDependencies,
    *,
    user: UserProfile,
) -> None:
    try:
        deps.flow.ensure_can_start_booking(
            user=user,
            existing_bookings=await deps.bookings.list_by_user(user.id),
        )
    except BusinessRuleError as error:
        logger.warning(
            "User cannot start booking flow",
            extra={"event": "user_flow_start_denied", "rule": error.rule},
        )
        await _send(target, _business_error_text(error), reply_markup=main_menu_keyboard())
        return

    draft = BookingDraft(full_name=user.full_name, email=user.email)
    await _save_draft(state, draft)
    logger.info(
        "User flow started",
        extra={"event": "user_flow_started", "flow": "create_booking", "user_id": str(user.id)},
    )
    if draft.full_name:
        await state.set_state(UserBookingStates.email)
        if draft.email:
            await _send(
                target,
                messages.EMAIL_FOUND.format(email=draft.email),
                reply_markup=email_found_keyboard(),
            )
            return
        await _send(target, messages.EMAIL, reply_markup=text_navigation_keyboard())
        return
    await state.set_state(UserBookingStates.name)
    await _send(target, messages.NAME, reply_markup=text_navigation_keyboard(include_back=False))


async def _show_meeting_types(
    target: Message | CallbackQuery,
    state: FSMContext,
    deps: UserFlowDependencies,
) -> None:
    meeting_types = await deps.meeting_types.list_active()
    await state.set_state(UserBookingStates.meeting_type)
    await _send(target, messages.MEETING_TYPE, reply_markup=meeting_types_keyboard(meeting_types))


async def _show_dates(
    target: Message | CallbackQuery,
    state: FSMContext,
    deps: UserFlowDependencies,
    *,
    page: int = 0,
) -> None:
    schedule = await deps.schedule.context_for_date(deps.clock().date())
    dates = deps.flow.available_dates(now=deps.clock(), settings=schedule.settings)
    await state.set_state(UserBookingStates.date)
    await _send(target, messages.DATE, reply_markup=dates_keyboard(dates, page=page))


async def _show_review(
    target: Message | CallbackQuery,
    state: FSMContext,
    deps: UserFlowDependencies,
) -> None:
    draft = _draft_from_data(await state.get_data())
    meeting_type = await _meeting_type_for_draft(draft, deps)
    await state.set_state(UserBookingStates.review)
    await _send(
        target,
        _review_text(draft, meeting_type),
        reply_markup=review_keyboard(),
    )


async def _handle_text_navigation(
    message: Message,
    state: FSMContext,
    deps: UserFlowDependencies,
) -> bool:
    if message.text == CANCEL:
        await state.clear()
        logger.info("User flow cancelled", extra={"event": "user_flow_cancelled"})
        await message.answer(
            messages.CANCELLED_FLOW,
            reply_markup=menu_reply_keyboard(),
        )
        return True
    if message.text == BACK:
        logger.info("User flow back pressed", extra={"event": "user_flow_back"})
        await _go_back_message(message, state, deps)
        return True
    return False


async def _go_back(
    callback: CallbackQuery,
    state: FSMContext,
    deps: UserFlowDependencies,
) -> None:
    current = await state.get_state()
    if current == UserBookingStates.email.state:
        await state.set_state(UserBookingStates.name)
        await _edit_or_answer(callback, messages.NAME)
    elif current == UserBookingStates.meeting_type.state:
        await state.set_state(UserBookingStates.email)
        await _edit_or_answer(callback, messages.EMAIL)
    elif current == UserBookingStates.duration.state:
        await _show_meeting_types(callback, state, deps)
    elif current in {UserBookingStates.date.state, UserBookingStates.time.state}:
        await _show_meeting_types(callback, state, deps)
    elif current == UserBookingStates.comment.state:
        await _show_dates(callback, state, deps)
    elif current == UserBookingStates.review.state:
        await state.set_state(UserBookingStates.comment)
        await _edit_or_answer(callback, messages.COMMENT, reply_markup=comment_keyboard())
    else:
        await _edit_or_answer(callback, messages.MAIN_MENU, reply_markup=main_menu_keyboard())


async def _go_back_message(
    message: Message,
    state: FSMContext,
    deps: UserFlowDependencies,
) -> None:
    current = await state.get_state()
    if current == UserBookingStates.email.state:
        await state.set_state(UserBookingStates.name)
        await message.answer(
            messages.NAME,
            reply_markup=text_navigation_keyboard(include_back=False),
        )
    elif current == UserBookingStates.comment.state:
        await _show_dates(message, state, deps)
    else:
        await state.clear()
        await message.answer(messages.MAIN_MENU, reply_markup=main_menu_keyboard())


async def _ensure_user(message: Message, deps: UserFlowDependencies) -> UserProfile:
    if not message.from_user:
        raise RuntimeError("Telegram user is required.")
    existing = await deps.users.get_by_telegram_id(message.from_user.id)
    user = deps.booking_service.create_or_update_user(
        telegram_id=message.from_user.id,
        telegram_username=message.from_user.username,
        now=deps.clock(),
        existing_user=existing,
    )
    await deps.users.save(user)
    return user


async def _ensure_user_from_callback(
    callback: CallbackQuery,
    deps: UserFlowDependencies,
) -> UserProfile:
    existing = await deps.users.get_by_telegram_id(callback.from_user.id)
    user = deps.booking_service.create_or_update_user(
        telegram_id=callback.from_user.id,
        telegram_username=callback.from_user.username,
        now=deps.clock(),
        existing_user=existing,
    )
    await deps.users.save(user)
    return user


async def _meeting_type_for_draft(
    draft: BookingDraft,
    deps: UserFlowDependencies,
) -> MeetingType | None:
    if not draft.meeting_type_id:
        return None
    return await deps.meeting_types.get(draft.meeting_type_id)


async def _previous_booking_for_draft(
    draft: BookingDraft,
    deps: UserFlowDependencies,
    user: UserProfile,
) -> BookingRecord | None:
    if not draft.previous_booking_id:
        return None
    return await deps.bookings.get_for_user(draft.previous_booking_id, user.id)


async def _send(target: Message | CallbackQuery, text: str, **kwargs) -> None:
    if isinstance(target, CallbackQuery):
        await _edit_or_answer(target, text, **kwargs)
        return
    await target.answer(text, **kwargs)


async def _edit_or_answer(callback: CallbackQuery, text: str, **kwargs) -> None:
    if callback.message:
        reply_markup = kwargs.get("reply_markup")
        if reply_markup is not None and not isinstance(reply_markup, InlineKeyboardMarkup):
            await callback.message.answer(text, **kwargs)
            return
        try:
            await callback.message.edit_text(text, **kwargs)
        except TelegramBadRequest as error:
            if "message is not modified" in str(error).lower():
                return
            await callback.message.answer(text, **kwargs)


async def _save_draft(state: FSMContext, draft: BookingDraft) -> None:
    await state.update_data(
        draft={
            "full_name": draft.full_name,
            "email": draft.email,
            "meeting_type_id": str(draft.meeting_type_id) if draft.meeting_type_id else None,
            "duration_minutes": draft.duration_minutes,
            "selected_date": draft.selected_date.isoformat() if draft.selected_date else None,
            "starts_at": draft.starts_at.isoformat() if draft.starts_at else None,
            "ends_at": draft.ends_at.isoformat() if draft.ends_at else None,
            "user_comment": draft.user_comment,
            "previous_booking_id": (
                str(draft.previous_booking_id) if draft.previous_booking_id else None
            ),
        }
    )


def _draft_from_data(data: dict) -> BookingDraft:
    raw = data.get("draft") or {}
    return BookingDraft(
        full_name=raw.get("full_name"),
        email=raw.get("email"),
        meeting_type_id=UUID(raw["meeting_type_id"]) if raw.get("meeting_type_id") else None,
        duration_minutes=raw.get("duration_minutes"),
        selected_date=(
            date.fromisoformat(raw["selected_date"]) if raw.get("selected_date") else None
        ),
        starts_at=datetime.fromisoformat(raw["starts_at"]) if raw.get("starts_at") else None,
        ends_at=datetime.fromisoformat(raw["ends_at"]) if raw.get("ends_at") else None,
        user_comment=raw.get("user_comment"),
        previous_booking_id=(
            UUID(raw["previous_booking_id"]) if raw.get("previous_booking_id") else None
        ),
    )


def _business_error_text(error: Exception) -> str:
    if isinstance(error, BusinessRuleError):
        if error.rule == "user_blocked":
            return messages.BLOCKED
        if error.rule == "max_active_bookings":
            return messages.BOOKING_LIMIT
        if error.rule == "personal_data_consent_required":
            return messages.CONSENT_REQUIRED
    return messages.ACTION_UNAVAILABLE


def _review_text(draft: BookingDraft, meeting_type: MeetingType | None) -> str:
    lines = [
        messages.REVIEW,
        "",
        f"Имя: {draft.full_name}",
        f"Email: {draft.email}",
        f"Тип: {meeting_type.name if meeting_type else '-'}",
            f"Длительность: {draft.duration_minutes} минут",
        (
            f"Дата и время: {format_datetime_msk(draft.starts_at)}"
            if draft.starts_at
            else "Дата и время: -"
        ),
    ]
    if draft.user_comment:
        lines.append(f"Комментарий: {draft.user_comment}")
    return "\n".join(lines)


def _bookings_text(bookings: list[BookingRecord]) -> str:
    lines = ["Ваши заявки:"]
    lines.extend(_booking_summary(booking) for booking in bookings)
    return "\n".join(lines)


def _booking_text(booking: BookingRecord) -> str:
    return "\n".join(["Заявка:", _booking_summary(booking)])


def _booking_summary(booking: BookingRecord) -> str:
    return (
        f"{format_datetime_msk(booking.starts_at)}, "
        f"{booking.duration_minutes} минут, {booking_status_label(booking.status)}"
    )
