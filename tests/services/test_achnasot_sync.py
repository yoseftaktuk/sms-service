from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from app.models import DonationReceipt, SyncCursor
from app.services.achnasot_sync_service import CURSOR_KEY, AchnasotSyncService
from app.services.nedarim_client import NedarimApiError

RECEIPT_URL = "https://files.ezcount.co.il/front/documents/get/abc"


def _income(income_id: int = 41, **overrides) -> dict:
    data = {
        "ID": income_id,
        "Date": "11/11/2026",
        "EntryTime": "11/11/2026 10:00",
        "Amount": "50.00",
        "Currency": "1",
        "ClientName": "ישראל ישראלי",
        "Phone": "0522514139",
        "Mail": "a@example.com",
        "HasKabala": "1",
        "Groupe": "מזומן",
    }
    data.update(overrides)
    return data


async def _seed_cursor(db_session, last_id: int) -> None:
    db_session.add(SyncCursor(key=CURSOR_KEY, last_id=last_id))
    await db_session.commit()


async def _cursor_id(db_session) -> int | None:
    result = await db_session.execute(select(SyncCursor).where(SyncCursor.key == CURSOR_KEY))
    cursor = result.scalar_one_or_none()
    if cursor is None:
        return None
    return cursor.last_id


async def _receipt(db_session, income_id: int) -> DonationReceipt | None:
    result = await db_session.execute(
        select(DonationReceipt).where(DonationReceipt.achnasot_id == income_id)
    )
    return result.scalar_one_or_none()


async def test_bootstrap_saves_cursor_and_does_not_send(db_session):
    service = AchnasotSyncService(db_session)
    with (
        patch(
            "app.services.achnasot_sync_service.get_achnasot_page",
            new_callable=AsyncMock,
            return_value=[_income(40)],
        ) as page,
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
        ) as sms,
    ):
        result = await service.sync()

    page.assert_awaited_once_with(max_id=1, order="Desc")
    sms.assert_not_awaited()
    assert result == {"status": "bootstrapped", "last_id": 40, "fetched": 0, "sent": 0}
    assert await _cursor_id(db_session) == 40
    count = await db_session.execute(select(func.count()).select_from(DonationReceipt))
    assert count.scalar_one() == 0


async def test_new_income_with_receipt_is_sent_once(db_session):
    await _seed_cursor(db_session, 40)
    pages = {
        40: [_income(41)],
    }

    async def fake_page(*, last_id=None, max_id=200, order="Asc"):
        return pages.get(last_id, [])

    service = AchnasotSyncService(db_session)
    with (
        patch(
            "app.services.achnasot_sync_service.get_achnasot_page",
            new=fake_page,
        ),
        patch(
            "app.services.donation_receipt_service.show_invoice",
            new_callable=AsyncMock,
            return_value=RECEIPT_URL,
        ) as show,
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
            return_value={"responseStatus": "OK"},
        ) as sms,
    ):
        first = await service.sync()
        second = await service.sync()

    assert first["status"] == "ok"
    assert first["last_id"] == 41
    assert first["fetched"] == 1
    assert first["sent"] == 1
    assert second["fetched"] == 0
    assert second["sent"] == 0
    show.assert_awaited_once_with(achnasot_id="41")
    sms.assert_awaited_once()
    message = sms.await_args.kwargs["message"]
    assert "ישראל ישראלי" in message
    assert "50.00 ₪" in message
    assert RECEIPT_URL in message
    record = await _receipt(db_session, 41)
    assert record is not None
    assert record.status == "sent"
    assert record.transaction_id == "achnasot:41"
    assert record.source == "achnasot"


async def test_already_sent_income_is_not_sent_again(db_session):
    await _seed_cursor(db_session, 40)
    db_session.add(
        DonationReceipt(
            transaction_id="achnasot:41",
            source="achnasot",
            achnasot_id=41,
            status="sent",
            donor_phone="0522514139",
            receipt_url=RECEIPT_URL,
        )
    )
    await db_session.commit()

    service = AchnasotSyncService(db_session)
    with (
        patch(
            "app.services.achnasot_sync_service.get_achnasot_page",
            new_callable=AsyncMock,
            return_value=[_income(41)],
        ),
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
        ) as sms,
    ):
        result = await service.sync()

    sms.assert_not_awaited()
    assert result["sent"] == 0
    assert result["last_id"] == 41
    record = await _receipt(db_session, 41)
    assert record is not None
    assert record.status == "sent"


async def test_receipt_issued_later_is_sent_on_the_next_run(db_session):
    await _seed_cursor(db_session, 40)
    pages = [[_income(41, HasKabala="0")], []]

    async def fake_page(*, last_id=None, max_id=200, order="Asc"):
        if pages:
            return pages.pop(0)
        return []

    service = AchnasotSyncService(db_session)
    with (
        patch("app.services.achnasot_sync_service.get_achnasot_page", new=fake_page),
        patch(
            "app.services.donation_receipt_service.show_invoice",
            new_callable=AsyncMock,
            return_value=RECEIPT_URL,
        ) as show,
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
            return_value={"responseStatus": "OK"},
        ) as sms,
    ):
        first = await service.sync()
        assert first["sent"] == 0
        record = await _receipt(db_session, 41)
        assert record is not None
        assert record.status == "receipt_pending"
        show.assert_not_awaited()
        sms.assert_not_awaited()

        second = await service.sync()

    assert second["sent"] == 1
    show.assert_awaited_once_with(achnasot_id="41")
    sms.assert_awaited_once()
    record = await _receipt(db_session, 41)
    assert record is not None
    assert record.status == "sent"


