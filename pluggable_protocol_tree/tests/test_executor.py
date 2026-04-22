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
