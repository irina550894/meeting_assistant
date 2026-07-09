from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.persistence.models.booking import Booking


class User(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    is_blocked: Mapped[bool] = mapped_column(default=False, nullable=False)
    telegram_username_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_url: Mapped[str | None] = mapped_column(String(2048))
    policy_url: Mapped[str | None] = mapped_column(String(2048))

    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")
