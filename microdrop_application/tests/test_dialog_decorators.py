"""Tests for microdrop_application.dialogs.decorators —
attempt_func_execution_with_error_dialog (the styled error-dialog
wrapper for top-level user-triggered UI actions)."""

import logging

import microdrop_application.dialogs.decorators as _dec

LOGGER_NAME = "microdrop_application.dialogs.decorators"


def test_attempt_func_execution_returns_wrapped_value_on_success():
    """Successful call passes through the wrapped function's return value
    with no dialog."""
    calls = []
    dec_error = _dec.error

    class _Fake:
        @_dec.attempt_func_execution_with_error_dialog
        def do(self, x, y):
            return x + y

    f = _Fake()
    # Sanity: the dialog is NOT invoked on success. Replace it with a
    # tripwire that fails the test if called.
    try:
        _dec.error = lambda *a, **k: calls.append("BUG: dialog called on success")
        assert f.do(2, 3) == 5
    finally:
        _dec.error = dec_error
    assert calls == []


def test_attempt_func_execution_shows_html_dialog_and_logs_on_exception(
    monkeypatch, caplog):
    """Exception path: dialog gets HTML informative + traceback detail,
    logger captures the stack, and the wrapper returns None instead of
    propagating."""
    captured = {}

    def _fake_error(parent, *, message, title, informative=None, detail=None,
                    **kw):
        captured["parent"] = parent
        captured["message"] = message
        captured["title"] = title
        captured["informative"] = informative
        captured["detail"] = detail

    monkeypatch.setattr(_dec, "error", _fake_error)
    caplog.set_level(logging.ERROR, logger=LOGGER_NAME)

    class _Fake:
        @_dec.attempt_func_execution_with_error_dialog
        def save_protocol_dialog(self):
            raise ValueError("disk full")

    result = _Fake().save_protocol_dialog()
    assert result is None
    # Message + title use the humanised operation name and the exception
    # type — both readable to a user.
    assert captured["title"] == "Save Protocol Dialog Error"
    assert "Save Protocol Dialog" in captured["message"]
    assert "ValueError" in captured["message"]
    # Informative is HTML, bold name, red exception type, escaped cause.
    assert "<b>Save Protocol Dialog</b>" in captured["informative"]
    assert "ValueError" in captured["informative"]
    assert "disk full" in captured["informative"]
    # Detail contains the full traceback (multi-line, includes "Traceback").
    assert "Traceback" in captured["detail"]
    assert "ValueError: disk full" in captured["detail"]
    # Logger captured it too, with exc_info.
    assert any(
        "Save Protocol Dialog failed" in r.message and r.exc_info
        for r in caplog.records)


def test_attempt_func_execution_handles_dialog_failure_gracefully(
    monkeypatch, caplog):
    """If the dialog itself raises (e.g. no Qt event loop), we log it
    but the wrapper does NOT propagate — original exception was already
    logged so the caller can carry on."""
    def _broken_error(*a, **k):
        raise RuntimeError("no event loop")

    monkeypatch.setattr(_dec, "error", _broken_error)
    caplog.set_level(logging.ERROR, logger=LOGGER_NAME)

    class _Fake:
        @_dec.attempt_func_execution_with_error_dialog
        def do(self):
            raise IOError("boom")

    # No exception propagates.
    assert _Fake().do() is None
    # Both the original error AND the dialog failure were logged.
    messages = " | ".join(r.message for r in caplog.records)
    assert "Do failed: boom" in messages
    assert "failed to show error dialog" in messages


def test_attempt_func_execution_html_escapes_exception_message(monkeypatch):
    """Exception message containing HTML special chars must be escaped
    so the dialog renders it as text, not markup."""
    captured = {}
    monkeypatch.setattr(_dec, "error",
                        lambda parent, **k: captured.update(k))

    class _Fake:
        @_dec.attempt_func_execution_with_error_dialog
        def do(self):
            raise RuntimeError("<script>alert('x')</script>")

    _Fake().do()
    # The raw script tag must NOT appear; escaped form must.
    assert "<script>" not in captured["informative"]
    assert "&lt;script&gt;" in captured["informative"]
