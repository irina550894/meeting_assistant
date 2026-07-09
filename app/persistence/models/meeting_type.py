from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.persistence.models.booking import Booking


class MeetingType(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "meeting_types"
    __table_args__ = (
        CheckConstraint(
            "array_length(allowed_durations_minutes, 1) > 0",
            name="durations_not_empty",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_durations_minutes: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    is_fixed_duration: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="meeting_type")
