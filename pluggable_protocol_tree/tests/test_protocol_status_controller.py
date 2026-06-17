"""Unit tests for ProtocolStatusController (fake signals + manager, no Qt)."""
from pluggable_protocol_tree.services.protocol_status_controller import (
    ProtocolStatusController,
)


class _Sig:
    """Minimal Qt-signal stand-in: connect() stores slots, emit() calls them."""
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot):
        self._slots.remove(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class _Signals:
    def __init__(self):
        for name in (
            "protocol_started", "step_started", "step_repetition",
            "phase_started", "phase_extended", "protocol_paused",
            "protocol_resumed", "protocol_repetition_finished",
            "protocol_finished", "protocol_aborted", "protocol_error",
        ):
            setattr(self, name, _Sig())


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
    sigs = _Signals()
    clock = {"t": 0.0}
    ctrl = ProtocolStatusController(
        qsignals=sigs, manager=_Manager(rows), clock=lambda: clock["t"],
    )
    return ctrl, sigs, clock, rows


def test_protocol_started_counts_steps():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started.emit()
    assert ctrl.model.step_total == 2
    assert ctrl.model.running is True


def test_step_started_sets_name_and_next():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started.emit()
    sigs.step_started.emit(rows[0])
    assert ctrl.model.step_index == 1
    assert ctrl.model.recent_step_name == "A"
    assert ctrl.model.next_step_name == "B"


def test_pause_resume_drive_model_with_clock():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started.emit()
    sigs.step_started.emit(rows[0])
    clock["t"] = 1.0
    sigs.protocol_paused.emit()
    assert ctrl.model.paused is True
    assert ctrl.model.protocol_clock.active(5.0) == 1.0


def test_phase_started_and_extended():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started.emit()
    sigs.step_started.emit(rows[0])
    sigs.phase_started.emit(2, 4, 1.5)
    assert ctrl.model.phase_index == 2
    assert ctrl.model.phase_total == 4
    assert ctrl.model.phase_target_s == 1.5
    sigs.phase_extended.emit(0.5)
    assert ctrl.model.phase_target_s == 2.0


def test_rep_chain_formatting():
    ctrl, sigs, clock, rows = _make()
    sigs.step_repetition.emit([("Wash", 2, 3)])
    assert ctrl.model.rep_chain_label == "rep 2/3 of 'Wash'"
    sigs.step_repetition.emit([])
    assert ctrl.model.rep_chain_label == ""


def test_terminal_signals_reset_trackers():
    # Finished / aborted are the post-protocol teardown: reset to idle.
    for term in ("protocol_finished", "protocol_aborted"):
        ctrl, sigs, clock, rows = _make()
        sigs.protocol_started.emit()
        sigs.step_started.emit(rows[0])
        clock["t"] = 5.0
        getattr(sigs, term).emit()
        assert ctrl.model.running is False
        assert ctrl.model.step_index == 0
        assert ctrl.model.step_total == 0
        assert ctrl.model.protocol_clock.elapsed(9.0) == 0.0


def test_error_resets_trackers():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started.emit()
    sigs.protocol_error.emit("boom")
    assert ctrl.model.running is False
    assert ctrl.model.step_total == 0


def test_disconnect_stops_updates():
    ctrl, sigs, clock, rows = _make()
    ctrl.disconnect()
    sigs.protocol_started.emit()
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
    c = ProtocolStatusController(qsignals=None, manager=manager, executor=ex,
                                 clock=lambda: 7.0)
    c.model.on_protocol_start(0.0, 1)
    c.model.on_step_start(0.0, "Wash", "-")
    c.model.pause(0.0)

    c.seek_to((0,), 0)

    assert ex.seek_calls == [((0,), 0)]
    assert c.model.step_index == 1          # step (0,) is the 1st step
    assert c.model.phase_index == 1         # phases are 1-based in the model
