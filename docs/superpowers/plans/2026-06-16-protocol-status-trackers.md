# Protocol Status Trackers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the protocol status-bar timing/counting out of `ProtocolTreePane` into a Qt-free `HasTraits` model driven by a small reusable controller, add the six time readouts (elapsed + active for protocol/step/phase) and Step n/N + Phase n/N counters, and bind the existing `StatusBar` to the model.

**Architecture:** Model (`ProtocolStatusModel` + `ScopeStopwatch`, pure) ← Controller (`ProtocolStatusController`, HasTraits, owns model, subscribes to `ExecutorSignals`) → View (`StatusBar.bind(model)`: Traits observers + a 10 Hz poll timer). The dock pane and the standalone demo window each own a controller. Model is mutated only on the GUI thread, so observers drive widgets directly with no Qt-signal bridge.

**Tech Stack:** Python, Traits (enthought), PySide6/pyface Qt, pytest.

Spec: `docs/superpowers/specs/2026-06-16-protocol-status-trackers-design.md`.

**Test command (verify once at Task 1, reuse everywhere):**
`pixi run pytest pluggable_protocol_tree/tests/<file> -v` run from `microdrop-py/src`. If that path fails, try `cd microdrop-py && pixi run pytest src/pluggable_protocol_tree/tests/<file> -v`. Pure-model/controller tests need no Redis/Qt.

---

### Task 1: `ScopeStopwatch` timing primitive

**Files:**
- Create: `pluggable_protocol_tree/models/stopwatch.py`
- Test: `pluggable_protocol_tree/tests/test_stopwatch.py`

- [ ] **Step 1: Write the failing test**

```python
# pluggable_protocol_tree/tests/test_stopwatch.py
"""Unit tests for ScopeStopwatch (pure, fake-clock)."""
from pluggable_protocol_tree.models.stopwatch import ScopeStopwatch


def test_not_started_reads_zero():
    sw = ScopeStopwatch()
    assert sw.elapsed(100.0) == 0.0
    assert sw.active(100.0) == 0.0


def test_elapsed_and_active_tick_together_when_running():
    sw = ScopeStopwatch()
    sw.start(0.0)
    assert sw.elapsed(2.0) == 2.0
    assert sw.active(2.0) == 2.0


def test_elapsed_ignores_pause_active_freezes():
    sw = ScopeStopwatch()
    sw.start(0.0)
    sw.pause(1.0)          # active frozen at 1.0; elapsed keeps going
    assert sw.elapsed(5.0) == 5.0
    assert sw.active(5.0) == 1.0
    sw.resume(5.0)         # active resumes from 1.0
    assert sw.elapsed(6.0) == 6.0
    assert sw.active(6.0) == 2.0


def test_stop_freezes_both():
    sw = ScopeStopwatch()
    sw.start(0.0)
    sw.stop(3.0)
    assert sw.elapsed(99.0) == 3.0
    assert sw.active(99.0) == 3.0


def test_resume_after_stop_is_noop():
    sw = ScopeStopwatch()
    sw.start(0.0)
    sw.stop(3.0)
    sw.resume(10.0)
    assert sw.elapsed(99.0) == 3.0
    assert sw.active(99.0) == 3.0


def test_pause_before_start_is_noop():
    sw = ScopeStopwatch()
    sw.pause(5.0)
    sw.start(10.0)
    assert sw.active(12.0) == 2.0


def test_start_resets_prior_accumulation():
    sw = ScopeStopwatch()
    sw.start(0.0)
    sw.stop(5.0)
    sw.start(100.0)        # restart from zero
    assert sw.elapsed(102.0) == 2.0
    assert sw.active(102.0) == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_stopwatch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluggable_protocol_tree.models.stopwatch'`. (This run also confirms the working test command for the rest of the plan.)

- [ ] **Step 3: Write minimal implementation**

```python
# pluggable_protocol_tree/models/stopwatch.py
"""Pause-aware stopwatch primitive for protocol status timing (issue #467).

Tracks two clocks for one scope (protocol / step / phase):

  * elapsed -- wall-clock since start; never freezes on pause.
  * active  -- excludes paused intervals; freezes between pause()/resume().

Every method takes ``now`` (a monotonic timestamp) rather than calling the
clock itself, so timing is fully deterministic under test. No Qt, no
threads.
"""


class ScopeStopwatch:
    __slots__ = ("_elapsed_anchor", "_elapsed_accum",
                 "_active_anchor", "_active_accum")

    def __init__(self):
        # monotonic when ticking began; None => stopped/never-started.
        self._elapsed_anchor = None
        self._elapsed_accum = 0.0
        # monotonic of current running segment; None => paused/stopped.
        self._active_anchor = None
        self._active_accum = 0.0

    def start(self, now):
        """(Re)start both clocks from zero; begin ticking and running."""
        self._elapsed_anchor = now
        self._elapsed_accum = 0.0
        self._active_anchor = now
        self._active_accum = 0.0

    def pause(self, now):
        """Freeze the active clock; elapsed keeps ticking."""
        if self._active_anchor is not None:
            self._active_accum += now - self._active_anchor
            self._active_anchor = None

    def resume(self, now):
        """Unfreeze the active clock. No-op if not started or already running."""
        if self._elapsed_anchor is not None and self._active_anchor is None:
            self._active_anchor = now

    def stop(self, now):
        """Freeze BOTH clocks at their current values."""
        if self._active_anchor is not None:
            self._active_accum += now - self._active_anchor
            self._active_anchor = None
        if self._elapsed_anchor is not None:
            self._elapsed_accum += now - self._elapsed_anchor
            self._elapsed_anchor = None

    def elapsed(self, now):
        """Wall-clock seconds since start (ignores pauses)."""
        running = 0.0 if self._elapsed_anchor is None else now - self._elapsed_anchor
        return self._elapsed_accum + running

    def active(self, now):
        """Active seconds since start (excludes paused intervals)."""
        running = 0.0 if self._active_anchor is None else now - self._active_anchor
        return self._active_accum + running
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_stopwatch.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/stopwatch.py pluggable_protocol_tree/tests/test_stopwatch.py
git commit -m "Add ScopeStopwatch timing primitive (issue #467)"
```

