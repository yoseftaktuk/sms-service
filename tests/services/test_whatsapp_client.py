from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.messaging.whatsapp_client import WhatsAppSendError, send_whatsapp


async def test_send_whatsapp_requires_config(monkeypatch):
    monkeypatch.setattr(settings, "greenapi_id_instance", "")
    monkeypatch.setattr(settings, "greenapi_api_token", "")
    with pytest.raises(WhatsAppSendError, match="not configured"):
        await send_whatsapp(phone="0522514139", message="hi")


async def test_send_whatsapp_success(monkeypatch):
    monkeypatch.setattr(settings, "greenapi_id_instance", "123")
    monkeypatch.setattr(settings, "greenapi_api_token", "tok")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"idMessage": "abc"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.messaging.whatsapp_client.httpx.AsyncClient", return_value=mock_client):
        data = await send_whatsapp(phone="0522514139", message="קבלה")

    assert data["idMessage"] == "abc"
