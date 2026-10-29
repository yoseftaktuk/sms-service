from unittest.mock import AsyncMock, patch

from app.models import DonationReceipt
from app.services.donation_receipt_service import STATUS_FAILED, STATUS_SENT, DonationReceiptService
from app.services.messaging.sms_client import SmsSendError
from app.services.messaging.whatsapp_client import WhatsAppSendError


async def test_process_delivery_sms_success(db_session):
    record = DonationReceipt(
        transaction_id="555",
        donor_name="ישראל",
        donor_phone="0522514139",
        amount="50",
        receipt_url="https://files.ezcount.co.il/front/documents/get/abc",
        status="send_pending",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    service = DonationReceiptService(db_session)
    with patch(
        "app.services.donation_receipt_service.send_sms",
        new_callable=AsyncMock,
        return_value={"responseStatus": "OK", "oks": ["0522514139"]},
    ):
        await service.process_delivery(record.id)

    await db_session.refresh(record)
    assert record.status == STATUS_SENT
    assert record.channel == "sms"


async def test_process_delivery_falls_back_to_whatsapp(db_session):
    record = DonationReceipt(
        transaction_id="556",
        donor_phone="0522514139",
        receipt_url="https://files.ezcount.co.il/front/documents/get/abc",
        status="send_pending",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    service = DonationReceiptService(db_session)
    with (
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
            side_effect=SmsSendError("fail"),
        ),
        patch(
            "app.services.donation_receipt_service.send_whatsapp",
            new_callable=AsyncMock,
            return_value={"idMessage": "wa-1"},
        ),
    ):
        await service.process_delivery(record.id)

    await db_session.refresh(record)
    assert record.status == STATUS_SENT
    assert record.channel == "whatsapp"


async def test_process_delivery_both_channels_fail(db_session):
    record = DonationReceipt(
        transaction_id="557",
        donor_phone="0522514139",
        receipt_url="https://files.ezcount.co.il/front/documents/get/abc",
        status="send_pending",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    service = DonationReceiptService(db_session)
    with (
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
            side_effect=SmsSendError("sms fail"),
        ),
        patch(
            "app.services.donation_receipt_service.send_whatsapp",
            new_callable=AsyncMock,
            side_effect=WhatsAppSendError("wa fail"),
        ),
    ):
        await service.process_delivery(record.id)

    await db_session.refresh(record)
    assert record.status == STATUS_FAILED
    assert record.channel is None
    assert record.send_attempts == 1
    assert record.last_error == "wa fail"


async def test_process_delivery_show_invoice_then_sms(db_session):
    record = DonationReceipt(
        transaction_id="558",
        donor_name="ישראל",
        donor_phone="0522514139",
        amount="18",
        status="receipt_pending",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    receipt_url = "https://files.ezcount.co.il/front/documents/get/from-invoice"
    service = DonationReceiptService(db_session)
    with (
        patch(
            "app.services.donation_receipt_service.show_invoice",
            new_callable=AsyncMock,
            return_value=receipt_url,
        ) as show,
        patch(
            "app.services.donation_receipt_service.send_sms",
            new_callable=AsyncMock,
            return_value={"responseStatus": "OK", "oks": ["0522514139"]},
        ) as sms,
    ):
        await service.process_delivery(record.id)

    show.assert_awaited_once_with("558")
    sms.assert_awaited_once()
    await db_session.refresh(record)
    assert record.receipt_url == receipt_url
    assert record.status == STATUS_SENT
    assert record.channel == "sms"
