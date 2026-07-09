import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from app.persistence.models.enums import BookingStatus

if TYPE_CHECKING:
    from app.persistence.models.meeting_type import MeetingType
    from app.persistence.models.reservation import SlotReservation
    from app.persistence.models.user import User


class Booking(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("duration_minutes in (30, 60, 90)", name="valid_duration_minutes"),
        CheckConstraint("starts_at < ends_at", name="valid_time_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    meeting_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meeting_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50),
        default=BookingStatus.PENDING.value,
        index=True,
        nullable=False,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    google_calendar_event_id: Mapped[str | None] = mapped_column(String(1024))
    meeting_url: Mapped[str | None] = mapped_column(String(2048))
    is_reschedule_request: Mapped[bool] = mapped_column(default=False, nullable=False)
    previous_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="SET NULL"),
    )

    user: Mapped["User"] = relationship(back_populates="bookings")
    meeting_type: Mapped["MeetingType"] = relationship(back_populates="bookings")
    previous_booking: Mapped["Booking | None"] = relationship(remote_side="Booking.id")
    reservation: Mapped["SlotReservation | None"] = relationship(back_populates="booking")
