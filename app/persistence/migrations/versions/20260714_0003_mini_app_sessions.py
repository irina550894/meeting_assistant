"""Add Mini App sessions.

Revision ID: 20260714_0003
Revises: 20260711_0002
Create Date: 2026-07-14

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260714_0003"
down_revision = "20260711_0002"
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "mini_app_sessions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_hash", sa.String(length=128), nullable=False),
        sa.Column("telegram_auth_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_hash"),
    )
    op.create_index("ix_mini_app_sessions_expires_at", "mini_app_sessions", ["expires_at"])
    op.create_index("ix_mini_app_sessions_user_id", "mini_app_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_mini_app_sessions_user_id", table_name="mini_app_sessions")
    op.drop_index("ix_mini_app_sessions_expires_at", table_name="mini_app_sessions")
    op.drop_table("mini_app_sessions")
