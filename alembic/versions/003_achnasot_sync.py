"""external income cursor and donation source

Revision ID: 003_achnasot_sync
Revises: 002_donation_receipt_short_url
Create Date: 2026-11-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_achnasot_sync"
down_revision: str | None = "002_donation_receipt_short_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "donation_receipts",
        sa.Column("source", sa.String(length=20), server_default="webhook", nullable=False),
    )
    op.add_column(
        "donation_receipts",
        sa.Column("achnasot_id", sa.BigInteger(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_donation_receipts_achnasot_id",
        "donation_receipts",
        ["achnasot_id"],
    )
    op.create_table(
        "sync_cursors",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("last_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("sync_cursors")
    op.drop_constraint("uq_donation_receipts_achnasot_id", "donation_receipts", type_="unique")
    op.drop_column("donation_receipts", "achnasot_id")
    op.drop_column("donation_receipts", "source")
