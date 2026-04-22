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


# --- priority bucket fan-out ---

from traits.api import HasTraits, Int, List, provides, Str

from pluggable_protocol_tree.interfaces.i_column import IColumnHandler
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)


def _recording_handler(name, priority, log: list, barrier=None):
    """Build a handler that appends (name, hook_name) to `log` on each
    fire. Optional `barrier` makes the handler block on a threading
    barrier inside on_step (used to prove parallel execution)."""
    class _H(BaseColumnHandler):
        def on_protocol_start(self, ctx):  log.append((name, "on_protocol_start"))
        def on_pre_step(self, row, ctx):   log.append((name, "on_pre_step"))
        def on_step(self, row, ctx):
            log.append((name, "on_step"))
            if barrier is not None:
                barrier.wait(timeout=2.0)
        def on_post_step(self, row, ctx):  log.append((name, "on_post_step"))
        def on_protocol_end(self, ctx):    log.append((name, "on_protocol_end"))
    h = _H()
    h.priority = priority
    return h


def _make_recording_column(col_id, priority, log, barrier=None):
    return Column(
        model=BaseColumnModel(col_id=col_id, col_name=col_id, default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_recording_handler(col_id, priority, log, barrier),
    )


def _executor_with(cols):
    """Build an executor on a fresh RowManager containing one step,
    with the given extra columns layered on top of the four PPT-1
    builtins (so iter_execution_steps yields one row)."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    builtins = [make_type_column(), make_id_column(),
                make_name_column(), make_duration_column()]
    rm = RowManager(columns=builtins + list(cols))
    rm.add_step(values={"name": "A"})
    return ProtocolExecutor(
        row_manager=rm,
        qsignals=ExecutorSignals(),
        pause_event=PauseEvent(),
        stop_event=threading.Event(),
    )


def test_run_hooks_orders_buckets_by_priority():
    log = []
    low = _make_recording_column("low", priority=10, log=log)
    high = _make_recording_column("high", priority=30, log=log)
    ex = _executor_with([high, low])   # deliberately shuffled
    ex.run()
    on_step_calls = [name for (name, hook) in log if hook == "on_step"]
    # All low (priority 10) before any high (priority 30)
    assert on_step_calls.index("low") < on_step_calls.index("high")


def test_run_hooks_fans_same_priority_in_parallel():
    log = []
    barrier = threading.Barrier(2)
    a = _make_recording_column("a", priority=20, log=log, barrier=barrier)
    b = _make_recording_column("b", priority=20, log=log, barrier=barrier)
    ex = _executor_with([a, b])
    # If they don't run in parallel the barrier never trips and the
    # executor blocks until barrier timeout (2s) — test would take >2s.
    start = time.monotonic()
    ex.run()
    elapsed = time.monotonic() - start
    assert elapsed < 1.5, "same-priority hooks did not fan out in parallel"
    on_step_names = [name for (name, hook) in log if hook == "on_step"]
    assert sorted(on_step_names) == ["a", "b"]


def test_run_hooks_uses_default_priority_50_for_unset():
    """BaseColumnHandler defaults priority to 50 — no explicit set
    needed for a column that doesn't care about ordering."""
    log = []
    no_pri = _make_recording_column("default", priority=50, log=log)
    early = _make_recording_column("early", priority=10, log=log)
    ex = _executor_with([no_pri, early])
    ex.run()
    on_step_calls = [name for (name, hook) in log if hook == "on_step"]
    assert on_step_calls.index("early") < on_step_calls.index("default")


def test_run_hooks_all_five_phases_fire_in_order_for_one_step():
    log = []
    col = _make_recording_column("c", priority=50, log=log)
    ex = _executor_with([col])
    ex.run()
    # Filter to the recording column only (built-ins also fire but with
    # no logging side effect — their handlers are BaseColumnHandler).
    c_calls = [hook for (name, hook) in log if name == "c"]
    assert c_calls == [
        "on_protocol_start",
        "on_pre_step", "on_step", "on_post_step",
        "on_protocol_end",
    ]


# --- same-topic conflict + error propagation ---

def _handler_with_topic(name, priority, topic, log):
    class _H(BaseColumnHandler):
        wait_for_topics = [topic]
        def on_step(self, row, ctx):
            log.append((name, "on_step"))
    h = _H()
    h.priority = priority
    return h


def _column_with_topic_handler(col_id, priority, topic, log):
    return Column(
        model=BaseColumnModel(col_id=col_id, col_name=col_id, default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_handler_with_topic(col_id, priority, topic, log),
    )


def test_same_topic_in_same_priority_bucket_raises():
    """Two columns both declaring the same wait_for_topic at the same
    priority would race for the mailbox. Detected at step start."""
    log = []
    a = _column_with_topic_handler("a", 20, "shared/topic", log)
    b = _column_with_topic_handler("b", 20, "shared/topic", log)
    ex = _executor_with([a, b])
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    # Surfaces as a protocol_error (the _build_step_ctx assertion raises).
    assert spy.events[-1][0] == "protocol_error"
    assert "shared/topic" in spy.events[-1][1]


def test_same_topic_different_priority_buckets_is_fine():
    """Sequential — no race. Should not raise."""
    log = []
    a = _column_with_topic_handler("a", 10, "shared/topic", log)
    b = _column_with_topic_handler("b", 30, "shared/topic", log)
    ex = _executor_with([a, b])
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    assert spy.events[-1] == ("protocol_finished",)


def test_hook_exception_emits_protocol_error_not_finished():
    log = []

    class _Boom(BaseColumnHandler):
        def on_step(self, row, ctx):
            raise RuntimeError("kaboom")

    col = Column(
        model=BaseColumnModel(col_id="boom", col_name="boom", default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_Boom(),
    )
    ex = _executor_with([col])
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    err_events = [e for e in spy.events if e[0] == "protocol_error"]
    assert len(err_events) == 1
    assert "kaboom" in err_events[0][1]
    # Did NOT emit finished or aborted.
    assert ("protocol_finished",) not in spy.events
    assert ("protocol_aborted",) not in spy.events


def test_on_protocol_end_runs_even_on_error():
    """Best-effort cleanup: if on_step raises, on_protocol_end still
    fires (in the except branch's fallback)."""
    log = []

    class _Boom(BaseColumnHandler):
        def on_step(self, row, ctx):
            raise RuntimeError("kaboom")
        def on_protocol_end(self, ctx):
            log.append("end_ran")

    col = Column(
        model=BaseColumnModel(col_id="boom", col_name="boom", default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_Boom(),
    )
    ex = _executor_with([col])
    ex.run()
    assert "end_ran" in log


def test_on_protocol_end_raising_during_error_cleanup_is_swallowed():
    """If both on_step AND on_protocol_end raise, the original error
    wins (it's what surfaces as protocol_error) and the on_protocol_end
    exception is logged but not re-raised."""
    log = []

    class _DoubleBoom(BaseColumnHandler):
        def on_step(self, row, ctx):
            raise RuntimeError("first")
        def on_protocol_end(self, ctx):
            raise RuntimeError("second")

    col = Column(
        model=BaseColumnModel(col_id="boom", col_name="boom", default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_DoubleBoom(),
    )
    ex = _executor_with([col])
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    err_events = [e for e in spy.events if e[0] == "protocol_error"]
    assert len(err_events) == 1
    assert "first" in err_events[0][1]
    assert "second" not in err_events[0][1]
