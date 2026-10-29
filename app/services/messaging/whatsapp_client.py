"""GreenAPI WhatsApp client (secondary channel)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.services.messaging.phone import to_whatsapp_chat_id

logger = logging.getLogger(__name__)


class WhatsAppSendError(Exception):
    """Raised when GreenAPI rejects or fails a WhatsApp send."""


async def send_whatsapp(*, phone: str, message: str) -> dict[str, Any]:
    """Send a text message via GreenAPI sendMessage."""
    if not settings.greenapi_id_instance or not settings.greenapi_api_token:
        raise WhatsAppSendError("GreenAPI is not configured")

    try:
        chat_id = to_whatsapp_chat_id(phone)
    except ValueError as exc:
        raise WhatsAppSendError("invalid phone number") from exc

    url = (
        f"{settings.greenapi_api_url.rstrip('/')}/waInstance{settings.greenapi_id_instance}"
        f"/sendMessage/{settings.greenapi_api_token}"
    )
    payload = {"chatId": chat_id, "message": message}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.exception("GreenAPI sendMessage failed")
        raise WhatsAppSendError("GreenAPI request failed") from exc

    if not data.get("idMessage"):
        raise WhatsAppSendError(str(data)[:200])
    return data
