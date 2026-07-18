"""Add sequential booking display numbers.

Revision ID: 20260719_0005
Revises: 20260715_0004
Create Date: 2026-07-19

"""

import sqlalchemy as sa
from alembic import op

revision = "20260719_0005"
down_revision = "20260715_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS booking_display_number_seq")
    op.add_column("bookings", sa.Column("display_number", sa.Integer(), nullable=True))
    op.execute(
        """
        WITH numbered AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS number
            FROM bookings
        )
        UPDATE bookings
        SET display_number = numbered.number
        FROM numbered
        WHERE bookings.id = numbered.id
        """
    )
    op.execute(
        """
        SELECT setval(
            'booking_display_number_seq',
            COALESCE((SELECT MAX(display_number) FROM bookings), 0) + 1,
            false
        )
        """
    )
    op.alter_column(
        "bookings",
        "display_number",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("nextval('booking_display_number_seq'::regclass)"),
    )
    op.create_index(
        "ix_bookings_display_number",
        "bookings",
        ["display_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_display_number", table_name="bookings")
    op.drop_column("bookings", "display_number")
    op.execute("DROP SEQUENCE IF EXISTS booking_display_number_seq")
