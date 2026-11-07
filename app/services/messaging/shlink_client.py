"""Shlink client that shortens Ezcount receipt links."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

EZCOUNT_RECEIPT_HOST = "files.ezcount.co.il"
SHORT_CODE_LENGTH = 10
_TIMEOUT_SECONDS = 5.0


class ShortenError(Exception):
    """Raised when Shlink rejects or fails a shorten request."""


def is_ezcount_receipt_url(url: str) -> bool:
    """True for an https Ezcount document URL with no embedded credentials."""
    parsed = urlparse(url.strip())
    path = parsed.path or ""
    return (
        parsed.scheme == "https"
        and parsed.hostname == EZCOUNT_RECEIPT_HOST
        and parsed.username is None
        and parsed.password is None
        and parsed.port in {None, 443}
        and path not in {"", "/"}
    )


async def shorten_url(long_url: str) -> str:
    """Return a Shlink short URL, or the original URL when shortening does not apply.

    Missing configuration and non-Ezcount URLs skip the HTTP call. Request failures
    raise ShortenError with a message that contains neither the API key nor the URL.
    """
    if not settings.shlink_base_url.strip() or not settings.shlink_api_key.strip():
        return long_url
    if not is_ezcount_receipt_url(long_url):
        return long_url

    endpoint = f"{settings.shlink_base_url.rstrip('/')}/rest/v3/short-urls"
    payload = {
        "longUrl": long_url,
        "findIfExists": True,
        "tags": ["receipt"],
        "crawlable": False,
        "shortCodeLength": SHORT_CODE_LENGTH,
    }
    headers = {
        "X-Api-Key": settings.shlink_api_key,
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.warning("Shlink shorten request failed")
        raise ShortenError("Shlink request failed") from None

    short_url = data.get("shortUrl") if isinstance(data, dict) else None
    if not isinstance(short_url, str) or not short_url.startswith("https://"):
        logger.warning("Shlink shorten response missing shortUrl")
        raise ShortenError("Shlink response missing shortUrl")
    return short_url
