from app.services.nedarim_client import ezcount_url, is_uuid, resolve_receipt_url_from_webhook


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