---

### Task 2: `ProtocolStatusModel`

**Files:**
- Create: `pluggable_protocol_tree/models/protocol_status.py`
- Test: `pluggable_protocol_tree/tests/test_protocol_status_model.py`

- [ ] **Step 1: Write the failing test**

```python
# pluggable_protocol_tree/tests/test_protocol_status_model.py
"""Unit tests for ProtocolStatusModel (pure, fake-clock, no Qt)."""
from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel


def test_protocol_start_sets_total_and_runs():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=3)
    assert m.step_total == 3
    assert m.step_index == 0
    assert m.running is True
    assert m.protocol_clock.elapsed(2.0) == 2.0


def test_step_start_increments_and_resets_phase():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=3)
    m.on_step_start(0.0, "Step A", "Step B")
    assert m.step_index == 1
    assert m.recent_step_name == "Step A"
    assert m.next_step_name == "Step B"
    assert m.phase_index == 0
    assert m.phase_total == 0
    assert m.step_clock.elapsed(1.0) == 1.0
    m.on_step_start(1.0, "Step B", "-")
    assert m.step_index == 2
    # step clock restarted at t=1.0
    assert m.step_clock.elapsed(3.0) == 2.0


def test_phase_start_sets_counts_and_target():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, "A", "-")
    m.on_phase_start(0.0, phase_index=2, phase_total=4, phase_target_s=1.5)
    assert m.phase_index == 2
    assert m.phase_total == 4
    assert m.phase_target_s == 1.5
    assert m.phase_clock.elapsed(0.5) == 0.5
    m.on_phase_extended(0.5)
    assert m.phase_target_s == 2.0


def test_pause_freezes_active_not_elapsed_all_scopes():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, "A", "-")
    m.on_phase_start(0.0, 1, 1, 1.0)
    m.pause(1.0)
    assert m.paused is True
    # elapsed keeps going, active frozen at 1.0
    assert m.protocol_clock.elapsed(5.0) == 5.0
    assert m.protocol_clock.active(5.0) == 1.0
    assert m.step_clock.active(5.0) == 1.0
    assert m.phase_clock.active(5.0) == 1.0
    m.resume(5.0)
    assert m.paused is False
    assert m.protocol_clock.active(6.0) == 2.0


def test_step_start_while_paused_keeps_active_frozen():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=2)
    m.on_step_start(0.0, "A", "B")
    m.pause(1.0)
    m.on_step_start(2.0, "B", "-")   # new step begins while paused
    # new step's active must not run until resume
    assert m.step_clock.active(4.0) == 0.0
    assert m.step_clock.elapsed(4.0) == 2.0
    m.resume(4.0)
    assert m.step_clock.active(5.0) == 1.0


def test_repetition_and_rep_chain():
    m = ProtocolStatusModel()
    m.on_repetition(1, 3)
    assert m.repeats_completed == 1
    assert m.repeats_total == 3
    m.set_rep_chain("rep 2/3 of 'Wash'")
    assert m.rep_chain_label == "rep 2/3 of 'Wash'"


def test_stop_freezes_all_and_clears_running():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=1)
    m.on_step_start(0.0, "A", "-")
    m.stop(3.0)
    assert m.running is False
    assert m.protocol_clock.elapsed(99.0) == 3.0
    assert m.step_clock.elapsed(99.0) == 3.0


def test_reset_restores_defaults():
    m = ProtocolStatusModel()
    m.on_protocol_start(0.0, step_total=5)
    m.on_step_start(0.0, "A", "B")
    m.reset()
    assert m.step_index == 0
    assert m.step_total == 0
    assert m.recent_step_name == "-"
    assert m.running is False
    assert m.protocol_clock.elapsed(9.0) == 0.0


def test_observers_fire_on_counter_change():
    m = ProtocolStatusModel()
    seen = []
    m.observe(lambda e: seen.append(e.new), "step_index")
    m.on_protocol_start(0.0, 2)
    m.on_step_start(0.0, "A", "B")
    assert 1 in seen
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_protocol_status_model.py -v`
Expected: FAIL with `ModuleNotFoundError: ... protocol_status`.

