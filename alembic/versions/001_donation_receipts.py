"""create donation_receipts

Revision ID: 001_donation_receipts
Revises:
Create Date: 2026-10-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_donation_receipts"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "donation_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("web_doc_id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("transaction_id", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.String(length=50), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("groupe", sa.String(length=200), nullable=True),
        sa.Column("confirmation", sa.String(length=100), nullable=True),
        sa.Column("transaction_time", sa.String(length=50), nullable=True),
        sa.Column("donor_name", sa.String(length=200), nullable=True),
        sa.Column("donor_phone", sa.String(length=50), nullable=True),
        sa.Column("donor_email", sa.String(length=200), nullable=True),
        sa.Column("receipt_created", sa.String(length=20), nullable=True),
        sa.Column("receipt_doc_num", sa.String(length=100), nullable=True),
        sa.Column("receipt_data", sa.Text(), nullable=True),
        sa.Column("receipt_url", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=True),
        sa.Column("send_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("web_doc_id"),
        sa.UniqueConstraint("transaction_id"),
    )
    op.create_index("ix_donation_receipts_transaction_id", "donation_receipts", ["transaction_id"])
    op.create_index("ix_donation_receipts_status", "donation_receipts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_donation_receipts_status", table_name="donation_receipts")
    op.drop_index("ix_donation_receipts_transaction_id", table_name="donation_receipts")
    op.drop_table("donation_receipts")
