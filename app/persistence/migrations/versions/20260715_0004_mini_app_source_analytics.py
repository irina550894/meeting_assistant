"""Add Mini App source fields and analytics events.

Revision ID: 20260715_0004
Revises: 20260714_0003
Create Date: 2026-07-15

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260715_0004"
down_revision = "20260714_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column(
            "created_source",
            sa.String(length=50),
            server_default="telegram_bot",
            nullable=False,
        ),
    )
    op.create_index("ix_bookings_created_source", "bookings", ["created_source"])

    op.add_column(
        "audit_logs",
        sa.Column(
            "source",
            sa.String(length=50),
            server_default="telegram_bot",
            nullable=False,
        ),
    )
    op.create_index("ix_audit_logs_source", "audit_logs", ["source"])

    op.create_table(
        "mini_app_events",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_name", sa.String(length=150), nullable=False),
        sa.Column("source", sa.String(length=50), server_default="mini_app", nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mini_app_events_created_at", "mini_app_events", ["created_at"])
    op.create_index("ix_mini_app_events_event_name", "mini_app_events", ["event_name"])
    op.create_index("ix_mini_app_events_source", "mini_app_events", ["source"])
    op.create_index("ix_mini_app_events_user_id", "mini_app_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_mini_app_events_user_id", table_name="mini_app_events")
    op.drop_index("ix_mini_app_events_source", table_name="mini_app_events")
    op.drop_index("ix_mini_app_events_event_name", table_name="mini_app_events")
    op.drop_index("ix_mini_app_events_created_at", table_name="mini_app_events")
    op.drop_table("mini_app_events")

    op.drop_index("ix_audit_logs_source", table_name="audit_logs")
    op.drop_column("audit_logs", "source")

    op.drop_index("ix_bookings_created_source", table_name="bookings")
    op.drop_column("bookings", "created_source")
