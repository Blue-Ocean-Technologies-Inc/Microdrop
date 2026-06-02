"""Tests for execution.exceptions, .events, .step_context.

Pure-Python unit tests — no Qt application, no Dramatiq broker.
Behavioral tests for Mailbox / ProtocolContext / StepContext / wait_for
get appended in later tasks; this file starts with the smallest
foundational types."""

from pluggable_protocol_tree.execution.exceptions import AbortError


def test_abort_error_is_exception():
    assert issubclass(AbortError, Exception)


def test_abort_error_carries_message():
    e = AbortError("stop pressed")
    assert str(e) == "stop pressed"


# --- PauseEvent ---

import threading
import time

from pluggable_protocol_tree.execution.events import PauseEvent


def test_pause_event_starts_unset_and_cleared():
    p = PauseEvent()
    assert p.is_set() is False


def test_pause_event_set_and_clear_round_trip():
    p = PauseEvent()
    p.set()
    assert p.is_set() is True
    p.clear()
    assert p.is_set() is False


def test_pause_event_wait_cleared_returns_immediately_when_unset():
    p = PauseEvent()
    # Already cleared; should not block.
    start = time.monotonic()
    p.wait_cleared(timeout=0.5)
    assert time.monotonic() - start < 0.1


def test_pause_event_wait_cleared_blocks_until_clear():
    p = PauseEvent()
    p.set()
    woken = threading.Event()

    def waiter():
        p.wait_cleared(timeout=2.0)
        woken.set()

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    # waiter should still be blocked
    assert woken.wait(timeout=0.1) is False
    p.clear()
    assert woken.wait(timeout=1.0) is True
    t.join(timeout=1.0)


# --- wait_first ---

from pluggable_protocol_tree.execution.step_context import wait_first


def test_wait_first_returns_event_that_fires_first():
    a = threading.Event()
    b = threading.Event()
    threading.Timer(0.05, b.set).start()
    fired = wait_first([a, b], timeout=1.0)
    assert fired is b


def test_wait_first_returns_none_on_timeout():
    a = threading.Event()
    b = threading.Event()
    fired = wait_first([a, b], timeout=0.05)
    assert fired is None


def test_wait_first_returns_immediately_when_event_already_set():
    a = threading.Event()
    a.set()
    start = time.monotonic()
    fired = wait_first([a], timeout=1.0)
    assert fired is a
    assert time.monotonic() - start < 0.1


# --- Mailbox ---

from pluggable_protocol_tree.execution.step_context import Mailbox
from pluggable_protocol_tree.execution.exceptions import AbortError


def test_mailbox_drain_one_returns_pre_deposited_immediately():
    mb = Mailbox()
    mb.deposit({"v": 1})
    stop = threading.Event()
    start = time.monotonic()
    item = mb.drain_one(predicate=None, timeout=1.0, stop_event=stop)
    assert item == {"v": 1}
    assert time.monotonic() - start < 0.1


def test_mailbox_drain_one_blocks_then_wakes_on_deposit():
    mb = Mailbox()
    stop = threading.Event()
    threading.Timer(0.05, lambda: mb.deposit("hello")).start()
    item = mb.drain_one(predicate=None, timeout=1.0, stop_event=stop)
    assert item == "hello"


def test_mailbox_drain_one_raises_timeout_when_nothing_arrives():
    mb = Mailbox()
    stop = threading.Event()
    with __import__("pytest").raises(TimeoutError):
        mb.drain_one(predicate=None, timeout=0.05, stop_event=stop)


def test_mailbox_drain_one_raises_abort_when_stop_pre_set():
    mb = Mailbox()
    stop = threading.Event()
    stop.set()
    with __import__("pytest").raises(AbortError):
        mb.drain_one(predicate=None, timeout=1.0, stop_event=stop)


def test_mailbox_drain_one_raises_abort_when_stop_fires_mid_wait():
    mb = Mailbox()
    stop = threading.Event()
    threading.Timer(0.05, stop.set).start()
    start = time.monotonic()
    with __import__("pytest").raises(AbortError):
        mb.drain_one(predicate=None, timeout=2.0, stop_event=stop)
    # Must abort promptly, not wait out the 2s timeout.
    assert time.monotonic() - start < 0.5


