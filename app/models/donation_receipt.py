import uuid
from datetime import datetime

from sqlalchemy import DateTime, Identity, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class DonationReceipt(Base):
    __tablename__ = "donation_receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    web_doc_id: Mapped[int] = mapped_column(Integer, Identity(always=False), unique=True)
    transaction_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    amount: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    groupe: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confirmation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transaction_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    donor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    donor_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    donor_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    receipt_created: Mapped[str | None] = mapped_column(String(20), nullable=True)
    receipt_doc_num: Mapped[str | None] = mapped_column(String(100), nullable=True)
    receipt_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="received", index=True)
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    send_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