- [ ] **Step 3: Write minimal implementation**

```python
# pluggable_protocol_tree/models/protocol_status.py
"""HasTraits model for the protocol status bar (issue #467).

Holds the observable counters / names and three ScopeStopwatch clocks
(protocol / step / phase), and encapsulates the timing *rules* (a new step
resets the phase clock; pause freezes active but not elapsed; ...). Pure:
no Qt, no threads, no direct clock calls -- every timing method takes
``now`` so the model is unit-testable with a fake clock.

The view binds to the observable traits (discrete updates) and polls the
clocks for the continuously-changing time readouts. See
ProtocolStatusController for the executor-signal -> model wiring.
"""

from traits.api import Bool, Float, HasTraits, Instance, Int, Str

from pluggable_protocol_tree.models.stopwatch import ScopeStopwatch


class ProtocolStatusModel(HasTraits):
    # --- counters ---
    step_index = Int(0)
    step_total = Int(0)
    phase_index = Int(0)
    phase_total = Int(0)
    repeats_completed = Int(0)
    repeats_total = Int(1)

    # --- names / labels ---
    recent_step_name = Str("-")
    next_step_name = Str("-")
    rep_chain_label = Str("")

    # --- phase target (for the "elapsed / target" readout) ---
    phase_target_s = Float(0.0)

    # --- run state ---
    running = Bool(False)
    paused = Bool(False)

    # --- clocks (plain helpers; default-constructed per model) ---
    protocol_clock = Instance(ScopeStopwatch, ())
    step_clock = Instance(ScopeStopwatch, ())
    phase_clock = Instance(ScopeStopwatch, ())

    # --- rule methods ---

    def reset(self):
        self.trait_set(
            step_index=0, step_total=0, phase_index=0, phase_total=0,
            repeats_completed=0, repeats_total=1,
            recent_step_name="-", next_step_name="-", rep_chain_label="",
            phase_target_s=0.0, running=False, paused=False,
        )
        self.protocol_clock = ScopeStopwatch()
        self.step_clock = ScopeStopwatch()
        self.phase_clock = ScopeStopwatch()

    def on_protocol_start(self, now, step_total):
        self.reset()
        self.step_total = int(step_total)
        self.running = True
        self.protocol_clock.start(now)

    def on_step_start(self, now, recent_name, next_name):
        self.step_index += 1
        self.recent_step_name = recent_name
        self.next_step_name = next_name
        self.phase_index = 0
        self.phase_total = 0
        self.phase_target_s = 0.0
        self.step_clock.start(now)
        self.phase_clock = ScopeStopwatch()      # fresh, unstarted
        if self.paused:                          # started mid-pause: keep frozen
            self.step_clock.pause(now)

    def on_phase_start(self, now, phase_index, phase_total, phase_target_s):
        self.phase_index = int(phase_index)
        self.phase_total = int(phase_total)
        try:
            self.phase_target_s = float(phase_target_s)
        except (TypeError, ValueError):
            self.phase_target_s = 0.0
        self.phase_clock.start(now)
        if self.paused:
            self.phase_clock.pause(now)

    def on_phase_extended(self, extra_s):
        try:
            self.phase_target_s += float(extra_s)
        except (TypeError, ValueError):
            pass

    def pause(self, now):
        self.paused = True
        self.protocol_clock.pause(now)
        self.step_clock.pause(now)
        self.phase_clock.pause(now)

    def resume(self, now):
        self.paused = False
        self.protocol_clock.resume(now)
        self.step_clock.resume(now)
        self.phase_clock.resume(now)

    def on_repetition(self, completed, total):
        self.repeats_completed = int(completed)
        self.repeats_total = int(total)

    def set_rep_chain(self, label):
        self.rep_chain_label = label

    def stop(self, now):
        self.running = False
        self.paused = False
        self.protocol_clock.stop(now)
        self.step_clock.stop(now)
        self.phase_clock.stop(now)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_protocol_status_model.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/protocol_status.py pluggable_protocol_tree/tests/test_protocol_status_model.py
git commit -m "Add ProtocolStatusModel state + timing rules (issue #467)"
```

---

### Task 3: `ProtocolStatusController`

**Files:**
- Create: `pluggable_protocol_tree/services/protocol_status_controller.py`
- Test: `pluggable_protocol_tree/tests/test_protocol_status_controller.py`

The test uses tiny fakes for `qsignals` (a connectable signal) and `manager` (an execution-step iterator) — no Qt, no executor.

- [ ] **Step 1: Write the failing test**

