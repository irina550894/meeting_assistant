import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from app.persistence.models.enums import BackgroundJobStatus


class BackgroundJob(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "background_jobs"

    job_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        default=BackgroundJobStatus.PENDING.value,
        index=True,
        nullable=False,
    )
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
    )
