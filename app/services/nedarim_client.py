"""Nedarim Plus receipt lookup and external-income sync."""

from __future__ import annotations

import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

EZCOUNT_RECEIPT_BASE = "https://files.ezcount.co.il/front/documents/get"
TAMAL_URL = "https://matara.pro/nedarimplus/Reports/Tamal3.aspx"
MANAGE_URL = "https://matara.pro/nedarimplus/Reports/Manage3.aspx"
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class NedarimApiError(Exception):
    """Nedarim returned an error object, or the client could not call the API."""

    def __init__(self, message: str, *, rate_limited: bool = False) -> None:
        super().__init__(message)
        self.rate_limited = rate_limited


def is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip()))


def ezcount_url(document_id: str) -> str:
    return f"{EZCOUNT_RECEIPT_BASE}/{document_id.strip()}"


def resolve_receipt_url_from_webhook(
    *,
    receipt_data: str | None,
    receipt_created: str | None,
) -> str | None:
    """Resolve a receipt URL from webhook fields without calling Nedarim."""
    raw = (receipt_data or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if is_uuid(raw):
        return ezcount_url(raw)

    created = (receipt_created or "").strip().lower()
    if created in {"1", "true", "yes"} and raw:
        return ezcount_url(raw)
    return None


async def show_invoice(
    transaction_id: str | None = None,
    *,
    achnasot_id: str | None = None,
) -> str | None:
    """Call ShowInvoice; return the receipt URL from Message when Result=OK.

    Credit-card webhooks pass transaction_id. External incomes pass achnasot_id.
    Exactly one identifier is sent.
    """
    has_transaction = bool(transaction_id and str(transaction_id).strip())
    has_achnasot = bool(achnasot_id and str(achnasot_id).strip())
    if has_transaction == has_achnasot:
        raise ValueError("Provide exactly one of transaction_id or achnasot_id")

    if not settings.nedarim_api_password:
        logger.warning("Nedarim API password not configured; skipping ShowInvoice")
        return None

    params = {
        "Action": "ShowInvoice",
        "MosadId": settings.nedarim_mosad_id,
        "ApiPassword": settings.nedarim_api_password,
    }
    if has_transaction:
        params["TransactionId"] = str(transaction_id).strip()
        log_id = params["TransactionId"]
    else:
        params["AchnasotId"] = str(achnasot_id).strip()
        log_id = params["AchnasotId"]

    try:
        data = await _get_json(TAMAL_URL, params)
    except Exception:
        logger.exception("ShowInvoice failed for id=%s", log_id)
        return None

    if not isinstance(data, dict) or data.get("Result") != "OK":
        message = data.get("Message") if isinstance(data, dict) else ""
        logger.info("ShowInvoice not OK for id=%s message=%s", log_id, str(message)[:120])
        return None

    message = str(data.get("Message") or "").strip()
    if message.startswith("http"):
        return message
    return None


async def get_achnasot_page(
    *,
    last_id: int | None = None,
    max_id: int = 200,
    order: str = "Asc",
) -> list[dict]:
    """Return one page of external incomes.

    An empty list means there are no further rows. Rate limits and other Nedarim
    error objects raise NedarimApiError and do not look like an empty page.
    """
    if not settings.nedarim_api_password:
        raise NedarimApiError("Nedarim API password not configured")

    params: dict[str, str] = {
        "Action": "GetAchnasotJson",
        "MosadId": str(settings.nedarim_mosad_id),
        "ApiPassword": settings.nedarim_api_password,
        "MaxId": str(max_id),
        "Order": order,
    }
    if last_id is not None:
        params["LastId"] = str(last_id)

    try:
        data = await _get_json(MANAGE_URL, params, timeout=30.0)
    except Exception as exc:
        logger.exception("GetAchnasotJson failed")
        raise NedarimApiError("GetAchnasotJson request failed") from exc

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        message = str(data.get("Message") or "").strip()
        if "TOO MANY REQUESTS" in message.upper():
            raise NedarimApiError(message or "TOO MANY REQUESTS", rate_limited=True)
        raise NedarimApiError(message or "unexpected GetAchnasotJson response")

    raise NedarimApiError("unexpected GetAchnasotJson response")


async def _get_json(url: str, params: dict[str, str], *, timeout: float = 20.0) -> object:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
