from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.services.nedarim_client import NedarimApiError


async def test_job_requires_configured_token(client, monkeypatch):
    monkeypatch.setattr(settings, "sync_job_token", "")
    response = await client.post("/api/v1/jobs/achnasot-sync")
    assert response.status_code == 503


async def test_job_rejects_invalid_token(client, monkeypatch):
    monkeypatch.setattr(settings, "sync_job_token", "expected-token")
    response = await client.post(
        "/api/v1/jobs/achnasot-sync",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


async def test_job_requires_api_password(client, monkeypatch):
    monkeypatch.setattr(settings, "sync_job_token", "expected-token")
    monkeypatch.setattr(settings, "nedarim_api_password", "")
    response = await client.post(
        "/api/v1/jobs/achnasot-sync",
        headers={"Authorization": "Bearer expected-token"},
    )
    assert response.status_code == 503


async def test_job_bootstraps_without_sending(client, monkeypatch):
    monkeypatch.setattr(settings, "sync_job_token", "expected-token")
    monkeypatch.setattr(settings, "nedarim_api_password", "npk_test")
    with (
        patch(
            "app.services.achnasot_sync_service.get_achnasot_page",
            new_callable=AsyncMock,
            return_value=[{"ID": 9}],
        ),
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
        ) as sms,
    ):
        response = await client.post(
            "/api/v1/jobs/achnasot-sync",
            headers={"Authorization": "Bearer expected-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "bootstrapped", "last_id": 9, "fetched": 0, "sent": 0}
    sms.assert_not_awaited()


async def test_job_returns_502_when_nedarim_fails(client, monkeypatch):
    monkeypatch.setattr(settings, "sync_job_token", "expected-token")
    monkeypatch.setattr(settings, "nedarim_api_password", "npk_test")
    with patch(
        "app.services.achnasot_sync_service.get_achnasot_page",
        new_callable=AsyncMock,
        side_effect=NedarimApiError("NO DATA"),
    ):
        response = await client.post(
            "/api/v1/jobs/achnasot-sync",
            headers={"Authorization": "Bearer expected-token"},
        )

    assert response.status_code == 502
