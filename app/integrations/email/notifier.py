import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol
from uuid import UUID

from app.core.booking import BookingRecord, MeetingType, UserProfile
from app.core.datetime_formatting import format_datetime_msk
from app.logging.config import get_logger
from app.settings.config import Settings

logger = get_logger(__name__)


class LookupStore(Protocol):
    async def get(self, entity_id: UUID) -> object | None: ...


class UserEmailSender(Protocol):
    async def send(self, *, to_email: str, subject: str, body: str) -> None: ...


class SmtpUserEmailSender:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.smtp_host and self.settings.smtp_from_email)

    async def send(self, *, to_email: str, subject: str, body: str) -> None:
        if not self.configured:
            raise EmailNotConfiguredError
        await asyncio.to_thread(
            self._send_sync,
            to_email=to_email,
            subject=subject,
            body=body,
        )

    def _send_sync(self, *, to_email: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_header()
        message["To"] = to_email
        message.set_content(body)

        host = self.settings.smtp_host
        if host is None:
            raise EmailNotConfiguredError

        with smtplib.SMTP(host, self.settings.smtp_port, timeout=15) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            if self.settings.smtp_username and self.settings.smtp_password:
                smtp.login(
                    self.settings.smtp_username,
                    self.settings.smtp_password.get_secret_value(),
                )
            smtp.send_message(message)

    def _from_header(self) -> str:
        if self.settings.smtp_from_email is None:
            raise EmailNotConfiguredError
        name = self.settings.smtp_from_name.strip()
        if not name:
            return self.settings.smtp_from_email
        return f"{name} <{self.settings.smtp_from_email}>"


class UserEmailNotifier:
    def __init__(
        self,
        *,
        settings: Settings,
        store: LookupStore,
        sender: UserEmailSender | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.sender = sender or SmtpUserEmailSender(settings=settings)

    async def booking_created(self, booking: BookingRecord) -> None:
        await self._send_booking_email(
            booking,
            kind="booking_created",
            subject=f"Заявка {_booking_number_label(booking)} получена",
            intro="Ваша заявка получена и ожидает подтверждения.",
        )

    async def booking_cancelled_by_user(self, booking: BookingRecord) -> None:
        await self._send_booking_email(
            booking,
            kind="booking_cancelled_by_user",
            subject=f"Заявка {_booking_number_label(booking)} отменена",
            intro="Ваша заявка отменена.",
            reason=booking.cancellation_reason,
        )

    async def reschedule_requested(self, booking: BookingRecord) -> None:
        await self._send_booking_email(
            booking,
            kind="reschedule_requested",
            subject=f"Запрос на перенос {_booking_number_label(booking)} получен",
            intro="Ваш запрос на перенос получен и ожидает подтверждения.",
        )

    async def booking_confirmed(self, booking: BookingRecord) -> None:
        await self._send_booking_email(
            booking,
            kind="booking_confirmed",
            subject=f"Встреча {_booking_number_label(booking)} подтверждена",
            intro="Ваша встреча подтверждена.",
        )

    async def booking_rejected(self, booking: BookingRecord, reason: str | None) -> None:
        await self._send_booking_email(
            booking,
            kind="booking_rejected",
            subject=f"Заявка {_booking_number_label(booking)} отклонена",
            intro="Ваша заявка отклонена.",
            reason=reason,
        )

    async def booking_cancelled_by_admin(
        self,
        booking: BookingRecord,
        reason: str | None,
    ) -> None:
        await self._send_booking_email(
            booking,
            kind="booking_cancelled_by_admin",
            subject=f"Встреча {_booking_number_label(booking)} отменена",
            intro="Встреча отменена администратором.",
            reason=reason,
        )

    async def user_blocked(self, user: UserProfile) -> None:
        if not user.email:
            return
        await self._safe_send(
            to_email=user.email,
            subject="Запись на встречу недоступна",
            body="\n".join(
                [
                    "Здравствуйте.",
                    "",
                    "К сожалению, сейчас Вы не можете создать заявку на встречу.",
                ]
            ),
            kind="user_blocked",
            booking=None,
        )

    async def send_user_message(self, user: UserProfile, text: str) -> None:
        if not user.email:
            return
        await self._safe_send(
            to_email=user.email,
            subject="Сообщение по заявке на встречу",
            body=text,
            kind="admin_user_message",
            booking=None,
        )

    async def _send_booking_email(
        self,
        booking: BookingRecord,
        *,
        kind: str,
        subject: str,
        intro: str,
        reason: str | None = None,
    ) -> None:
        user = await self.store.get(booking.user_id)
        meeting_type = await self.store.get(booking.meeting_type_id)
        if not isinstance(user, UserProfile):
            return
        if not user.email:
            logger.info(
                "User email is missing",
                extra={"event": "email_skipped", "reason": "user_email_missing", "kind": kind},
            )
            return
        meeting_type_name = meeting_type.name if isinstance(meeting_type, MeetingType) else "-"
        await self._safe_send(
            to_email=user.email,
            subject=subject,
            body=_booking_email_body(
                booking=booking,
                user=user,
                meeting_type_name=meeting_type_name,
                intro=intro,
                reason=reason,
            ),
            kind=kind,
            booking=booking,
        )

    async def _safe_send(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        kind: str,
        booking: BookingRecord | None,
    ) -> None:
        try:
            await self.sender.send(to_email=to_email, subject=subject, body=body)
        except EmailNotConfiguredError:
            logger.info(
                "Email delivery is not configured",
                extra={
                    "event": "email_not_configured",
                    "kind": kind,
                    "booking_id": str(booking.id) if booking else None,
                },
            )
        except Exception as error:
            logger.error(
                "Email delivery failed",
                extra={
                    "event": "email_delivery_failed",
                    "kind": kind,
                    "booking_id": str(booking.id) if booking else None,
                    "error_type": type(error).__name__,
                },
            )
        else:
            logger.info(
                "Email delivered",
                extra={
                    "event": "email_sent",
                    "kind": kind,
                    "booking_id": str(booking.id) if booking else None,
                },
            )


class EmailNotConfiguredError(RuntimeError):
    pass


def _booking_email_body(
    *,
    booking: BookingRecord,
    user: UserProfile,
    meeting_type_name: str,
    intro: str,
    reason: str | None,
) -> str:
    lines = [
        f"Здравствуйте, {user.full_name or 'клиент'}.",
        "",
        intro,
        "",
        f"Номер заявки: {_booking_number_label(booking)}",
        f"Тип встречи: {meeting_type_name}",
        f"Дата и время: {format_datetime_msk(booking.starts_at)}",
        f"Длительность: {booking.duration_minutes} минут",
        f"Комментарий: {booking.user_comment or '-'}",
    ]
    if booking.meeting_url:
        lines.append(f"Ссылка на видеовстречу: {booking.meeting_url}")
    if reason:
        lines.append(f"Причина: {reason}")
    lines.extend(["", "С уважением,", "Ассистент по встречам"])
    return "\n".join(lines)


def _booking_number_label(booking: BookingRecord) -> str:
    if booking.display_number is not None:
        return f"№{booking.display_number}"
    return str(booking.id)