```python
# pluggable_protocol_tree/tests/test_protocol_status_controller.py
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


def test_terminal_signals_stop():
    for term in ("protocol_finished", "protocol_aborted"):
        ctrl, sigs, clock, rows = _make()
        sigs.protocol_started.emit()
        getattr(sigs, term).emit()
        assert ctrl.model.running is False


def test_error_stops():
    ctrl, sigs, clock, rows = _make()
    sigs.protocol_started.emit()
    sigs.protocol_error.emit("boom")
    assert ctrl.model.running is False


def test_disconnect_stops_updates():
    ctrl, sigs, clock, rows = _make()
    ctrl.disconnect()
    sigs.protocol_started.emit()
    assert ctrl.model.step_total == 0   # not wired anymore
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_protocol_status_controller.py -v`
Expected: FAIL with `ModuleNotFoundError: ... protocol_status_controller`.

- [ ] **Step 3: Write minimal implementation**

```python
# pluggable_protocol_tree/services/protocol_status_controller.py
"""Links executor lifecycle signals to a ProtocolStatusModel (issue #467).

A small HasTraits adapter owned by the composition root (the dock pane in
the full app; the demo window standalone). It owns the model, connects one
slot per ExecutorSignals signal, and translates each into a single model
method call stamped with ``now``. No formatting, no widgets -- the view
binds to ``self.model`` separately.

Invariant: ExecutorSignals is a QObject delivering via queued connections,
so these slots run on the GUI thread; the model is therefore mutated only
on the GUI thread and its observers may drive widgets directly.
"""

import time

from traits.api import Any, Callable, HasTraits, Instance

from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel


class ProtocolStatusController(HasTraits):
    #: The status model this controller drives. The view binds to it.
    model = Instance(ProtocolStatusModel, ())

    #: ExecutorSignals QObject (duck-typed; any object exposing the
    #: signals works -- keeps Qt types out of the signature and tests Qt-free).
    qsignals = Any()

    #: RowManager -- needed for the step count and next-step name.
    manager = Any()

    #: Monotonic clock source; overridable in tests.
    clock = Callable(time.monotonic)

    def traits_init(self):
        self._connect()

    # --- wiring ---

    def _pairs(self):
        s = self.qsignals
        return (
            (s.protocol_started, self._on_protocol_started),
            (s.step_started, self._on_step_started),
            (s.step_repetition, self._on_step_repetition),
            (s.phase_started, self._on_phase_started),
            (s.phase_extended, self._on_phase_extended),
            (s.protocol_paused, self._on_paused),
            (s.protocol_resumed, self._on_resumed),
            (s.protocol_repetition_finished, self._on_repetition_finished),
            (s.protocol_finished, self._on_stopped),
            (s.protocol_aborted, self._on_stopped),
            (s.protocol_error, self._on_error),
        )

    def _connect(self):
        if self.qsignals is None:
            return
        for sig, slot in self._pairs():
            sig.connect(slot)

    def disconnect(self):
        if self.qsignals is None:
            return
        for sig, slot in self._pairs():
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    # --- slots (executor signal -> model) ---

    def _on_protocol_started(self):
        self.model.on_protocol_start(self.clock(), self._count_steps())

    def _on_step_started(self, row):
        self.model.on_step_start(self.clock(), row.name, self._next_name(row))

    def _on_step_repetition(self, rep_chain):
        self.model.set_rep_chain(self._fmt_chain(rep_chain))

    def _on_phase_started(self, phase_index, phase_total, phase_duration_s):
        self.model.on_phase_start(
            self.clock(), phase_index, phase_total, phase_duration_s)

    def _on_phase_extended(self, extra_s):
        self.model.on_phase_extended(extra_s)

    def _on_paused(self):
        self.model.pause(self.clock())

    def _on_resumed(self):
        self.model.resume(self.clock())

    def _on_repetition_finished(self, completed, total):
        self.model.on_repetition(completed, total)

    def _on_stopped(self):
        self.model.stop(self.clock())

    def _on_error(self, _msg):
        self.model.stop(self.clock())

    # --- helpers (need manager) ---

    def _count_steps(self):
        try:
            return sum(1 for _ in self.manager.iter_execution_steps())
        except Exception:
            return 0

    def _next_name(self, current):
        steps = self.manager.iter_execution_steps()
        cur_path = tuple(current.path)
        for row in steps:
            if tuple(row.path) == cur_path:
                nxt = next(steps, None)
                return nxt.name if nxt is not None else "-"
        return "-"

    @staticmethod
    def _fmt_chain(rep_chain):
        if not rep_chain:
            return ""
        return " · ".join(
            f"rep {idx}/{total} of '{name}'" for name, idx, total in rep_chain
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_protocol_status_controller.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/services/protocol_status_controller.py pluggable_protocol_tree/tests/test_protocol_status_controller.py
git commit -m "Add ProtocolStatusController wiring executor signals to model (issue #467)"
```

---

### Task 4: `StatusBar.bind(model)` + combined time fields

**Files:**
- Modify: `pluggable_protocol_tree/views/navigation_bar.py` (the `StatusBar` class, ~382-531)

No new automated test (pure-Qt view; verified via the demo-window test in Task 7 and manual run in Task 8). This task is a structural view change.

- [ ] **Step 1: Add a poll-interval constant near the top of `navigation_bar.py`**

Find the module-level constants area (near other `*_MS` / width constants) and add:

