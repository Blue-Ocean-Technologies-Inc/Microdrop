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
