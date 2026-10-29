import hashlib
import hmac
import json
import logging
import time
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import DonationReceipt


@pytest.fixture
def webhook_secret(monkeypatch):
    secret = "whsec_test_secret"
    monkeypatch.setattr(settings, "nedarim_webhook_secret", secret)
    monkeypatch.setattr(settings, "environment", "development")
    return secret


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"v1={digest}"


async def test_webhook_rejects_invalid_signature(client, webhook_secret):
    body = b'{"TransactionId":"100"}'
    response = await client.post(
        "/api/v1/webhooks/nedarim/transactions",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Nedarim-Timestamp": str(int(time.time())),
            "X-Nedarim-Signature": "v1=invalid",
        },
    )
    assert response.status_code == 401


async def test_webhook_persists_and_returns_webdocid(client, webhook_secret, db_session, caplog):
    caplog.set_level(logging.INFO)
    payload = {
        "TransactionId": "77462999",
        "ClientName": "אריה אלוני",
        "Phone": "0522514139",
        "Mail": "aloninet@gmail.com",
        "Amount": "100.00",
        "Currency": "1",
        "ReceiptCreated": "1",
        "ReceiptData": "87b66e12-ad15-4cb2-9f3f-c6a2a85478f2",
        "Groupe": "תרומה לבית הכנסת",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()))

    with patch(
        "app.api.v1.endpoints.transactions.process_donation_receipt_background",
        new_callable=AsyncMock,
    ) as background:
        response = await client.post(
            "/api/v1/webhooks/nedarim/transactions",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Nedarim-Timestamp": ts,
                "X-Nedarim-Signature": _sign(webhook_secret, ts, body),
            },
        )
        background.assert_called_once()

    assert response.status_code == 200
    data = response.json()
    assert "WEBDocID" in data
    assert isinstance(data["WEBDocID"], int)

    result = await db_session.execute(
        select(DonationReceipt).where(DonationReceipt.transaction_id == "77462999")
    )
    record = result.scalar_one()
    assert record.donor_phone == "0522514139"
    assert record.receipt_data == "87b66e12-ad15-4cb2-9f3f-c6a2a85478f2"
    assert record.receipt_url and "ezcount" in record.receipt_url
    assert record.status == "send_pending"
    assert record.web_doc_id == data["WEBDocID"]
    assert "0522514139" not in caplog.text
    assert "aloninet@gmail.com" not in caplog.text


async def test_webhook_idempotent_when_already_sent(client, webhook_secret, db_session):
    existing = DonationReceipt(
        transaction_id="999",
        donor_phone="0522514139",
        amount="10",
        receipt_url="https://example.com/r",
        status="sent",
        channel="sms",
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    payload = {
        "TransactionId": "999",
        "Phone": "0522514139",
        "Amount": "99",
        "ReceiptData": "https://example.com/other",
    }
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))

    with patch(
        "app.api.v1.endpoints.transactions.process_donation_receipt_background",
        new_callable=AsyncMock,
    ) as background:
        response = await client.post(
            "/api/v1/webhooks/nedarim/transactions",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Nedarim-Timestamp": ts,
                "X-Nedarim-Signature": _sign(webhook_secret, ts, body),
            },
        )
        background.assert_not_called()

    assert response.status_code == 200
    assert response.json()["WEBDocID"] == existing.web_doc_id
    await db_session.refresh(existing)
    assert existing.amount == "10"
    assert existing.receipt_url == "https://example.com/r"
    assert existing.status == "sent"