```python
STATUS_POLL_INTERVAL_MS = 100   # 10 Hz refresh for the live time readouts
```

- [ ] **Step 2: Ensure `QTimer` and `time` are imported**

At the top of `navigation_bar.py`, confirm/add:
```python
import time
from pyface.qt.QtCore import QTimer   # use the same Qt import style already in this file
```
(If the file already imports `QTimer`/`Qt` from a specific module, add `QTimer` to that existing import rather than a new line.)

- [ ] **Step 3: Widen the three time labels and set neutral initial text**

In `StatusBar.__init__`, replace the three label constructions:

```python
        self.lbl_total_time = QLabel("Total Time: 0 s")
        self.lbl_total_time.setFixedWidth(120)
        self.lbl_total_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_step_time = QLabel("Step Time: 0 s")
        self.lbl_step_time.setFixedWidth(115)
        self.lbl_step_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
```

with:

```python
        self.lbl_total_time = QLabel("Protocol 0.0s (act 0.0s)")
        self.lbl_total_time.setFixedWidth(190)
        self.lbl_total_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_step_time = QLabel("Step 0.0s (act 0.0s)")
        self.lbl_step_time.setFixedWidth(170)
        self.lbl_step_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
```

And change the phase label's initial text + width:

```python
        self.lbl_phase_time = QLabel("Phase 0/0  0.0s/0.0s (act 0.0s)")
        self.lbl_phase_time.setFixedWidth(260)
        self.lbl_phase_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_phase_time.setVisible(False)
```

- [ ] **Step 4: Add `_model`/`_poll_timer` attributes at the end of `__init__`**

At the very end of `StatusBar.__init__` (after `self._apply_styling()` / the colorScheme connect), add:

```python
        # Bound lazily via bind(); until then the labels show their
        # neutral initial text.
        self._model = None
        self._poll_timer = None
```

- [ ] **Step 5: Add the `bind` + refresh methods to `StatusBar`**

Add these methods to the `StatusBar` class (e.g. right after `_apply_styling`):

```python
    def bind(self, model):
        """Bind this status bar to a ProtocolStatusModel.

        Discrete traits (counters, names, rep-chain) drive label text via
        Traits observers; the continuously-changing time readouts are
        refreshed by a 10 Hz poll timer that runs only while a protocol is
        active. Safe to touch widgets in the observers: the model is mutated
        only on the GUI thread (see ProtocolStatusController)."""
        self._model = model
        if self._poll_timer is None:
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(STATUS_POLL_INTERVAL_MS)
            self._poll_timer.timeout.connect(self._refresh_times)

        model.observe(self._on_counts_changed,
                      "step_index, step_total, phase_index, phase_total")
        model.observe(self._on_repeats_changed,
                      "repeats_completed, repeats_total")
        model.observe(self._on_names_changed,
                      "recent_step_name, next_step_name, rep_chain_label")
        model.observe(self._on_running_changed, "running")

        self._refresh_counts()
        self._refresh_repeats()
        self._refresh_names()
        self._refresh_times()

    # --- observer handlers (discrete) ---

    def _on_counts_changed(self, event):
        self._refresh_counts()

    def _on_repeats_changed(self, event):
        self._refresh_repeats()

    def _on_names_changed(self, event):
        self._refresh_names()

    def _on_running_changed(self, event):
        if self._poll_timer is None:
            return
        if event.new:
            if not self._poll_timer.isActive():
                self._poll_timer.start()
        else:
            self._refresh_times()        # final freeze-frame
            self._poll_timer.stop()

    # --- refreshers ---

    def _refresh_counts(self):
        m = self._model
        if m is None:
            return
        self.lbl_step_progress.setText(f"Step {m.step_index}/{m.step_total}")

    def _refresh_repeats(self):
        m = self._model
        if m is None:
            return
        self.lbl_repeat_protocol_status.setText(f"{m.repeats_completed}/")

    def _refresh_names(self):
        m = self._model
        if m is None:
            return
        self.lbl_recent_step.setText(f"Most Recent Step: {m.recent_step_name}")
        self.lbl_next_step.setText(f"Next Step: {m.next_step_name}")
        if m.rep_chain_label:
            self.lbl_step_repetition.setText(m.rep_chain_label)
            self.lbl_step_repetition.setVisible(True)
        else:
            self.lbl_step_repetition.setText("")
            self.lbl_step_repetition.setVisible(False)

    def _refresh_times(self):
        m = self._model
        if m is None:
            return
        now = time.monotonic()
        self.lbl_total_time.setText(
            f"Protocol {m.protocol_clock.elapsed(now):.1f}s "
            f"(act {m.protocol_clock.active(now):.1f}s)"
        )
        self.lbl_step_time.setText(
            f"Step {m.step_clock.elapsed(now):.1f}s "
            f"(act {m.step_clock.active(now):.1f}s)"
        )
        if m.phase_total > 0:
            head = f"Phase {m.phase_index}/{m.phase_total}"
        elif m.phase_index > 0:
            head = f"Phase {m.phase_index}"
        else:
            head = "Phase"
        self.lbl_phase_time.setText(
            f"{head}  {m.phase_clock.elapsed(now):.1f}s/"
            f"{m.phase_target_s:.1f}s (act {m.phase_clock.active(now):.1f}s)"
        )
```

