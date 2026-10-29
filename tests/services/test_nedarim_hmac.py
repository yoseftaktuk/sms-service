import hashlib
import hmac
import time

from app.services.nedarim_hmac import verify_nedarim_signature


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"v1={digest}"


def test_verify_nedarim_signature_ok():
    secret = "whsec_test"
    body = b'{"TransactionId":"1"}'
    ts = str(int(time.time()))
    assert verify_nedarim_signature(
        timestamp=ts,
        signature_header=_sign(secret, ts, body),
        raw_body=body,
        secret=secret,
        now=float(ts),
    )


def test_verify_nedarim_signature_rejects_bad_sig():
    secret = "whsec_test"
    body = b'{"TransactionId":"1"}'
    ts = str(int(time.time()))
    assert not verify_nedarim_signature(
        timestamp=ts,
        signature_header="v1=deadbeef",
        raw_body=body,
        secret=secret,
        now=float(ts),
    )


def test_verify_nedarim_signature_known_vector():
    body = b'{"TransactionId":"1"}'
    assert verify_nedarim_signature(
        timestamp="1700000000",
        signature_header="v1=2F004E9518460EB5F53AAA9BE0B41E6099DACD70CD42CAE217619B49655D0AF0",
        raw_body=body,
        secret="whsec_test",
        now=1700000000,
    )


def test_verify_nedarim_signature_rejects_non_numeric_timestamp():
    assert not verify_nedarim_signature(
        timestamp="not-a-time",
        signature_header="v1=abc",
        raw_body=b"{}",
        secret="whsec_test",
        now=1700000000,
    )


def test_verify_nedarim_signature_rejects_empty_signature_value():
    assert not verify_nedarim_signature(
        timestamp="1700000000",
        signature_header="v1=",
        raw_body=b"{}",
        secret="whsec_test",
        now=1700000000,
    )


def test_verify_nedarim_signature_rejects_empty_secret():
    body = b"{}"
    assert not verify_nedarim_signature(
        timestamp="1700000000",
        signature_header="v1=abc",
        raw_body=body,
        secret="",
        now=1700000000,
    )


def test_verify_nedarim_signature_rejects_skew():
    secret = "whsec_test"
    body = b"{}"
    ts = str(int(time.time()) - 10_000)
    assert not verify_nedarim_signature(
        timestamp=ts,
        signature_header=_sign(secret, ts, body),
        raw_body=body,
        secret=secret,
        max_skew_seconds=300,
        now=time.time(),
    )
