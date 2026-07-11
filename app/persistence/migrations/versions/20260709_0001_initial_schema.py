"""Initial PostgreSQL schema.

Revision ID: 20260709_0001
Revises: None
Create Date: 2026-07-09

"""
from collections.abc import Sequence
from datetime import time

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260709_0001"
down_revision = None
branch_labels = None
depends_on = None


def timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=False),
        sa.Column("telegram_username_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_url", sa.String(length=2048), nullable=True),
        sa.Column("policy_url", sa.String(length=2048), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    op.create_table(
        "meeting_types",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("allowed_durations_minutes", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("is_fixed_duration", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "array_length(allowed_durations_minutes, 1) > 0",
            name="durations_not_empty",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "schedule_settings",
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("min_booking_lead_days", sa.Integer(), nullable=False),
        sa.Column("booking_horizon_days", sa.Integer(), nullable=False),
        sa.Column("slot_step_minutes", sa.Integer(), nullable=False),
        sa.Column("meeting_buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("daily_meeting_limit", sa.Integer(), nullable=True),
        sa.Column("default_meeting_url", sa.String(length=2048), nullable=True),
        sa.Column("personal_data_consent_url", sa.String(length=2048), nullable=True),
        sa.Column("personal_data_policy_url", sa.String(length=2048), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "working_hours",
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("is_working_day", sa.Boolean(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("weekday between 0 and 6", name="valid_weekday"),
        sa.CheckConstraint("start_time < end_time", name="valid_working_hours_range"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "schedule_restrictions",
        sa.Column("restriction_type", sa.String(length=50), nullable=False),
        sa.Column("restriction_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("admin_comment", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "restriction_type in ('closed_day', 'time_interval')",
            name="valid_restriction_type",
        ),
        sa.CheckConstraint(
            "start_time is null or end_time is null or start_time < end_time",
            name="valid_restriction_range",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schedule_restrictions_restriction_date",
        "schedule_restrictions",
        ["restriction_date"],
    )

    op.create_table(
        "bookings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("meeting_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("google_calendar_event_id", sa.String(length=1024), nullable=True),
        sa.Column("meeting_url", sa.String(length=2048), nullable=True),
        sa.Column("is_reschedule_request", sa.Boolean(), nullable=False),
        sa.Column("previous_booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("duration_minutes in (30, 60, 90)", name="valid_duration_minutes"),
        sa.CheckConstraint("starts_at < ends_at", name="valid_time_range"),
        sa.ForeignKeyConstraint(["meeting_type_id"], ["meeting_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bookings_reserved_until", "bookings", ["reserved_until"])
    op.create_index("ix_bookings_starts_at", "bookings", ["starts_at"])
    op.create_index("ix_bookings_status", "bookings", ["status"])
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])

    op.create_table(
        "slot_reservations",
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("starts_at < ends_at", name="valid_reservation_range"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    op.create_index("ix_slot_reservations_expires_at", "slot_reservations", ["expires_at"])
    op.create_index("ix_slot_reservations_starts_at", "slot_reservations", ["starts_at"])

    op.create_table(
        "background_jobs",
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_background_jobs_job_type", "background_jobs", ["job_type"])
    op.create_index("ix_background_jobs_run_at", "background_jobs", ["run_at"])
    op.create_index("ix_background_jobs_status", "background_jobs", ["status"])

    op.create_table(
        "audit_logs",
        sa.Column("actor_type", sa.String(length=50), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=150), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("error_type", sa.String(length=150), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_actor_type", "audit_logs", ["actor_type"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "google_oauth_tokens",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_uri", sa.String(length=2048), nullable=True),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider"),
    )

    op.create_table(
        "notification_logs",
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=100), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=True),
        sa.Column("template_key", sa.String(length=150), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_logs_channel", "notification_logs", ["channel"])
    op.create_index("ix_notification_logs_status", "notification_logs", ["status"])

    seed_initial_data()


def seed_initial_data() -> None:
    meeting_types = sa.table(
        "meeting_types",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("allowed_durations_minutes", postgresql.ARRAY(sa.Integer)),
        sa.column("is_fixed_duration", sa.Boolean),
    )
    schedule_settings = sa.table(
        "schedule_settings",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("timezone", sa.String),
        sa.column("min_booking_lead_days", sa.Integer),
        sa.column("booking_horizon_days", sa.Integer),
        sa.column("slot_step_minutes", sa.Integer),
        sa.column("meeting_buffer_minutes", sa.Integer),
        sa.column("daily_meeting_limit", sa.Integer),
        sa.column("default_meeting_url", sa.String),
    )
    working_hours = sa.table(
        "working_hours",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("weekday", sa.Integer),
        sa.column("is_working_day", sa.Boolean),
        sa.column("start_time", sa.Time),
        sa.column("end_time", sa.Time),
    )

    op.bulk_insert(
        meeting_types,
        [
            {
                "id": "00000000-0000-4000-8000-000000000101",
                "name": "Консультация",
                "slug": "consultation",
                "is_active": True,
                "allowed_durations_minutes": [30, 60, 90],
                "is_fixed_duration": False,
            },
            {
                "id": "00000000-0000-4000-8000-000000000102",
                "name": "Диагностика",
                "slug": "diagnostics",
                "is_active": True,
                "allowed_durations_minutes": [60],
                "is_fixed_duration": True,
            },
        ],
    )
    op.bulk_insert(
        schedule_settings,
        [
            {
                "id": "00000000-0000-4000-8000-000000000201",
                "timezone": "Europe/Moscow",
                "min_booking_lead_days": 1,
                "booking_horizon_days": 30,
                "slot_step_minutes": 60,
                "meeting_buffer_minutes": 90,
                "daily_meeting_limit": None,
                "default_meeting_url": "https://telemost.yandex.ru/j/75500242705811",
            }
        ],
    )
    op.bulk_insert(working_hours, default_working_hours_rows())


def default_working_hours_rows() -> Sequence[dict[str, object]]:
    return [
        {
            "id": f"00000000-0000-4000-8000-00000000030{weekday}",
            "weekday": weekday,
            "is_working_day": weekday < 5,
            "start_time": time(10, 0) if weekday < 5 else None,
            "end_time": time(18, 0) if weekday < 5 else None,
        }
        for weekday in range(7)
    ]


def downgrade() -> None:
    op.drop_index("ix_notification_logs_status", table_name="notification_logs")
    op.drop_index("ix_notification_logs_channel", table_name="notification_logs")
    op.drop_table("notification_logs")
    op.drop_table("google_oauth_tokens")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_background_jobs_status", table_name="background_jobs")
    op.drop_index("ix_background_jobs_run_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_job_type", table_name="background_jobs")
    op.drop_table("background_jobs")
    op.drop_index("ix_slot_reservations_starts_at", table_name="slot_reservations")
    op.drop_index("ix_slot_reservations_expires_at", table_name="slot_reservations")
    op.drop_table("slot_reservations")
    op.drop_index("ix_bookings_user_id", table_name="bookings")
    op.drop_index("ix_bookings_status", table_name="bookings")
    op.drop_index("ix_bookings_starts_at", table_name="bookings")
    op.drop_index("ix_bookings_reserved_until", table_name="bookings")
    op.drop_table("bookings")
    op.drop_index(
        "ix_schedule_restrictions_restriction_date",
        table_name="schedule_restrictions",
    )
    op.drop_table("schedule_restrictions")
    op.drop_table("working_hours")
    op.drop_table("schedule_settings")
    op.drop_table("meeting_types")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
