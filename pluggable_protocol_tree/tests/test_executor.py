"""Tests for execution.executor and .signals.

Most tests do NOT require a QApplication — Qt direct-connect signals work
without an event loop when sender and receiver share a thread. Tests that
need cross-thread signal delivery construct a QApplication via fixture.
"""

from pluggable_protocol_tree.execution.signals import ExecutorSignals


def test_executor_signals_constructible_without_qapplication():
    s = ExecutorSignals()
    # All eight expected signals are present as attributes.
    for name in (
        "protocol_started", "step_started", "step_finished",
        "protocol_paused", "protocol_resumed",
        "protocol_finished", "protocol_aborted", "protocol_error",
    ):
        assert hasattr(s, name), f"missing signal: {name}"


def test_executor_signals_direct_connect_invokes_slot():
    s = ExecutorSignals()
    received = []
    s.protocol_finished.connect(lambda: received.append("finished"))
    s.protocol_finished.emit()
    assert received == ["finished"]


def test_executor_signals_step_started_carries_row():
    s = ExecutorSignals()
    received = []
    s.step_started.connect(lambda row: received.append(row))
    sentinel = object()
    s.step_started.emit(sentinel)
    assert received == [sentinel]


def test_executor_signals_protocol_error_carries_message():
    s = ExecutorSignals()
    received = []
    s.protocol_error.connect(lambda msg: received.append(msg))
    s.protocol_error.emit("oops")
    assert received == ["oops"]


# --- ProtocolExecutor public API ---

import threading

import pytest

from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column


def _make_executor():
    """Bare-bones executor with the four PPT-1 built-in columns."""
    cols = [make_type_column(), make_id_column(),
            make_name_column(), make_duration_column()]
    rm = RowManager(columns=cols)
    return ProtocolExecutor(
        row_manager=rm,
        qsignals=ExecutorSignals(),
        pause_event=PauseEvent(),
        stop_event=threading.Event(),
    )


def test_executor_constructible_with_required_traits():
    ex = _make_executor()
    assert ex.row_manager is not None
    assert ex.qsignals is not None
    assert ex.pause_event is not None
    assert ex.stop_event is not None


def test_executor_pause_emits_protocol_paused():
    ex = _make_executor()
    received = []
    ex.qsignals.protocol_paused.connect(lambda: received.append("paused"))
    ex.pause()
    assert ex.pause_event.is_set() is True
    assert received == ["paused"]


def test_executor_resume_emits_protocol_resumed():
    ex = _make_executor()
    received = []
    ex.qsignals.protocol_resumed.connect(lambda: received.append("resumed"))
    ex.pause()
    ex.resume()
    assert ex.pause_event.is_set() is False
    assert received == ["resumed"]


def test_executor_stop_sets_stop_event_and_clears_pause():
    """stop() must also clear pause_event so a Stop-while-paused doesn't
    deadlock the main loop in wait_cleared()."""
    ex = _make_executor()
    ex.pause()
    assert ex.pause_event.is_set() is True
    ex.stop()
    assert ex.stop_event.is_set() is True
    assert ex.pause_event.is_set() is False


# --- ProtocolExecutor.run() — main loop ---

import time

from pluggable_protocol_tree.execution.signals import ExecutorSignals


class _SignalSpy:
    """Collects signal emissions into a list for assertion."""
    def __init__(self, sigs: ExecutorSignals):
        self.events = []
        sigs.protocol_started.connect(lambda: self.events.append(("protocol_started",)))
        sigs.step_started.connect(lambda r: self.events.append(("step_started", r.name)))
        sigs.step_finished.connect(lambda r: self.events.append(("step_finished", r.name)))
        sigs.protocol_finished.connect(lambda: self.events.append(("protocol_finished",)))
        sigs.protocol_aborted.connect(lambda: self.events.append(("protocol_aborted",)))
        sigs.protocol_error.connect(lambda m: self.events.append(("protocol_error", m)))


def test_run_empty_protocol_emits_started_then_finished():
    ex = _make_executor()
    spy = _SignalSpy(ex.qsignals)
    ex.run()       # synchronous; bypasses start()/QThread
    assert spy.events[0] == ("protocol_started",)
    assert spy.events[-1] == ("protocol_finished",)


def test_run_three_steps_emits_step_signals_in_order():
    ex = _make_executor()
    a = ex.row_manager.add_step(values={"name": "A"})
    b = ex.row_manager.add_step(values={"name": "B"})
    c = ex.row_manager.add_step(values={"name": "C"})
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    step_events = [e for e in spy.events if e[0] in ("step_started", "step_finished")]
    assert step_events == [
        ("step_started", "A"), ("step_finished", "A"),
        ("step_started", "B"), ("step_finished", "B"),
        ("step_started", "C"), ("step_finished", "C"),
    ]


def test_run_stop_pre_set_aborts_immediately():
    ex = _make_executor()
    ex.row_manager.add_step(values={"name": "A"})
    ex.row_manager.add_step(values={"name": "B"})
    ex.stop_event.set()
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    # No step events; terminal is aborted, not finished.
    assert ("step_started", "A") not in spy.events
    assert spy.events[-1] == ("protocol_aborted",)


def test_run_pause_then_resume_blocks_then_continues():
    """Set pause_event before calling run() so iter_execution_steps's
    first iteration hits wait_cleared(). Then clear it from another
    thread to release."""
    ex = _make_executor()
    ex.row_manager.add_step(values={"name": "A"})
    ex.pause_event.set()
    spy = _SignalSpy(ex.qsignals)

    def resumer():
        time.sleep(0.05)
        ex.pause_event.clear()

    threading.Thread(target=resumer, daemon=True).start()
    start = time.monotonic()
    ex.run()
    elapsed = time.monotonic() - start
    # We waited ~50ms before resume; protocol then completed quickly.
    assert elapsed >= 0.05
    assert spy.events[-1] == ("protocol_finished",)


def test_run_stop_while_paused_breaks_out():
    """Regression for the deadlock-avoidance code in stop()."""
    ex = _make_executor()
    ex.row_manager.add_step(values={"name": "A"})
    ex.pause_event.set()
    spy = _SignalSpy(ex.qsignals)

    def stopper():
        time.sleep(0.05)
        ex.stop()

    threading.Thread(target=stopper, daemon=True).start()
    ex.run()
    assert spy.events[-1] == ("protocol_aborted",)
