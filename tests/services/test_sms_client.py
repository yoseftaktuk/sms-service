from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.messaging.sms_client import SmsSendError, send_sms


async def test_send_sms_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "yemot_api_key", "")
    with pytest.raises(SmsSendError, match="not configured"):
        await send_sms(phone="0522514139", message="hi")


async def test_send_sms_success(monkeypatch):
    monkeypatch.setattr(settings, "yemot_api_key", "test-key")
    monkeypatch.setattr(settings, "yemot_sms_from", "Poaley")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "responseStatus": "OK",
        "oks": ["0522514139"],
        "Billing": 0.2,
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.messaging.sms_client.httpx.AsyncClient", return_value=mock_client):
        data = await send_sms(phone="0522514139", message="קבלה")

    assert data["responseStatus"] == "OK"
    mock_client.get.assert_awaited()
    kwargs = mock_client.get.await_args.kwargs
    assert kwargs["headers"]["Authorization"] == "test-key"
    assert kwargs["params"]["phones"] == "0522514139"
    assert kwargs["params"]["from"] == "Poaley"
