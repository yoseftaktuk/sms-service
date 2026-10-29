"""Yemot HaMashiach SendSms client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.services.messaging.phone import normalize_israeli_phone

logger = logging.getLogger(__name__)


class SmsSendError(Exception):
    """Raised when Yemot rejects or fails an SMS send."""


async def send_sms(*, phone: str, message: str) -> dict[str, Any]:
    """Send one SMS via Yemot SendSms. Returns the JSON response on success."""
    if not settings.yemot_api_key:
        raise SmsSendError("Yemot API key is not configured")

    normalized = normalize_israeli_phone(phone)
    if not normalized:
        raise SmsSendError("invalid phone number")

    params: dict[str, str] = {
        "phones": normalized,
        "message": message,
    }
    if settings.yemot_sms_from:
        params["from"] = settings.yemot_sms_from

    url = f"{settings.yemot_api_base_url.rstrip('/')}/SendSms"
    headers = {"Authorization": settings.yemot_api_key}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.exception("Yemot SendSms request failed")
        raise SmsSendError("Yemot request failed") from exc

    if data.get("responseStatus") != "OK":
        raise SmsSendError(str(data.get("message") or data.get("responseStatus") or "SendSms failed"))

    oks = data.get("oks") or []
    oks_normalized = {normalize_israeli_phone(str(item)) for item in oks}
    if normalized not in oks_normalized and oks:
        errors = data.get("errors") or {}
        raise SmsSendError(f"phone not in oks: {errors}")

    return data
