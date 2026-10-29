"""Normalize Israeli phone numbers for SMS / WhatsApp providers."""

from __future__ import annotations

import re

_DIGITS = re.compile(r"\D+")


def normalize_israeli_phone(raw: str | None) -> str | None:
    """Return a local Israeli mobile number (05XXXXXXXX) or None if invalid."""
    if not raw:
        return None

    digits = _DIGITS.sub("", raw)
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    elif digits.startswith("00972"):
        digits = "0" + digits[5:]

    if len(digits) == 9 and digits.startswith("5"):
        digits = "0" + digits

    if len(digits) != 10 or not digits.startswith("05"):
        return None
    return digits


def to_whatsapp_chat_id(phone: str) -> str:
    """GreenAPI expects international digits without plus, e.g. 9725..."""
    local = normalize_israeli_phone(phone)
    if not local:
        raise ValueError("invalid phone")
    return f"972{local[1:]}@c.us"
