"""Hourly pull of Nedarim external incomes and one-time receipt delivery."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DonationReceipt, SyncCursor
from app.services.donation_receipt_service import (
    STATUS_RECEIPT_PENDING,
    STATUS_SEND_PENDING,
    STATUS_SENT,
    STATUS_SKIPPED_NO_PHONE,
    STATUS_SKIPPED_NO_RECEIPT,
    TERMINAL_STATUSES,
    DonationReceiptService,
)
from app.services.messaging.phone import normalize_israeli_phone
from app.services.nedarim_client import NedarimApiError, get_achnasot_page

logger = logging.getLogger(__name__)

CURSOR_KEY = "achnasot"
SOURCE_ACHNASOT = "achnasot"
PAGE_SIZE = 200
MAX_PAGES = 10
RECEIPT_WAIT_DAYS = 30
LOCK_KEY = 701866901


class AchnasotSyncService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.receipts = DonationReceiptService(db)

    async def sync(self) -> dict[str, Any]:
        if not await self._try_lock():
            logger.info("achnasot sync skipped; another run holds the lock")
            return _result("busy", await self._current_last_id())

        try:
            result = await self._sync_locked()
        finally:
            await self._unlock()

        logger.info(
            "achnasot sync status=%s last_id=%s fetched=%s sent=%s",
            result["status"],
            result["last_id"],
            result["fetched"],
            result["sent"],
        )
        return result

    async def _sync_locked(self) -> dict[str, Any]:
        cursor = await self._get_cursor()
        if cursor is None:
            return await self._bootstrap()

        last_id = cursor.last_id
        fetched = 0
        sent = 0
        seen_ids: set[UUID] = set()

        try:
            for _ in range(MAX_PAGES):
                page = await get_achnasot_page(last_id=last_id, max_id=PAGE_SIZE, order="Asc")
                if not page:
                    break
                incomes = [(item, _income_id(item)) for item in page]
                deliver_now: list[UUID] = []
                for item, income_id in incomes:
                    record, should_deliver = await self._upsert(item, income_id)
                    seen_ids.add(record.id)
                    fetched += 1
                    if should_deliver and record.id not in deliver_now:
                        deliver_now.append(record.id)
                last_id = max(income_id for _, income_id in incomes)
                await self._save_cursor(last_id)
                await self.db.commit()
                for receipt_id in deliver_now:
                    if await self._deliver(receipt_id):
                        sent += 1
                if len(page) < PAGE_SIZE:
                    break
        except NedarimApiError as exc:
            if exc.rate_limited:
                logger.warning("GetAchnasotJson rate limited")
                return _result("rate_limited", last_id, fetched, sent)
            raise

        sent += await self._retry_open(seen_ids)
        return _result("ok", last_id, fetched, sent)

    async def _bootstrap(self) -> dict[str, Any]:
        try:
            page = await get_achnasot_page(max_id=1, order="Desc")
        except NedarimApiError as exc:
            if exc.rate_limited:
                logger.warning("GetAchnasotJson rate limited during bootstrap")
                return _result("rate_limited", None)
            raise

        last_id = _income_id(page[0]) if page else 0
        await self._save_cursor(last_id)
        await self.db.commit()
        return _result("bootstrapped", last_id)

    async def _retry_open(self, exclude_ids: set[UUID]) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=RECEIPT_WAIT_DAYS)
        stmt = (
            select(DonationReceipt)
            .where(
                DonationReceipt.source == SOURCE_ACHNASOT,
                DonationReceipt.status.notin_(TERMINAL_STATUSES),
            )
            .order_by(DonationReceipt.created_at.asc())
        )
        if exclude_ids:
            stmt = stmt.where(DonationReceipt.id.notin_(exclude_ids))

        result = await self.db.execute(stmt)
        sent = 0
        for record in result.scalars():
            created = record.created_at
            if created is not None and _as_utc(created) < cutoff and not record.receipt_url:
                record.status = STATUS_SKIPPED_NO_RECEIPT
                await self.db.commit()
                logger.info("achnasot receipt wait expired achnasot_id=%s", record.achnasot_id)
                continue
            if await self._deliver(record.id):
                sent += 1
        return sent

    async def _upsert(self, item: dict[str, Any], income_id: int) -> tuple[DonationReceipt, bool]:
        existing = await self._get_by_achnasot_id(income_id)
        if existing and existing.status in TERMINAL_STATUSES:
            return existing, False

        if existing is None:
            record = DonationReceipt(
                transaction_id=f"achnasot:{income_id}",
                source=SOURCE_ACHNASOT,
                achnasot_id=income_id,
            )
            self.db.add(record)
        else:
            record = existing

        should_deliver = _apply_snapshot(record, item)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raced = await self._get_by_achnasot_id(income_id)
            if raced is None:
                raise
            if raced.status in TERMINAL_STATUSES:
                return raced, False
            should_deliver = _apply_snapshot(raced, item)
            await self.db.commit()
            await self.db.refresh(raced)
            return raced, should_deliver

        await self.db.refresh(record)
        return record, should_deliver

    async def _deliver(self, receipt_id: UUID) -> bool:
        await self.receipts.process_delivery(receipt_id)
        record = await self.db.get(DonationReceipt, receipt_id)
        return record is not None and record.status == STATUS_SENT

    async def _get_by_achnasot_id(self, achnasot_id: int) -> DonationReceipt | None:
        result = await self.db.execute(
            select(DonationReceipt).where(DonationReceipt.achnasot_id == achnasot_id)
        )
        return result.scalar_one_or_none()

    async def _get_cursor(self) -> SyncCursor | None:
        result = await self.db.execute(select(SyncCursor).where(SyncCursor.key == CURSOR_KEY))
        return result.scalar_one_or_none()

    async def _current_last_id(self) -> int | None:
        cursor = await self._get_cursor()
        if cursor is None:
            return None
        return cursor.last_id

    async def _save_cursor(self, last_id: int) -> None:
        cursor = await self._get_cursor()
        if cursor is None:
            self.db.add(SyncCursor(key=CURSOR_KEY, last_id=last_id))
            return
        cursor.last_id = last_id

    async def _try_lock(self) -> bool:
        result = await self.db.execute(
            text("SELECT pg_try_advisory_lock(CAST(:key AS bigint))"),
            {"key": LOCK_KEY},
        )
        return bool(result.scalar())

    async def _unlock(self) -> None:
        for _ in range(2):
            try:
                if not self.db.is_active:
                    await self.db.rollback()
                await self.db.execute(
                    text("SELECT pg_advisory_unlock(CAST(:key AS bigint))"),
                    {"key": LOCK_KEY},
                )
                return
            except Exception:
                logger.exception("achnasot sync failed to release lock")
        logger.error("achnasot sync lock was not released")


def _apply_snapshot(record: DonationReceipt, item: dict[str, Any]) -> bool:
    phone = normalize_israeli_phone(_text(item, "Phone"))
    record.amount = _clip(_text(item, "Amount"), 50)
    record.currency = _clip(_text(item, "Currency"), 10)
    record.groupe = _clip(_text(item, "Groupe"), 200)
    record.transaction_time = _clip(_text(item, "EntryTime") or _text(item, "Date"), 50)
    record.donor_name = _clip(_text(item, "ClientName"), 200)
    record.donor_phone = phone
    record.donor_email = _clip(_text(item, "Mail"), 200)
    record.receipt_created = "1" if _has_kabala(item.get("HasKabala")) else "0"

    if not phone:
        record.status = STATUS_SKIPPED_NO_PHONE
        return False
    if not _has_kabala(item.get("HasKabala")):
        record.status = STATUS_RECEIPT_PENDING
        return False
    record.status = STATUS_SEND_PENDING if record.receipt_url else STATUS_RECEIPT_PENDING
    return True


def _income_id(item: dict[str, Any]) -> int:
    raw = item.get("ID")
    if raw is None or str(raw).strip() == "":
        raise NedarimApiError("Achnasot item missing ID")
    try:
        return int(str(raw).strip())
    except ValueError as exc:
        raise NedarimApiError("Achnasot item has an invalid ID") from exc


def _has_kabala(value: object) -> bool:
    if value is True or value == 1:
        return True
    return str(value).strip().lower() in {"1", "true", "yes"}


def _text(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _result(status: str, last_id: int | None, fetched: int = 0, sent: int = 0) -> dict[str, Any]:
    return {"status": status, "last_id": last_id, "fetched": fetched, "sent": sent}
