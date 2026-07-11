"""Use one-hour slot step by default.

Revision ID: 20260711_0002
Revises: 20260709_0001
Create Date: 2026-07-11

"""

from alembic import op

revision = "20260711_0002"
down_revision = "20260709_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("update schedule_settings set slot_step_minutes = 60")


def downgrade() -> None:
    op.execute("update schedule_settings set slot_step_minutes = 30")
