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
