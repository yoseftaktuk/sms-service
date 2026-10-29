"""Persist Nedarim donations and orchestrate receipt link delivery."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.models import DonationReceipt
from app.services.messaging.phone import normalize_israeli_phone
from app.services.messaging.sms_client import SmsSendError, send_sms
from app.services.messaging.whatsapp_client import WhatsAppSendError, send_whatsapp
from app.services.nedarim_client import resolve_receipt_url_from_webhook, show_invoice

logger = logging.getLogger(__name__)

STATUS_RECEIVED = "received"
STATUS_RECEIPT_PENDING = "receipt_pending"
STATUS_SEND_PENDING = "send_pending"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_SKIPPED_NO_PHONE = "skipped_no_phone"

TERMINAL_STATUSES = {STATUS_SENT, STATUS_SKIPPED_NO_PHONE}


def _str_field(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def build_receipt_message(*, donor_name: str | None, amount: str | None, receipt_url: str) -> str:
    name = donor_name or "תורם יקר"
    amount_part = f" בסך {amount} ₪" if amount else ""
    return f"שלום {name}, תודה על תרומתך{amount_part} לבית כנסת פועלי צדק. הקבלה שלך: {receipt_url}"


class DonationReceiptService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_transaction_id(self, transaction_id: str) -> DonationReceipt | None:
        result = await self.db.execute(
            select(DonationReceipt).where(DonationReceipt.transaction_id == transaction_id)
        )
        return result.scalar_one_or_none()

    async def upsert_from_webhook(self, payload: dict[str, Any]) -> tuple[DonationReceipt, bool]:
        """Create or update a donation receipt from a Nedarim transaction webhook.

        Returns (record, should_process) where should_process is False when already sent
        or when there is nothing to deliver.
        """
        transaction_id = _str_field(payload, "TransactionId")
        if not transaction_id:
            raise ValueError("TransactionId is required")

        if _str_field(payload, "Status") == "Error":
            raise ValueError("refusal payload is not accepted on transaction webhook")

        mosad = _str_field(payload, "MosadNumber")
        if mosad and mosad != str(settings.nedarim_mosad_id).strip():
            raise ValueError("MosadNumber does not match")

        existing = await self.get_by_transaction_id(transaction_id)
        if existing and existing.status == STATUS_SENT:
            return existing, False

        if existing:
            record = existing
        else:
            record = DonationReceipt(transaction_id=transaction_id)
            self.db.add(record)

        should_process = self._apply_webhook_snapshot(record, payload)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raced = await self.get_by_transaction_id(transaction_id)
            if raced is None:
                raise
            if raced.status == STATUS_SENT:
                return raced, False
            should_process = self._apply_webhook_snapshot(raced, payload)
            await self.db.commit()
            await self.db.refresh(raced)
            return raced, should_process

        await self.db.refresh(record)
        return record, should_process

    def _apply_webhook_snapshot(self, record: DonationReceipt, payload: dict[str, Any]) -> bool:
        receipt_data = _str_field(payload, "ReceiptData")
        receipt_url = resolve_receipt_url_from_webhook(
            receipt_data=receipt_data,
            receipt_created=_str_field(payload, "ReceiptCreated"),
        )
        phone = normalize_israeli_phone(_str_field(payload, "Phone"))

        record.amount = _str_field(payload, "Amount")
        record.currency = _str_field(payload, "Currency")
        record.groupe = _str_field(payload, "Groupe")
        record.confirmation = _str_field(payload, "Confirmation")
        record.transaction_time = _str_field(payload, "TransactionTime")
        record.donor_name = _str_field(payload, "ClientName")
        record.donor_phone = phone
        record.donor_email = _str_field(payload, "Mail")
        record.receipt_created = _str_field(payload, "ReceiptCreated")
        record.receipt_doc_num = _str_field(payload, "ReceiptDocNum")
        record.receipt_data = receipt_data
        if receipt_url:
            record.receipt_url = receipt_url

        if not phone:
            record.status = STATUS_SKIPPED_NO_PHONE
            return False
        if not record.receipt_url:
            record.status = STATUS_RECEIPT_PENDING
            return True
        record.status = STATUS_SEND_PENDING
        return True

    async def process_delivery(self, receipt_id: UUID) -> None:
        result = await self.db.execute(select(DonationReceipt).where(DonationReceipt.id == receipt_id))
        record = result.scalar_one_or_none()
        if record is None or record.status in TERMINAL_STATUSES:
            return

        if not record.receipt_url:
            record.receipt_url = await show_invoice(record.transaction_id)
            if not record.receipt_url:
                record.status = STATUS_RECEIPT_PENDING
                await self.db.commit()
                return

        if not record.donor_phone:
            record.status = STATUS_SKIPPED_NO_PHONE
            await self.db.commit()
            return

        message = build_receipt_message(
            donor_name=record.donor_name,
            amount=record.amount,
            receipt_url=record.receipt_url,
        )
        record.send_attempts = (record.send_attempts or 0) + 1
        record.status = STATUS_SEND_PENDING

        try:
            await send_sms(phone=record.donor_phone, message=message)
            record.status = STATUS_SENT
            record.channel = "sms"
            record.sent_at = datetime.now(UTC)
            record.last_error = None
            await self.db.commit()
            return
        except SmsSendError as exc:
            logger.info("SMS failed for transaction_id=%s: %s", record.transaction_id, exc)
            record.last_error = str(exc)[:500]

        try:
            await send_whatsapp(phone=record.donor_phone, message=message)
            record.status = STATUS_SENT
            record.channel = "whatsapp"
            record.sent_at = datetime.now(UTC)
            record.last_error = None
            await self.db.commit()
            return
        except WhatsAppSendError as exc:
            logger.info("WhatsApp failed for transaction_id=%s: %s", record.transaction_id, exc)
            record.last_error = str(exc)[:500]
            record.status = STATUS_FAILED
            await self.db.commit()


async def process_donation_receipt_background(receipt_id: UUID) -> None:
    """Background worker entrypoint with its own DB session."""
    async with async_session_factory() as session:
        service = DonationReceiptService(session)
        try:
            await service.process_delivery(receipt_id)
        except Exception:
            logger.exception("Background delivery failed for receipt_id=%s", receipt_id)
