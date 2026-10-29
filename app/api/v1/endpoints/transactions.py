"""Nedarim Plus transaction webhook receiver."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.webhook import NedarimWebhookResponse
from app.services.donation_receipt_service import (
    DonationReceiptService,
    process_donation_receipt_background,
)
from app.services.nedarim_hmac import diagnose_nedarim_signature, verify_nedarim_signature

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/transactions", response_model=NedarimWebhookResponse)
async def nedarim_transaction_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    x_nedarim_timestamp: str | None = Header(default=None, alias="X-Nedarim-Timestamp"),
    x_nedarim_signature: str | None = Header(default=None, alias="X-Nedarim-Signature"),
) -> NedarimWebhookResponse:
    raw_body = await request.body()

    if not settings.nedarim_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    valid = verify_nedarim_signature(
        timestamp=x_nedarim_timestamp,
        signature_header=x_nedarim_signature,
        raw_body=raw_body,
        secret=settings.nedarim_webhook_secret,
        max_skew_seconds=settings.nedarim_hmac_max_skew_seconds,
    )
    if not valid:
        diagnosis = diagnose_nedarim_signature(
            timestamp=x_nedarim_timestamp,
            signature_header=x_nedarim_signature,
            raw_body=raw_body,
            secret=settings.nedarim_webhook_secret,
            max_skew_seconds=settings.nedarim_hmac_max_skew_seconds,
        )
        logger.warning("nedarim webhook rejected: %s", diagnosis)
        raise HTTPException(status_code=401, detail="Invalid Nedarim signature")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON object")

    service = DonationReceiptService(db)
    try:
        record, should_process = await service.upsert_from_webhook(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if should_process:
        background_tasks.add_task(process_donation_receipt_background, record.id)

    logger.info(
        "nedarim transaction stored transaction_id=%s status=%s web_doc_id=%s",
        record.transaction_id,
        record.status,
        record.web_doc_id,
    )
    return NedarimWebhookResponse(WEBDocID=record.web_doc_id)
