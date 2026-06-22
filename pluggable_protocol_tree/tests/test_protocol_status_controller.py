"""Unit tests for ProtocolStatusController (real ExecutorSignals events +
fake manager, no Qt). ExecutorSignals is a HasTraits, so "emitting" a signal
is setting its Event trait; default-dispatch observers fire synchronously on
the setting thread, so these asserts run inline with no event loop."""
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.services.protocol_status_controller import (
    ProtocolStatusController,
)


class _Executor:
    """Minimal executor stand-in: the controller reads .signals off it."""
    def __init__(self, signals):
        self.signals = signals


class _Row:
    def __init__(self, name, path):
        self.name = name
        self.path = path


class _Manager:
    def __init__(self, rows):
        self._rows = rows

    def iter_execution_steps(self):
        return iter(list(self._rows))


def _make(rows=None):
    rows = rows or [_Row("A", (0,)), _Row("B", (1,))]
    sigs = ExecutorSignals()
    clock = {"t": 0.0}
    ctrl = ProtocolStatusController(
        executor=_Executor(sigs), manager=_Manager(rows),
        clock=lambda: clock["t"],
    )
    return ctrl, sigs, clock, rows


def test_protocol_started_counts_steps():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started = True
    assert ctrl.model.step_total == 2
    assert ctrl.model.running is True


def test_step_started_sets_name_and_next():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started = True
    sigs.step_started = (rows[0], 1, 2)
    assert ctrl.model.step_index == 1
    assert ctrl.model.recent_step_name == "A"
    assert ctrl.model.next_step_name == "B"


def test_pause_resume_drive_model_with_clock():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started = True
    sigs.step_started = (rows[0], 1, 2)
    clock["t"] = 1.0
    sigs.protocol_paused = True
    assert ctrl.model.paused is True
    assert ctrl.model.protocol_clock.active(5.0) == 1.0


def test_phase_started_and_extended():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started = True
    sigs.step_started = (rows[0], 1, 2)
    sigs.phase_started = (2, 4, 1.5)
    assert ctrl.model.phase_index == 2
    assert ctrl.model.phase_total == 4
    assert ctrl.model.phase_target_s == 1.5
    sigs.phase_extended = 0.5
    assert ctrl.model.phase_target_s == 2.0


def test_rep_chain_formatting():
    ctrl, sigs, clock, rows = _make()
    sigs.step_repetition = [("Wash", 2, 3)]
    assert ctrl.model.rep_chain_label == "Step Rep 2/3"
    sigs.step_repetition = []
    assert ctrl.model.rep_chain_label == ""


def test_step_count_collapses_repetitions():
    # One step yielded 3 times (Reps=3) reads as a single step, not 3 -- the
    # rep progress lives in the separate step_repetition label.
    shared = _Row("Wash", (0,))
    ctrl, sigs, clock, rows = _make(rows=[shared, shared, shared])
    sigs.protocol_started = True
    assert ctrl.model.step_total == 1
    sigs.step_started = (shared, 2, 3)   # executor's 2nd of 3 frames
    assert ctrl.model.step_index == 1    # still the only distinct step
    assert ctrl.model.step_total == 1


def test_frame_index_tracked_alongside_distinct_step():
    # The per-rep execution frame is kept for the timeline's "show full" view,
    # separate from the collapsed step counter.
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started = True
    sigs.step_started = (rows[0], 3, 5)   # executor frame 3 of 5
    assert ctrl.model.frame_index == 3
    assert ctrl.model.frame_total == 5
    assert ctrl.model.step_index == 1     # distinct step still 1


def test_step_rep_tracked_from_chain():
    ctrl, sigs, clock, rows = _make()
    sigs.step_repetition = [("Wash", 2, 8)]
    assert ctrl.model.step_rep_index == 2
    assert ctrl.model.step_rep_total == 8
    sigs.step_repetition = []             # non-repeating step clears it
    assert ctrl.model.step_rep_index == 0
    assert ctrl.model.step_rep_total == 0


def test_terminal_signals_reset_trackers():
    # Finished / aborted are the post-protocol teardown: reset to idle.
    for term in ("protocol_finished", "protocol_aborted"):
        ctrl, sigs, clock, rows = _make()
        sigs.protocol_started = True
        sigs.step_started = (rows[0], 1, 2)
        clock["t"] = 5.0
        setattr(sigs, term, True)
        assert ctrl.model.running is False
        assert ctrl.model.step_index == 0
        assert ctrl.model.step_total == 0
        assert ctrl.model.protocol_clock.elapsed(9.0) == 0.0


def test_error_resets_trackers():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started = True
    sigs.protocol_error = "boom"
    assert ctrl.model.running is False
    assert ctrl.model.step_total == 0


def test_disconnect_stops_updates():
    ctrl, sigs, clock, rows = _make()
    ctrl.disconnect()
    sigs.protocol_started = True
    assert ctrl.model.step_total == 0   # not wired anymore


# ---------------------------------------------------------------------------
# seek_to (#471)
# ---------------------------------------------------------------------------

from types import SimpleNamespace
from pluggable_protocol_tree.services.protocol_status_controller import (
    ProtocolStatusController,
)


class _StubExecutor:
    def __init__(self):
        self.seek_calls = []
        self.signals = None    # this test drives seek_to directly, no events

    def seek(self, step_path, phase_index):
        self.seek_calls.append((tuple(step_path), phase_index))


def _row(path, name="S", **kw):
    return SimpleNamespace(path=tuple(path), name=name, dotted_path=lambda: "1",
                           **kw)


def test_seek_to_calls_executor_and_updates_model():
    row = _row((0,), name="Wash", electrodes=[], routes=[], trail_length=1,
               trail_overlay=0, soft_start=False, soft_end=False,
               repeat_duration=0.0, repeat_duration_controls=False,
               linear_repeats=False, route_repetitions=1, duration_s=1.0)
    manager = SimpleNamespace(
        iter_execution_steps=lambda: iter([row]),
    )
    ex = _StubExecutor()
    c = ProtocolStatusController(signals=None, manager=manager, executor=ex,
                                 clock=lambda: 7.0)
    c.model.on_protocol_start(0.0, 1)
    c.model.on_step_start(0.0, 1, 1, (0,), "Wash", "-")
    c.model.pause(0.0)

    c.seek_to((0,), 0)

    assert ex.seek_calls == [((0,), 0)]
    assert c.model.step_index == 1          # step (0,) is the 1st step
    assert c.model.step_total == 1
    assert c.model.current_step_path == (0,)
    assert c.model.phase_index == 1         # phases are 1-based in the model
