"""Basic database read smoke test."""


def test_read_manual():
    from wechatauto import WeChatDB

    db = WeChatDB()
    info = db.get_self_info()
    assert info is not None
