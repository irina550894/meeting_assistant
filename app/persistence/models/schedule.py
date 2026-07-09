from datetime import date, time

from sqlalchemy import Boolean, CheckConstraint, Date, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from app.persistence.models.enums import RestrictionType


class ScheduleSettings(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_settings"

    timezone: Mapped[str] = mapped_column(String(100), default="Europe/Moscow", nullable=False)
    min_booking_lead_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    booking_horizon_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    slot_step_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    meeting_buffer_minutes: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    daily_meeting_limit: Mapped[int | None] = mapped_column(Integer)
    default_meeting_url: Mapped[str | None] = mapped_column(String(2048))
    personal_data_consent_url: Mapped[str | None] = mapped_column(String(2048))
    personal_data_policy_url: Mapped[str | None] = mapped_column(String(2048))


class WorkingHours(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "working_hours"
    __table_args__ = (
        CheckConstraint("weekday between 0 and 6", name="valid_weekday"),
        CheckConstraint("start_time < end_time", name="valid_working_hours_range"),
    )

    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    is_working_day: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time(timezone=False))
    end_time: Mapped[time | None] = mapped_column(Time(timezone=False))


class ScheduleRestriction(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_restrictions"
    __table_args__ = (
        CheckConstraint(
            "restriction_type in ('closed_day', 'time_interval')",
            name="valid_restriction_type",
        ),
        CheckConstraint(
            "start_time is null or end_time is null or start_time < end_time",
            name="valid_restriction_range",
        ),
    )

    restriction_type: Mapped[str] = mapped_column(
        String(50),
        default=RestrictionType.CLOSED_DAY.value,
        nullable=False,
    )
    restriction_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time(timezone=False))
    end_time: Mapped[time | None] = mapped_column(Time(timezone=False))
    admin_comment: Mapped[str | None] = mapped_column(Text)
