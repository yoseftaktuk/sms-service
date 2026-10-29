"""Verify Nedarim Plus webhook HMAC signatures."""

from __future__ import annotations

import hashlib
import hmac
import time


def diagnose_nedarim_signature(
    *,
    timestamp: str | None,
    signature_header: str | None,
    raw_body: bytes,
    secret: str,
    max_skew_seconds: int = 300,
    now: float | None = None,
) -> dict[str, object]:
    """Explain a failed check without including the secret, signature, or body."""
    secret_stripped = secret.strip()
    provided = (signature_header or "").strip().removeprefix("v1=").strip().lower()
    info: dict[str, object] = {
        "reason": "ok",
        "timestamp_present": bool(timestamp),
        "timestamp_len": len(timestamp) if timestamp else 0,
        "signature_present": bool(signature_header),
        "signature_len": len(provided),
        "body_len": len(raw_body),
        "body_is_json_object": raw_body.lstrip().startswith(b"{"),
        "secret_len": len(secret),
        "secret_edge_whitespace": secret != secret_stripped,
    }
    if not secret:
        info["reason"] = "missing_secret"
        return info
    if not timestamp:
        info["reason"] = "missing_timestamp"
        return info
    if not signature_header:
        info["reason"] = "missing_signature"
        return info
    try:
        ts = int(timestamp.strip())
    except ValueError:
        info["reason"] = "timestamp_not_int"
        return info
    current = time.time() if now is None else now
    info["skew_seconds"] = int(abs(current - ts))
    if abs(current - ts) > max_skew_seconds:
        info["reason"] = "timestamp_skew"
        return info
    if not provided:
        info["reason"] = "empty_signature"
        return info
    message = f"{timestamp}.".encode("utf-8") + raw_body
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if len(provided) != len(expected):
        info["reason"] = "signature_length"
        return info
    if hmac.compare_digest(expected, provided):
        return info
    info["reason"] = "signature_mismatch"
    if secret != secret_stripped:
        stripped_expected = hmac.new(secret_stripped.encode("utf-8"), message, hashlib.sha256).hexdigest()
        info["stripped_secret_matches"] = hmac.compare_digest(stripped_expected, provided)
    return info


def verify_nedarim_signature(
    *,
    timestamp: str | None,
    signature_header: str | None,
    raw_body: bytes,
    secret: str,
    max_skew_seconds: int = 300,
    now: float | None = None,
) -> bool:
    """Return True when X-Nedarim-* headers match HMAC-SHA256(timestamp + '.' + body)."""
    return (
        diagnose_nedarim_signature(
            timestamp=timestamp,
            signature_header=signature_header,
            raw_body=raw_body,
            secret=secret,
            max_skew_seconds=max_skew_seconds,
            now=now,
        )["reason"]
        == "ok"
    )