def _signed_headers(secret: str, body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    return {
        "Content-Type": "application/json",
        "X-Nedarim-Timestamp": ts,
        "X-Nedarim-Signature": _sign(secret, ts, body),
    }


async def test_webhook_without_phone_is_skipped(client, webhook_secret, db_session):
    body = json.dumps({"TransactionId": "77001", "ClientName": "ללא טלפון", "Amount": "18"}).encode()
    with patch(
        "app.api.v1.endpoints.transactions.process_donation_receipt_background",
        new_callable=AsyncMock,
    ) as background:
        response = await client.post(
            "/api/v1/webhooks/nedarim/transactions",
            content=body,
            headers=_signed_headers(webhook_secret, body),
        )
        background.assert_not_called()

    assert response.status_code == 200
    result = await db_session.execute(
        select(DonationReceipt).where(DonationReceipt.transaction_id == "77001")
    )
    record = result.scalar_one()
    assert record.status == "skipped_no_phone"
    assert record.donor_phone is None


async def test_webhook_requires_configured_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "nedarim_webhook_secret", "")
    response = await client.post(
        "/api/v1/webhooks/nedarim/transactions",
        content=b'{"TransactionId":"1"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 503


async def test_webhook_rejects_missing_headers(client, webhook_secret):
    response = await client.post(
        "/api/v1/webhooks/nedarim/transactions",
        content=b'{"TransactionId":"1"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401


async def test_webhook_rejects_tampered_body(client, webhook_secret):
    body = b'{"TransactionId":"42","Amount":"10"}'
    headers = _signed_headers(webhook_secret, body)
    tampered = b'{"TransactionId":"42","Amount":"11"}'
    response = await client.post(
        "/api/v1/webhooks/nedarim/transactions",
        content=tampered,
        headers=headers,
    )
    assert response.status_code == 401


async def test_webhook_rejects_json_array(client, webhook_secret):
    body = b"[1,2,3]"
    response = await client.post(
        "/api/v1/webhooks/nedarim/transactions",
        content=body,
        headers=_signed_headers(webhook_secret, body),
    )
    assert response.status_code == 400


async def test_webhook_rejects_invalid_json(client, webhook_secret):
    body = b"not-json"
    response = await client.post(
        "/api/v1/webhooks/nedarim/transactions",
        content=body,
        headers=_signed_headers(webhook_secret, body),
    )
    assert response.status_code == 400


async def test_webhook_rejects_missing_transaction_id(client, webhook_secret):
    body = b'{"Amount":"10"}'
    response = await client.post(
        "/api/v1/webhooks/nedarim/transactions",
        content=body,
        headers=_signed_headers(webhook_secret, body),
    )
    assert response.status_code == 400


async def test_webhook_rejects_mosad_mismatch(client, webhook_secret):
    body = json.dumps({"TransactionId": "50", "MosadNumber": "1111111"}).encode()
    response = await client.post(
        "/api/v1/webhooks/nedarim/transactions",
        content=body,
        headers=_signed_headers(webhook_secret, body),
    )
    assert response.status_code == 400


async def test_webhook_rejects_refusal_payload(client, webhook_secret):
    body = json.dumps({"Status": "Error", "Message": "סירוב", "TransactionId": "51"}).encode()
    response = await client.post(
        "/api/v1/webhooks/nedarim/transactions",
        content=body,
        headers=_signed_headers(webhook_secret, body),
    )
    assert response.status_code == 400


async def test_webhook_duplicate_updates_and_keeps_web_doc_id(client, webhook_secret, db_session):
    first = json.dumps(
        {"TransactionId": "88001", "Phone": "0522514139", "Amount": "18", "ReceiptData": ""}
    ).encode()
    second = json.dumps(
        {
            "TransactionId": "88001",
            "Phone": "0522514139",
            "Amount": "36",
            "ReceiptData": "https://files.ezcount.co.il/front/documents/get/doc-1",
        }
    ).encode()

    with patch(
        "app.api.v1.endpoints.transactions.process_donation_receipt_background",
        new_callable=AsyncMock,
    ):
        first_response = await client.post(
            "/api/v1/webhooks/nedarim/transactions",
            content=first,
            headers=_signed_headers(webhook_secret, first),
        )
        second_response = await client.post(
            "/api/v1/webhooks/nedarim/transactions",
            content=second,
            headers=_signed_headers(webhook_secret, second),
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["WEBDocID"] == second_response.json()["WEBDocID"]

    result = await db_session.execute(
        select(DonationReceipt).where(DonationReceipt.transaction_id == "88001")
    )
    record = result.scalar_one()
    assert record.amount == "36"
    assert record.receipt_url == "https://files.ezcount.co.il/front/documents/get/doc-1"
    assert record.status == "send_pending"

    count = await db_session.scalar(
        select(func.count()).select_from(DonationReceipt).where(DonationReceipt.transaction_id == "88001")
    )
    assert count == 1