def test_mailbox_predicate_rejects_then_accepts():
    mb = Mailbox()
    stop = threading.Event()
    mb.deposit({"ready": False})
    mb.deposit({"ready": True})
    item = mb.drain_one(
        predicate=lambda p: p.get("ready"),
        timeout=1.0,
        stop_event=stop,
    )
    assert item == {"ready": True}


def test_mailbox_predicate_rejects_all_pre_deposited_then_blocks():
    mb = Mailbox()
    stop = threading.Event()
    mb.deposit({"ready": False})
    mb.deposit({"ready": False})
    threading.Timer(0.05, lambda: mb.deposit({"ready": True})).start()
    item = mb.drain_one(
        predicate=lambda p: p.get("ready"),
        timeout=1.0,
        stop_event=stop,
    )
    assert item == {"ready": True}


# --- ProtocolContext + StepContext + wait_for ---

from pluggable_protocol_tree.execution.step_context import (
    ProtocolContext, StepContext,
)
from pluggable_protocol_tree.models.row import BaseRow


def _make_step_ctx(topics: list) -> StepContext:
    """Helper: build a StepContext with mailboxes pre-opened for `topics`."""
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    for t in topics:
        step.open_mailbox(t)
    return step


def test_wait_for_returns_payload_after_deposit():
    step = _make_step_ctx(["t/foo"])
    threading.Timer(
        0.05, lambda: step.deposit("t/foo", {"v": 1})
    ).start()
    payload = step.wait_for("t/foo", timeout=1.0)
    assert payload == {"v": 1}


def test_wait_for_returns_pre_deposited_immediately():
    """The race-fix that justifies the per-step pre-registration model."""
    step = _make_step_ctx(["t/ack"])
    step.deposit("t/ack", {"ok": True})
    start = time.monotonic()
    payload = step.wait_for("t/ack", timeout=1.0)
    assert payload == {"ok": True}
    assert time.monotonic() - start < 0.1


def test_wait_for_unknown_topic_raises_keyerror():
    """Unopened topics indicate a missing wait_for_topics declaration."""
    step = _make_step_ctx(["t/known"])
    import pytest
    with pytest.raises(KeyError):
        step.wait_for("t/unknown", timeout=0.1)


def test_wait_for_timeout():
    step = _make_step_ctx(["t/never"])
    import pytest
    with pytest.raises(TimeoutError):
        step.wait_for("t/never", timeout=0.05)


def test_wait_for_abort_when_stop_event_fires():
    step = _make_step_ctx(["t/never"])
    threading.Timer(0.05, step.protocol.stop_event.set).start()
    import pytest
    with pytest.raises(AbortError):
        step.wait_for("t/never", timeout=2.0)


def test_wait_for_predicate_filters_payloads():
    step = _make_step_ctx(["t/status"])
    step.deposit("t/status", {"ready": False})
    step.deposit("t/status", {"ready": True})
    payload = step.wait_for(
        "t/status", timeout=1.0,
        predicate=lambda p: p.get("ready") is True,
    )
    assert payload == {"ready": True}


def test_protocol_context_scratch_is_per_protocol():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    proto.scratch["k"] = "v"
    assert proto.scratch["k"] == "v"


def test_step_context_scratch_is_per_step_and_independent():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    a = StepContext(row=BaseRow(name="a"), protocol=proto)
    b = StepContext(row=BaseRow(name="b"), protocol=proto)
    a.scratch["k"] = "av"
    b.scratch["k"] = "bv"
    assert a.scratch["k"] == "av"
    assert b.scratch["k"] == "bv"


# --- listener active-step pointer ---

from pluggable_protocol_tree.execution import listener as _listener


def test_listener_active_step_initially_none():
    _listener.clear_active_step()
    assert _listener.get_active_step() is None


def test_listener_set_then_get_returns_step():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    _listener.set_active_step(step)
    try:
        assert _listener.get_active_step() is step
    finally:
        _listener.clear_active_step()


def test_listener_clear_resets_to_none():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    _listener.set_active_step(step)
    _listener.clear_active_step()
    assert _listener.get_active_step() is None


