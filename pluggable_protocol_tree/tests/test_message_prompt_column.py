"""Tests for the message-prompt column handler's guard logic.

These cover the two paths that don't touch Qt — the empty-message no-op
and the already-stopped abort — so they run headless without a running
event loop. The dialog path itself (QTimer.singleShot -> information()
-> event set -> ctx.wait returns) needs a Qt application and is exercised
by the StepContext.wait tests in test_step_context.py plus manual/demo
runs of run_widget.py.
"""

import threading
import types

import pytest

from pluggable_protocol_tree.builtins.message_prompt_column import (
    MsgPromptColumnHandler, make_message_prompt_column,
)
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.exceptions import AbortError
from pluggable_protocol_tree.execution.step_context import ProtocolContext


class _FakeCtx:
    """Minimal ctx exposing only what on_pre_step reads: ``protocol`` and
    ``wait``. Records the events passed to wait() so a no-op can be asserted
    by ``waited is None``."""

    def __init__(self, protocol):
        self.protocol = protocol
        self.waited = None

    def wait(self, events, timeout=86400):
        self.waited = events


def _make_proto() -> ProtocolContext:
    return ProtocolContext(
        columns=[], stop_event=threading.Event(), pause_event=PauseEvent(),
    )


def test_empty_message_is_a_noop():
    handler = MsgPromptColumnHandler()
    proto = _make_proto()
    ctx = _FakeCtx(proto)
    row = types.SimpleNamespace(message_prompt="")

    handler.on_pre_step(row, ctx)

    # No dialog, no wait, no pause.
    assert ctx.waited is None
    assert proto.pause_event.is_set() is False


def test_aborts_when_already_stopped_before_prompt():
    handler = MsgPromptColumnHandler()
    proto = _make_proto()
    proto.stop_event.set()
    ctx = _FakeCtx(proto)
    row = types.SimpleNamespace(message_prompt="Load 100uL")

    with pytest.raises(AbortError):
        handler.on_pre_step(row, ctx)


def test_factory_wires_model_view_handler():
    col = make_message_prompt_column()
    assert col.model.col_id == "message_prompt"
    assert isinstance(col.handler, MsgPromptColumnHandler)
    # The handler's reusable dialog event is created in traits_init.
    assert isinstance(col.handler._wait_for_dialog_event, threading.Event)
