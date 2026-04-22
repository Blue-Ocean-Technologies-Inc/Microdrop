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