def test_listener_route_to_active_step_deposits_into_mailbox():
    """Direct route() helper bypasses Dramatiq for unit testing."""
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    step.open_mailbox("t/foo")
    _listener.set_active_step(step)
    try:
        _listener.route_to_active_step("t/foo", {"v": 42})
        item = step.wait_for("t/foo", timeout=0.1)
        assert item == {"v": 42}
    finally:
        _listener.clear_active_step()


def test_listener_route_with_no_active_step_drops_silently():
    _listener.clear_active_step()
    # No exception, no observable side effect.
    _listener.route_to_active_step("t/foo", {"v": 1})


def test_listener_route_for_unopened_topic_drops_silently():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    step.open_mailbox("t/known")
    _listener.set_active_step(step)
    try:
        # No exception — the listener simply has nowhere to put it.
        _listener.route_to_active_step("t/unknown", {"v": 1})
    finally:
        _listener.clear_active_step()


# --- ProtocolContext.pause/resume + StepContext.wait ---

import pytest

from pluggable_protocol_tree.execution.events import PauseEvent


class _FakeSignal:
    """Records each emit() onto a shared log so tests can assert ordering."""

    def __init__(self, log: list, name: str):
        self._log = log
        self._name = name

    def emit(self):
        self._log.append(self._name)


class _FakeQSignals:
    """Stand-in for ExecutorSignals — no QObject / Qt loop needed. Only the
    two signals pause/resume touch are provided."""

    def __init__(self):
        self.events: list = []
        self.protocol_paused = _FakeSignal(self.events, "paused")
        self.protocol_resumed = _FakeSignal(self.events, "resumed")


def _make_proto(qsignals=None) -> ProtocolContext:
    return ProtocolContext(
        columns=[],
        stop_event=threading.Event(),
        pause_event=PauseEvent(),
        qsignals=qsignals,
    )


def test_pause_resume_set_clear_event_and_emit_signals():
    q = _FakeQSignals()
    proto = _make_proto(q)
    proto.pause()
    assert proto.pause_event.is_set() is True
    proto.resume()
    assert proto.pause_event.is_set() is False
    # Single source of truth: paused then resumed, in order.
    assert q.events == ["paused", "resumed"]


def test_pause_resume_without_qsignals_does_not_crash():
    """Headless/test runs have no ExecutorSignals; only the event toggles."""
    proto = _make_proto(qsignals=None)
    proto.pause()
    assert proto.pause_event.is_set() is True
    proto.resume()
    assert proto.pause_event.is_set() is False


def test_wait_returns_and_resumes_when_event_fires():
    q = _FakeQSignals()
    proto = _make_proto(q)
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    ev = threading.Event()
    threading.Timer(0.05, ev.set).start()

    step.wait(events=[ev, proto.stop_event], timeout=1.0)

    # Acknowledged → run resumed before returning.
    assert proto.pause_event.is_set() is False
    assert q.events == ["paused", "resumed"]


def test_wait_aborts_promptly_when_stop_event_fires():
    proto = _make_proto()
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    threading.Timer(0.05, proto.stop_event.set).start()
    start = time.monotonic()
    with pytest.raises(AbortError):
        step.wait(events=[proto.stop_event], timeout=2.0)
    # Must abort on the stop_event, not wait out the 2s timeout.
    assert time.monotonic() - start < 0.5


def test_wait_times_out_when_nothing_fires():
    proto = _make_proto()
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    ev = threading.Event()  # never set
    with pytest.raises(TimeoutError):
        step.wait(events=[ev, proto.stop_event], timeout=0.05)


def test_wait_returns_on_external_resume():
    """Clearing pause_event out-of-band (e.g. toolbar Resume) ends the wait
    even though none of the passed events ever fire."""
    proto = _make_proto()
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    ev = threading.Event()  # never set
    threading.Timer(0.05, proto.pause_event.clear).start()
    start = time.monotonic()
    step.wait(events=[ev, proto.stop_event], timeout=2.0)
    assert time.monotonic() - start < 0.5
    assert proto.pause_event.is_set() is False