- [ ] **Step 6: Verify the file imports cleanly**

Run: `pixi run python -c "import pluggable_protocol_tree.views.navigation_bar"`
Expected: no output, exit 0.

- [ ] **Step 7: Commit**

```bash
git add pluggable_protocol_tree/views/navigation_bar.py
git commit -m "Add StatusBar.bind(model) + combined time fields (issue #467)"
```

---

### Task 5: Strip status logic from `ProtocolTreePane`

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py`

Goal: remove the embedded status state + display, KEEP every non-status responsibility. Work slot-by-slot. After this task the pane no longer updates the status bar by itself; Task 6 wires the controller that does.

- [ ] **Step 1: Remove the status state-vars block**

Delete these lines from `__init__` (currently ~246-273):
```python
        self._step_index = 0
        self._step_total = 0
        self._step_started_at: float | None = None
        self._phase_started_at: float | None = None
        self._phase_target: float | None = None
        self._phase_index = 0
        self._phase_total = 0
        self._current_row = None
        self._repeats_total = 1
        self._repeats_completed = 0
```
KEEP `self._current_run_preview_mode`, `self._pause_phases`, `self._pause_phase_idx`, `self._start_pending`, `self._wait_active` (non-status). Also delete the status label aliases:
```python
        self._status_step_label = self.status_bar.lbl_step_progress
        self._status_step_time_label = self.status_bar.lbl_step_time
        self._status_reps_label = self.status_bar.lbl_step_repetition
        self._status_phase_time_label = (
            self.status_bar.lbl_phase_time if self.phase_ack_topic is not None
            else None
        )
```
and the tick timer:
```python
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(STATUS_TICK_INTERVAL_MS)
        self._tick_timer.timeout.connect(self._refresh_status)
```

NOTE on `_repeats_total`/`_repeats_completed`: these feed `_update_repeat_status_label` / `_on_error`. They move to the model. In `_start_protocol_run` (~627-632) the lines
```python
        self._repeats_total = repeats
        self._repeats_completed = 0
        ...
        self._update_repeat_status_label()
```
become (the spin box value is the desired total; the model gets it once the run starts):
```python
        self._current_run_preview_mode = preview_mode
```
Delete `_update_repeat_status_label` (the model + StatusBar own the repeat label now) and remove its other call sites (`_on_error`). In `_on_error`, delete:
```python
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
```

- [ ] **Step 2: Trim `_on_protocol_started` to its non-status duties**

Replace (~409-419) with:
```python
    def _on_protocol_started(self):
        self._start_pending = False
        self.protocol_running_changed.emit(True)
        self._publish_protocol_running("True")
        logger.info("Protocol started")
```

- [ ] **Step 3: Trim `_on_step_started` to its non-status duties**

The slot is also connected to `widget.highlight_active_row` separately, so the pane's own `_on_step_started` keeps only what isn't status. Its current body is entirely status + the explanatory NOTE comment. Replace (~421-454) with:
```python
    def _on_step_started(self, row):
        # Row highlighting is wired separately (widget.highlight_active_row).
        # Status counters / timers are owned by ProtocolStatusController now.
        #
        # NOTE: we deliberately do NOT publish the static step view to the
        # DV here. RoutesHandler publishes a per-phase display for every
        # phase while a protocol runs, which is authoritative; publishing a
        # static row view here raced with phase 1 and cleared it.
        pass
```
(Keep the slot — it documents the deliberate no-op and remains a connection point. If the project lints against empty slots, leave the comment + `return`.)

- [ ] **Step 4: Reduce phase/step/repetition status slots to no-ops or remove**

Delete `_on_phase_started`, `_on_phase_extended`, `_on_step_repetition`, `_on_step_finished`, `_refresh_status`, and `_next_step_name` (all status-only; `_next_step_name` moved to the controller).

Then remove their signal connections in `_wire_executor_signals` (~360-370):
```python
        self.executor.qsignals.step_started.connect(self._on_step_started)
        self.executor.qsignals.step_finished.connect(self._on_step_finished)
        self.executor.qsignals.step_repetition.connect(self._on_step_repetition)
        ...
        self.executor.qsignals.phase_started.connect(self._on_phase_started)
        self.executor.qsignals.phase_extended.connect(self._on_phase_extended)
