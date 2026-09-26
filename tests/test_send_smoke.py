"""Basic send smoke test.

Run manually on Windows with WeChat logged in.
"""


def test_send_manual():
    from wechatauto.guia import quick_send

    result = quick_send(
        "Qlawork upstream validation test",
        "文件传输助手",
        verify=True,
    )
    assert result is not False
