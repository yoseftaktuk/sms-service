"""add donation_receipts.short_url

Revision ID: 002_donation_receipt_short_url
Revises: 001_donation_receipts
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_donation_receipt_short_url"
down_revision: str | None = "001_donation_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "donation_receipts",
        sa.Column("short_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("donation_receipts", "short_url")