```
Keep `step_started.connect(self.widget.highlight_active_row)`. Keep the `_on_step_started` no-op connection only if you kept the slot; otherwise drop both the slot and its connect. Keep `protocol_started.connect(self._on_protocol_started)`, `protocol_error.connect(self._on_error)`, and the `protocol_wait_*` connections (loading screen — non-status).

- [ ] **Step 5: Check pause/resume + pause-phase code for status references**

`_on_protocol_paused` / `_on_protocol_resumed` (button-state machine) and the pause-phase navigation may reference removed vars (`_current_row`, `_phase_index`, `_phase_total`, `_phase_started_at`, `_tick_timer`). Grep and fix:

Run: `git grep -nE "_step_index|_step_total|_step_started_at|_phase_started_at|_phase_target|_phase_index|_phase_total|_current_row|_tick_timer|_refresh_status|_status_step_label|_status_step_time_label|_status_reps_label|_status_phase_time_label|_update_repeat_status_label|_next_step_name|_repeats_total|_repeats_completed" -- pluggable_protocol_tree/views/protocol_tree_pane.py`

For each remaining hit that is genuinely about **status display**, remove it. For any that the **pause-phase navigation** needs (e.g. it independently tracks the current row/phase to drive the phase nav buttons), keep that logic but give it its own private var that does NOT alias status (e.g. keep a local `self._nav_current_row` set where the pane needs it). If the pause-phase logic was *reusing* the old `_current_row`/`_phase_*` status vars, re-introduce minimal private vars for navigation only, set from the relevant signals the pane still listens to. Document why with a short comment.

Also remove the now-unused imports (`time`, `QTimer`, `STATUS_TICK_INTERVAL_MS`) if nothing else in the file uses them.

- [ ] **Step 6: Verify import + grep is clean**

Run: `pixi run python -c "import pluggable_protocol_tree.views.protocol_tree_pane"`
Expected: exit 0 (ImportError/NameError here means a missed reference — fix it).

- [ ] **Step 7: Commit**

```bash
git add pluggable_protocol_tree/views/protocol_tree_pane.py
git commit -m "Strip embedded status logic from ProtocolTreePane (issue #467)"
```

---

### Task 6: Wire the controller in the dock pane

**Files:**
- Modify: `pluggable_protocol_tree/views/dock_pane.py`

- [ ] **Step 1: Add the import + trait**

Add the import near the other `services` imports:
```python
from pluggable_protocol_tree.services.protocol_status_controller import (
    ProtocolStatusController,
)
```
Add the trait to `PluggableProtocolDockPane` (next to `protocol_state_tracker`):
```python
    status_controller = Instance(ProtocolStatusController)
```

- [ ] **Step 2: Instantiate + bind in `create_contents`**

In `create_contents`, after the `pane = ProtocolTreePane(...)` block and before `pane._seed_default_step_if_empty()`, add:
```python
        # The dock pane is the app's HasTraits composition root: it owns the
        # status controller that links the executor's Qt signals to the
        # status model, and binds the (view-only) status bar to that model.
        self.status_controller = ProtocolStatusController(
            qsignals=pane.executor.qsignals,
            manager=self.manager,
        )
        pane.status_bar.bind(self.status_controller.model)
```

- [ ] **Step 3: Verify import**

Run: `pixi run python -c "import pluggable_protocol_tree.views.dock_pane"`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add pluggable_protocol_tree/views/dock_pane.py
git commit -m "Dock pane owns ProtocolStatusController and binds status bar (issue #467)"
```

---

### Task 7: Migrate the demo window + its tests

**Files:**
- Modify: `pluggable_protocol_tree/demos/base_demo_window.py`
- Modify: `pluggable_protocol_tree/tests/test_base_demo_window.py`

- [ ] **Step 1: Build the controller in the demo window**

In `BasePluggableProtocolDemoWindow.__init__`, after `self.pane = ProtocolTreePane(...)` (just after the `phase_acked` wiring, ~228), add:
```python
        from pluggable_protocol_tree.services.protocol_status_controller import (
            ProtocolStatusController,
        )
        self.status_controller = ProtocolStatusController(
            qsignals=self.pane.executor.qsignals,
            manager=self.pane.manager,
        )
        self.pane.status_bar.bind(self.status_controller.model)
```

- [ ] **Step 2: Replace the removed status-internal properties with a model accessor**

Delete the properties that proxy removed pane internals (`_status_step_label`, `_status_step_time_label`, `_status_reps_label`, `_status_phase_time_label`, `_tick_timer`, `_step_index` [+setter], `_step_total` [+setter], `_step_started_at` [+setter], `_phase_started_at` [+setter], `_current_row` [+setter]) — base_demo_window.py ~449-507.

