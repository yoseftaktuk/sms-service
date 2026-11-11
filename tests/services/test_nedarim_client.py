from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.nedarim_client import (
    MANAGE_URL,
    TAMAL_URL,
    NedarimApiError,
    ezcount_url,
    get_achnasot_page,
    is_uuid,
    resolve_receipt_url_from_webhook,
    show_invoice,
)


def test_is_uuid():
    assert is_uuid("87b66e12-ad15-4cb2-9f3f-c6a2a85478f2")
    assert not is_uuid("not-a-uuid")


def test_resolve_http_receipt_data():
    url = "https://files.ezcount.co.il/front/documents/get/abc"
    assert resolve_receipt_url_from_webhook(receipt_data=url, receipt_created="1") == url


def test_resolve_uuid_receipt_data():
    uid = "87b66e12-ad15-4cb2-9f3f-c6a2a85478f2"
    assert resolve_receipt_url_from_webhook(receipt_data=uid, receipt_created="1") == ezcount_url(uid)


def test_resolve_non_uuid_when_receipt_created():
    assert resolve_receipt_url_from_webhook(receipt_data="doc-99", receipt_created="1") == ezcount_url(
        "doc-99"
    )


def test_resolve_non_uuid_without_receipt_created():
    assert resolve_receipt_url_from_webhook(receipt_data="doc-99", receipt_created="0") is None


def test_resolve_empty():
    assert resolve_receipt_url_from_webhook(receipt_data="", receipt_created="0") is None


def _http_client(payload):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


async def test_show_invoice_uses_transaction_id(monkeypatch):
    monkeypatch.setattr(settings, "nedarim_api_password", "npk_test")
    client = _http_client({"Result": "OK", "Message": "https://files.ezcount.co.il/r/1"})
    with patch("app.services.nedarim_client.httpx.AsyncClient", return_value=client):
        url = await show_invoice("55")

    assert url == "https://files.ezcount.co.il/r/1"
    params = client.get.await_args.kwargs["params"]
    assert client.get.await_args.args[0] == TAMAL_URL
    assert params["TransactionId"] == "55"
    assert "AchnasotId" not in params


async def test_show_invoice_uses_achnasot_id(monkeypatch):
    monkeypatch.setattr(settings, "nedarim_api_password", "npk_test")
    client = _http_client({"Result": "OK", "Message": "https://files.ezcount.co.il/r/2"})
    with patch("app.services.nedarim_client.httpx.AsyncClient", return_value=client):
        url = await show_invoice(achnasot_id="88")

    assert url == "https://files.ezcount.co.il/r/2"
    params = client.get.await_args.kwargs["params"]
    assert params["AchnasotId"] == "88"
    assert "TransactionId" not in params


async def test_show_invoice_requires_one_identifier():
    with pytest.raises(ValueError):
        await show_invoice()
    with pytest.raises(ValueError):
        await show_invoice("55", achnasot_id="88")


async def test_get_achnasot_page_sends_last_id(monkeypatch):
    monkeypatch.setattr(settings, "nedarim_api_password", "npk_test")
    client = _http_client([{"ID": 12, "Phone": "0522514139"}])
    with patch("app.services.nedarim_client.httpx.AsyncClient", return_value=client):
        rows = await get_achnasot_page(last_id=10, max_id=200, order="Asc")

    assert rows == [{"ID": 12, "Phone": "0522514139"}]
    params = client.get.await_args.kwargs["params"]
    assert client.get.await_args.args[0] == MANAGE_URL
    assert params["Action"] == "GetAchnasotJson"
    assert params["LastId"] == "10"
    assert params["MaxId"] == "200"
    assert params["Order"] == "Asc"
    assert params["ApiPassword"] == "npk_test"


async def test_get_achnasot_page_omits_last_id_when_missing(monkeypatch):
    monkeypatch.setattr(settings, "nedarim_api_password", "npk_test")
    client = _http_client([])
    with patch("app.services.nedarim_client.httpx.AsyncClient", return_value=client):
        rows = await get_achnasot_page(max_id=1, order="Desc")

    assert rows == []
    assert "LastId" not in client.get.await_args.kwargs["params"]
    assert client.get.await_args.kwargs["params"]["Order"] == "Desc"


async def test_get_achnasot_page_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "nedarim_api_password", "npk_test")
    client = _http_client({"Result": "Error", "Message": "TOO MANY REQUESTS"})
    with patch("app.services.nedarim_client.httpx.AsyncClient", return_value=client):
        with pytest.raises(NedarimApiError) as exc_info:
            await get_achnasot_page(last_id=1)

    assert exc_info.value.rate_limited is True


async def test_get_achnasot_page_error_is_not_an_empty_page(monkeypatch):
    monkeypatch.setattr(settings, "nedarim_api_password", "npk_test")
    client = _http_client({"Result": "Error", "Message": "NO DATA"})
    with patch("app.services.nedarim_client.httpx.AsyncClient", return_value=client):
        with pytest.raises(NedarimApiError) as exc_info:
            await get_achnasot_page(last_id=1)

    assert exc_info.value.rate_limited is False


async def test_get_achnasot_page_requires_password(monkeypatch):
    monkeypatch.setattr(settings, "nedarim_api_password", "")
    with pytest.raises(NedarimApiError):
        await get_achnasot_page(last_id=1)