async def test_income_without_phone_is_skipped(db_session):
    await _seed_cursor(db_session, 40)
    service = AchnasotSyncService(db_session)
    with (
        patch(
            "app.services.achnasot_sync_service.get_achnasot_page",
            new_callable=AsyncMock,
            return_value=[_income(41, Phone="")],
        ),
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
        ) as sms,
    ):
        first = await service.sync()
        second = await service.sync()

    sms.assert_not_awaited()
    assert first["sent"] == 0
    assert second["sent"] == 0
    record = await _receipt(db_session, 41)
    assert record is not None
    assert record.status == "skipped_no_phone"


async def test_dollar_currency_uses_dollar_symbol(db_session):
    await _seed_cursor(db_session, 40)
    service = AchnasotSyncService(db_session)
    with (
        patch(
            "app.services.achnasot_sync_service.get_achnasot_page",
            new_callable=AsyncMock,
            return_value=[_income(41, Currency="2", Amount="10")],
        ),
        patch(
            "app.services.donation_receipt_service.show_invoice",
            new_callable=AsyncMock,
            return_value=RECEIPT_URL,
        ),
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
            return_value={"responseStatus": "OK"},
        ) as sms,
    ):
        await service.sync()

    message = sms.await_args.kwargs["message"]
    assert "10 $" in message
    assert "₪" not in message


async def test_failed_send_is_retried_next_run(db_session):
    await _seed_cursor(db_session, 50)
    db_session.add(
        DonationReceipt(
            transaction_id="achnasot:8",
            source="achnasot",
            achnasot_id=8,
            status="failed",
            donor_name="דנה",
            donor_phone="0522514139",
            amount="10",
            currency="1",
            receipt_url=RECEIPT_URL,
        )
    )
    await db_session.commit()

    service = AchnasotSyncService(db_session)
    with (
        patch(
            "app.services.achnasot_sync_service.get_achnasot_page",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.donation_receipt_service.show_invoice",
            new_callable=AsyncMock,
        ) as show,
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
            return_value={"responseStatus": "OK"},
        ) as sms,
    ):
        result = await service.sync()

    show.assert_not_awaited()
    sms.assert_awaited_once()
    assert result["sent"] == 1
    record = await _receipt(db_session, 8)
    assert record is not None
    assert record.status == "sent"


async def test_pending_receipt_expires_after_30_days(db_session):
    await _seed_cursor(db_session, 10)
    db_session.add(
        DonationReceipt(
            transaction_id="achnasot:3",
            source="achnasot",
            achnasot_id=3,
            status="receipt_pending",
            donor_phone="0522514139",
            created_at=datetime.now(UTC) - timedelta(days=31),
        )
    )
    await db_session.commit()

    service = AchnasotSyncService(db_session)
    with (
        patch(
            "app.services.achnasot_sync_service.get_achnasot_page",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.donation_receipt_service.show_invoice",
            new_callable=AsyncMock,
        ) as show,
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
        ) as sms,
    ):
        await service.sync()

    show.assert_not_awaited()
    sms.assert_not_awaited()
    record = await _receipt(db_session, 3)
    assert record is not None
    assert record.status == "skipped_no_receipt"


async def test_rate_limit_does_not_move_cursor(db_session):
    await _seed_cursor(db_session, 5)
    service = AchnasotSyncService(db_session)
    with patch(
        "app.services.achnasot_sync_service.get_achnasot_page",
        new_callable=AsyncMock,
        side_effect=NedarimApiError("TOO MANY REQUESTS", rate_limited=True),
    ):
        result = await service.sync()

    assert result["status"] == "rate_limited"
    assert result["last_id"] == 5
    assert await _cursor_id(db_session) == 5


async def test_full_page_continues_from_the_highest_id(db_session, monkeypatch):
    monkeypatch.setattr("app.services.achnasot_sync_service.PAGE_SIZE", 2)
    await _seed_cursor(db_session, 10)
    calls: list[int | None] = []

    async def fake_page(*, last_id=None, max_id=200, order="Asc"):
        calls.append(last_id)
        if last_id == 10:
            return [_income(11, HasKabala="0"), _income(12, HasKabala="0")]
        return []

    service = AchnasotSyncService(db_session)
    with (
        patch("app.services.achnasot_sync_service.get_achnasot_page", new=fake_page),
        patch("app.services.donation_receipt_service.send_sms", new_callable=AsyncMock) as sms,
    ):
        result = await service.sync()

    assert calls == [10, 12]
    assert result["fetched"] == 2
    assert result["last_id"] == 12
    assert result["sent"] == 0
    sms.assert_not_awaited()
