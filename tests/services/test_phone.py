from app.services.messaging.phone import normalize_israeli_phone, to_whatsapp_chat_id


def test_normalize_local_mobile():
    assert normalize_israeli_phone("052-251-4139") == "0522514139"


def test_normalize_international():
    assert normalize_israeli_phone("+972522514139") == "0522514139"


def test_normalize_invalid():
    assert normalize_israeli_phone("123") is None
    assert normalize_israeli_phone(None) is None


def test_whatsapp_chat_id():
    assert to_whatsapp_chat_id("0522514139") == "972522514139@c.us"
