import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.services.messaging.shlink_client import ShortenError, shorten_url

LONG_URL = "https://files.ezcount.co.il/front/documents/get/abc"
SHORT_URL = "https://s.example.com/abcdefghij"


def _configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "shlink_base_url", "https://s.example.com")
    monkeypatch.setattr(settings, "shlink_api_key", "test-key")


def _client(response: MagicMock | None = None, error: Exception | None = None) -> AsyncMock:
    mock_client = AsyncMock()
    if error is not None:
        mock_client.post = AsyncMock(side_effect=error)
    else:
        mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


async def test_shorten_url_success(monkeypatch):
    _configured(monkeypatch)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"shortUrl": SHORT_URL, "shortCode": "abcdefghij"}
    mock_client = _client(mock_response)

    with patch(
        "app.services.messaging.shlink_client.httpx.AsyncClient",
        return_value=mock_client,
    ) as client_cls:
        result = await shorten_url(LONG_URL)

    assert result == SHORT_URL
    client_cls.assert_called_once_with(timeout=5.0)
    kwargs = mock_client.post.await_args.kwargs
    assert kwargs["headers"]["X-Api-Key"] == "test-key"
    assert kwargs["headers"]["Accept"] == "application/json"
    assert kwargs["json"] == {
        "longUrl": LONG_URL,
        "findIfExists": True,
        "tags": ["receipt"],
        "crawlable": False,
        "shortCodeLength": 10,
    }


@pytest.mark.parametrize(
    ("base_url", "api_key"),
    [("", "test-key"), ("https://s.example.com", ""), ("  ", "  ")],
)
async def test_shorten_url_skips_when_unconfigured(monkeypatch, base_url, api_key):
    monkeypatch.setattr(settings, "shlink_base_url", base_url)
    monkeypatch.setattr(settings, "shlink_api_key", api_key)

    with patch("app.services.messaging.shlink_client.httpx.AsyncClient") as client_cls:
        result = await shorten_url(LONG_URL)

    assert result == LONG_URL
    client_cls.assert_not_called()


async def test_shorten_url_http_error_hides_url_and_key(monkeypatch, caplog):
    _configured(monkeypatch)
    caplog.set_level(logging.WARNING)
    mock_client = _client(error=httpx.ConnectError("down"))

    with (
        patch("app.services.messaging.shlink_client.httpx.AsyncClient", return_value=mock_client),
        pytest.raises(ShortenError, match="Shlink request failed"),
    ):
        await shorten_url(LONG_URL)

    assert "test-key" not in caplog.text
    assert "ezcount" not in caplog.text
    assert LONG_URL not in caplog.text


@pytest.mark.parametrize(
    "long_url",
    [
        "https://evil.example/phish",
        "http://files.ezcount.co.il/front/documents/get/abc",
        "https://files.ezcount.co.il.evil.example/front/documents/get/abc",
        "https://user:pass@files.ezcount.co.il/front/documents/get/abc",
        "https://files.ezcount.co.il",
    ],
)
async def test_shorten_url_skips_non_ezcount_https_url(monkeypatch, long_url):
    _configured(monkeypatch)

    with patch("app.services.messaging.shlink_client.httpx.AsyncClient") as client_cls:
        result = await shorten_url(long_url)

    assert result == long_url
    client_cls.assert_not_called()