Keep `experiment_label` and `_on_protocol_terminated` (but see Step 3). Add one accessor so tests can reach the model and the live labels:
```python
    @property
    def status_model(self):
        return self.status_controller.model

    @property
    def status_bar(self):                 # already exists -- keep
        return self.pane.status_bar
```
(If `status_bar` already exists, don't duplicate it.)

- [ ] **Step 3: Fix `_on_protocol_terminated`**

The pane may still expose `_on_protocol_terminated`; if it does and it no longer resets status (status resets via the model on the next run / on `stop`), keep the demo-readout reset part only:
```python
    def _on_protocol_terminated(self):
        """Test hook -- pane terminator + reset demo readouts."""
        self.pane._on_protocol_terminated()
        for readout in self.config.status_readouts:
            slug = _slug(readout.label)
            label = self._readout_labels.get(slug)
            if label is not None:
                label.setText(f"{readout.label}: {readout.initial}")
```
(unchanged if `pane._on_protocol_terminated` still exists; if Task 5 removed it, drop the first line.)

- [ ] **Step 4: Rewrite the coupled tests in `test_base_demo_window.py`**

The pure timing/counter behaviors are already covered by `test_protocol_status_model.py` / `test_protocol_status_controller.py`. In `test_base_demo_window.py`, DELETE the tests that assert on removed internals:
- the `_status_step_label.text() == "Step 0/0"` assertion form (now `Step 0/0` text comes from the model bind; rewrite — see below),
- `test_window_tick_timer_runs_at_10_hz` (the pane tick timer is gone),
- the `_phase_started_at`/`_step_started_at`/`_current_row` manipulation tests,
- the elapsed-into-`_status_step_time_label` test,
- the `_tick_timer.isActive()` test.

REPLACE them with window-level tests that go through the model + bound labels. Example replacements (adapt to the file's existing fixtures/helpers):
```python
def test_status_bar_reflects_model_step_counter(qapp):
    w = _make_window()              # use the file's existing window factory
    w.status_model.on_protocol_start(0.0, step_total=3)
    w.status_model.on_step_start(0.0, "A", "B")
    qapp.processEvents()
    assert w.status_bar.lbl_step_progress.text() == "Step 1/3"


def test_status_bar_poll_timer_runs_only_while_running(qapp):
    w = _make_window()
    assert not w.status_bar._poll_timer.isActive()
    w.status_model.running = True
    qapp.processEvents()
    assert w.status_bar._poll_timer.isActive()
    w.status_model.running = False
    qapp.processEvents()
    assert not w.status_bar._poll_timer.isActive()


def test_status_bar_rep_chain_label(qapp):
    w = _make_window()
    w.status_model.set_rep_chain("rep 2/3 of 'Wash'")
    qapp.processEvents()
    assert w.status_bar.lbl_step_repetition.text() == "rep 2/3 of 'Wash'"
    w.status_model.set_rep_chain("")
    qapp.processEvents()
    assert w.status_bar.lbl_step_repetition.text() == ""
```
Keep all tests in the file that are unrelated to status (experiment label, readouts, navigation, etc.) unchanged.

- [ ] **Step 5: Run the demo-window test file**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_base_demo_window.py -v`
Expected: PASS (no references to removed internals; new status tests green). Fix any remaining `AttributeError` for removed members by routing through `status_model` / the bound labels.

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git commit -m "Migrate demo window + tests to status model/controller (issue #467)"
```

---

### Task 8: Full regression + manual smoke

**Files:** none (verification only).

- [ ] **Step 1: Run the new + migrated test files together**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_stopwatch.py pluggable_protocol_tree/tests/test_protocol_status_model.py pluggable_protocol_tree/tests/test_protocol_status_controller.py pluggable_protocol_tree/tests/test_base_demo_window.py -v`
Expected: all PASS.

- [ ] **Step 2: Run the broader pane/protocol-tree test subset to catch regressions**

Run: `pixi run pytest pluggable_protocol_tree/tests -k "not redis and not dropbot" -q`
Expected: no new failures vs. baseline. Investigate any failure referencing removed status members.

- [ ] **Step 3: Manual smoke (GUI)**

Run a demo that shows the status bar (e.g. `pixi run python -m pluggable_protocol_tree.demos.run_widget_auto`), start a protocol, and confirm: Protocol/Step/Phase time fields update live, active freezes on pause while elapsed keeps counting, Step n/N and Phase n/N advance, recent/next step + rep-chain update, and everything freezes at the final frame on completion.

- [ ] **Step 4: Final commit (if any manual-fix tweaks were needed)**

```bash
git add -A
git commit -m "Polish protocol status trackers after smoke test (issue #467)"
```

---

## Self-Review

- **Spec coverage:** elapsed×3 + active×3 (ScopeStopwatch elapsed/active × protocol/step/phase clocks — Tasks 1-2, displayed Task 4); Step n/N (model.step_index/total → lbl_step_progress); Phase n/N (model.phase_index/total → phase field); pause freezes active not elapsed (Task 2 tests); MVC separation (Tasks 2/3/4); dock pane as composition-root controller owner (Task 6); demo reuse (Task 7); deferred navigate-while-paused (explicitly out of scope, no task — correct).
- **Placeholder scan:** none — every code step has full code; integration steps name exact members and provide the replacement text.
- **Type/name consistency:** `ProtocolStatusModel`, `ProtocolStatusController`, `ScopeStopwatch`, method names (`on_protocol_start`, `on_step_start`, `on_phase_start`, `on_phase_extended`, `pause`, `resume`, `on_repetition`, `set_rep_chain`, `stop`, `reset`), clock methods (`start/pause/resume/stop/elapsed/active`), and view members (`bind`, `_poll_timer`, `lbl_step_progress`, `lbl_total_time`, `lbl_step_time`, `lbl_phase_time`, `lbl_step_repetition`) are consistent across tasks.
- **Risk note:** Task 5 Step 5 is the only judgement-heavy step (untangling pause-phase navigation from status vars); it is gated by an import check and the Task 8 regression subset.
