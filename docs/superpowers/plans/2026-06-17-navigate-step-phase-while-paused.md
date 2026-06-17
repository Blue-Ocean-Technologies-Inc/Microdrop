# Navigate step/phase while paused → resume from there — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** While a protocol is paused, let the operator navigate to a different step/phase so the counters/timers follow and **resume continues from there** with that step/phase timer reset.

**Architecture:** Approach A (cooperative resume-target). A Qt-free seek lives in the execution layer (`ProtocolContext.resume_target` + a pure `seek` helper); the executor consults it at its two pause checkpoints on resume. The status model gains `seek_step`/`seek_phase` rules; the controller gains `seek_to(...)`. `ProtocolTreePane` is thinned — its paused-phase-nav state moves into the controller. Different-step seek re-runs step hooks from a `start_phase_index`; same-step phase seek jumps the static phase loop in place (no hook rerun). Duration-mode precise phase-resume is deferred to #477.

**Tech Stack:** Python 3.13, Enthought Traits (Qt-free models), PySide6 (views), pytest (+ pytest-qt `qapp`), pixi env.

**Test command convention (this repo):** the env python crashes importing numpy directly; always go through pixi, headless Qt:
```bash
cd /c/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py
QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/<file> -q
```

---

## File structure

- Create `src/pluggable_protocol_tree/execution/seek.py` — pure seek resolution (`resolve_seek`, `seek_decision`). No Qt, no threads.
- Create `src/pluggable_protocol_tree/tests/test_seek.py` — pure tests for the above.
- Modify `src/pluggable_protocol_tree/models/protocol_status.py` — add `seek_step`, `seek_phase`.
- Modify `src/pluggable_protocol_tree/tests/test_protocol_status_model.py` — tests for the two new rules.
- Modify `src/pluggable_protocol_tree/services/protocol_status_controller.py` — add `executor` trait + `seek_to`, absorb phase materialization + `_publish_paused_phase`.
- Modify `src/pluggable_protocol_tree/tests/test_protocol_status_controller.py` — tests for `seek_to`.
- Modify `src/pluggable_protocol_tree/execution/step_context.py` — `ProtocolContext.resume_target`, `StepContext.start_phase_index`.
- Modify `src/pluggable_protocol_tree/execution/executor.py` — `seek()`, track active ctx + position, `_run_steps` redirect.
- Modify `src/pluggable_protocol_tree/builtins/routes_column.py` — static phase loop honors `start_phase_index` + loop-level pause/seek checkpoint.
- Modify `src/pluggable_protocol_tree/views/protocol_tree_pane.py` — thin the pane; delegate phase nav + step selection (while paused) to the controller.
- Modify `src/pluggable_protocol_tree/views/dock_pane.py` and `src/pluggable_protocol_tree/demos/base_demo_window.py` — pass `executor` to the controller.

---

## Task 1: Pure seek resolution helpers

**Files:**
- Create: `src/pluggable_protocol_tree/execution/seek.py`
- Test: `src/pluggable_protocol_tree/tests/test_seek.py`

- [ ] **Step 1: Write the failing tests**

```python
# src/pluggable_protocol_tree/tests/test_seek.py
from pluggable_protocol_tree.execution.seek import resolve_seek, seek_decision


def test_resolve_seek_finds_frame_index_and_clamps_phase():
    frames = [(0,), (1,), (2,)]
    # phase clamped to >= 0
    assert resolve_seek(frames, ((1,), 3)) == (1, 3)
    assert resolve_seek(frames, ((1,), -5)) == (1, 0)


def test_resolve_seek_missing_path_returns_none():
    assert resolve_seek([(0,), (1,)], ((9,), 0)) is None


def test_resolve_seek_none_target_returns_none():
    assert resolve_seek([(0,)], None) is None


def test_seek_decision_continue_when_no_target():
    assert seek_decision(None, (1,), 2) == ("continue", 2)


def test_seek_decision_jump_same_step():
    assert seek_decision(((1,), 4), (1,), 0) == ("jump", 4)


def test_seek_decision_abort_different_step():
    assert seek_decision(((2,), 1), (1,), 0) == ("abort", 1)
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_seek.py -q` (from `microdrop-py`)
Expected: FAIL — `ModuleNotFoundError: ...execution.seek`.

- [ ] **Step 3: Write the implementation**

```python
# src/pluggable_protocol_tree/execution/seek.py
"""Pure (Qt-free, thread-free) seek resolution for mid-run navigation (#471).

A seek target is ``(step_path, phase_index)``. ``resolve_seek`` maps it to a
frame index in execution order; ``seek_decision`` tells a phase loop what to do
on resume given the current position. Both are pure so they unit-test without
the executor, threads, or Qt.
"""

from typing import List, Optional, Tuple

Path = Tuple[int, ...]


def resolve_seek(frame_paths: List[Path], target) -> Optional[Tuple[int, int]]:
    """Return ``(frame_index, phase_index)`` for ``target`` ((path, phase)), or
    None if target is None or its path is not among ``frame_paths``. The phase
    index is clamped to >= 0 (upper clamping is the phase loop's job — it knows
    the materialized phase count)."""
    if target is None:
        return None
    target_path, target_phase = target
    target_path = tuple(target_path)
    for i, path in enumerate(frame_paths):
        if tuple(path) == target_path:
            return i, max(0, int(target_phase))
    return None


def seek_decision(resume_target, current_path: Path, current_phase_index: int):
    """Decide what a phase loop should do at its pause checkpoint on resume.

    Returns one of:
      ``("continue", current_phase_index)`` — no seek pending,
      ``("jump", target_phase)``           — same step, jump the phase loop,
      ``("abort", target_phase)``          — different step, unwind to the
                                             frame walk and re-enter the target.
    """
    if resume_target is None:
        return ("continue", current_phase_index)
    target_path, target_phase = resume_target
    if tuple(target_path) == tuple(current_path):
        return ("jump", int(target_phase))
    return ("abort", int(target_phase))
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_seek.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pluggable_protocol_tree/execution/seek.py src/pluggable_protocol_tree/tests/test_seek.py
git commit -m "Add pure seek-resolution helpers for mid-run navigation (#471)"
```

---

## Task 2: Status model seek rules

**Files:**
- Modify: `src/pluggable_protocol_tree/models/protocol_status.py` (add after `on_phase_start`, ~line 92)
- Test: `src/pluggable_protocol_tree/tests/test_protocol_status_model.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to src/pluggable_protocol_tree/tests/test_protocol_status_model.py
from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel


def test_seek_step_sets_index_and_resets_step_timer_frozen_while_paused():
    m = ProtocolStatusModel()
    m.on_protocol_start(now=0.0, step_total=5)
    m.on_step_start(now=0.0, recent_name="A", next_name="B")   # step_index=1
    m.on_step_start(now=1.0, recent_name="B", next_name="C")   # step_index=2
    m.pause(now=2.0)
    m.seek_step(now=2.0, step_index=4, recent_name="D", next_name="E")
    assert m.step_index == 4                      # set, not incremented
    assert m.recent_step_name == "D"
    assert m.phase_index == 0 and m.phase_total == 0
    # step timer reset to 0 and frozen (paused) — read later, still 0
    assert m.step_clock.elapsed(now=9.0) == 0.0
    assert m.step_clock.active(now=9.0) == 0.0


def test_seek_phase_resets_phase_timer_frozen_while_paused():
    m = ProtocolStatusModel()
    m.on_protocol_start(now=0.0, step_total=1)
    m.on_step_start(now=0.0, recent_name="A", next_name="-")
    m.on_phase_start(now=0.0, phase_index=1, phase_total=4, phase_target_s=2.0)
    m.pause(now=1.0)
    m.seek_phase(now=1.0, phase_index=3, phase_total=4, phase_target_s=2.0)
    assert m.phase_index == 3 and m.phase_total == 4
    assert m.phase_clock.elapsed(now=9.0) == 0.0
    assert m.phase_clock.active(now=9.0) == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_protocol_status_model.py -q -k seek`
Expected: FAIL — `AttributeError: 'ProtocolStatusModel' object has no attribute 'seek_step'`.

- [ ] **Step 3: Write the implementation**

Add to `ProtocolStatusModel` (after `on_phase_start`):

```python
    def seek_step(self, now, step_index, recent_name, next_name):
        """Navigate to an arbitrary step while paused: SET the counter (not
        increment), reset the phase scope, and reset the step timer. Seek only
        happens while paused, so the fresh step clock is started then paused so
        both elapsed and active read 0 until resume."""
        self.step_index = int(step_index)
        self.recent_step_name = recent_name
        self.next_step_name = next_name
        self.phase_index = 0
        self.phase_total = 0
        self.phase_target_s = 0.0
        self.step_clock = ScopeStopwatch()
        self.step_clock.start(now)
        self.phase_clock = ScopeStopwatch()      # fresh, unstarted
        if self.paused:
            self.step_clock.pause(now)

    def seek_phase(self, now, phase_index, phase_total, phase_target_s):
        """Navigate to an arbitrary phase while paused: SET the counters and
        reset the phase timer (elapsed AND active), frozen while paused."""
        self.phase_index = int(phase_index)
        self.phase_total = int(phase_total)
        try:
            self.phase_target_s = float(phase_target_s)
        except (TypeError, ValueError):
            self.phase_target_s = 0.0
        self.phase_clock = ScopeStopwatch()
        self.phase_clock.start(now)
        if self.paused:
            self.phase_clock.pause(now)
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_protocol_status_model.py -q`
Expected: PASS (all model tests).

- [ ] **Step 5: Commit**

```bash
git add src/pluggable_protocol_tree/models/protocol_status.py src/pluggable_protocol_tree/tests/test_protocol_status_model.py
git commit -m "Add seek_step/seek_phase rules to ProtocolStatusModel (#471)"
```

---

## Task 3: Controller seek orchestration

**Files:**
- Modify: `src/pluggable_protocol_tree/services/protocol_status_controller.py`
- Test: `src/pluggable_protocol_tree/tests/test_protocol_status_controller.py`

Background: the controller already holds `model`, `qsignals`, `manager`, `clock`. Add an `executor` trait and a `seek_to`. `seek_to` resolves the step index + next name from the manager, materializes the target step's phases via `iter_phases` to get `phase_total`/target, calls `executor.seek`, then `model.seek_step` (if the step changed) and `model.seek_phase`.

- [ ] **Step 1: Write the failing test**

```python
# append to src/pluggable_protocol_tree/tests/test_protocol_status_controller.py
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


def test_seek_to_calls_executor_and_updates_model(monkeypatch):
    # One step at path (0,) with no routes -> iter_phases yields a single phase.
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_protocol_status_controller.py -q -k seek_to`
Expected: FAIL — `seek_to` / `executor` not defined.

- [ ] **Step 3: Write the implementation**

In `protocol_status_controller.py`: add the import and the `executor` trait, then `seek_to` + helpers.

```python
# at top, with the other imports
from pluggable_protocol_tree.services.phase_math import iter_phases
```

```python
# add trait beside manager
    #: ProtocolExecutor -- needed to record the resume target for a seek.
    executor = Any()
```

```python
# add methods (after _next_name)
    def _step_index_of(self, step_path):
        """1-based position of step_path in execution order, or 0 if absent."""
        target = tuple(step_path)
        for i, row in enumerate(self.manager.iter_execution_steps(), start=1):
            if tuple(row.path) == target:
                return i
        return 0

    def _row_at(self, step_path):
        target = tuple(step_path)
        for row in self.manager.iter_execution_steps():
            if tuple(row.path) == target:
                return row
        return None

    @staticmethod
    def _phase_total_for(row):
        """Materialized phase count for a row (count/fixed steps). Duration-mode
        precise phases are deferred (#477); fall back to 1 on any failure."""
        try:
            phases = list(iter_phases(
                static_electrodes=list(getattr(row, "electrodes", []) or []),
                routes=list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                soft_start=bool(getattr(row, "soft_start", False)),
                soft_end=bool(getattr(row, "soft_end", False)),
                repeat_duration_s=0.0,
                linear_repeats=bool(getattr(row, "linear_repeats", False)),
                n_repeats=int(getattr(row, "route_repetitions", 1)),
                step_duration_s=float(getattr(row, "duration_s", 1.0)),
            ))
            return max(1, len(phases))
        except Exception:
            return 1

    def seek_to(self, step_path, phase_index):
        """Navigate (while paused) to ``(step_path, phase_index)`` — 0-based
        phase. Records the resume target on the executor and updates the model
        so the counters/timers follow. No-op if the path is gone."""
        row = self._row_at(step_path)
        if row is None:
            return
        now = self.clock()
        step_idx = self._step_index_of(step_path)
        phase_total = self._phase_total_for(row)
        # clamp phase to [0, phase_total-1]; model phases are 1-based.
        phase0 = max(0, min(int(phase_index), phase_total - 1))

        if self.executor is not None:
            self.executor.seek(tuple(step_path), phase0)

        if step_idx != self.model.step_index:
            self.model.seek_step(now, step_idx, row.name, self._next_name(row))
        self.model.seek_phase(
            now, phase0 + 1, phase_total, float(getattr(row, "duration_s", 0.0)))
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_protocol_status_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pluggable_protocol_tree/services/protocol_status_controller.py src/pluggable_protocol_tree/tests/test_protocol_status_controller.py
git commit -m "Add seek_to orchestration to ProtocolStatusController (#471)"
```

---

## Task 4: Execution-context seek state

**Files:**
- Modify: `src/pluggable_protocol_tree/execution/step_context.py`

Add `resume_target` to `ProtocolContext` and `start_phase_index` to `StepContext`. No new tests (pure trait additions exercised via Tasks 5–6); a quick import smoke check guards typos.

- [ ] **Step 1: Add the traits**

In `ProtocolContext` (after `pre_protocol_wait_s`):

```python
    # Mid-run seek target (issue #471): (step_path, phase_index) or None.
    # Set by ProtocolExecutor.seek() while paused; consulted at the pause
    # checkpoints on resume via execution.seek.seek_decision. Plain attribute
    # semantics are fine — a single GUI-thread write, worker-thread read.
    resume_target = Any(None)
```

In `StepContext` (after `step_phases_done_event`):

```python
    start_phase_index = Int(0,
        desc="0-based phase to begin this step at. Non-zero only when the "
             "executor re-enters a step after a different-step seek (#471).")
```

Add `Int` to the traits import on line 115:
```python
from traits.api import Any, Bool, Dict, Float, HasTraits, Instance, Str, List, Int
```

- [ ] **Step 2: Smoke-check the import**

Run: `cd /c/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run python -c "from pluggable_protocol_tree.execution.step_context import ProtocolContext, StepContext; ProtocolContext(); print(StepContext().start_phase_index)"`
Expected: prints `0`.

- [ ] **Step 3: Commit**

```bash
git add src/pluggable_protocol_tree/execution/step_context.py
git commit -m "Add resume_target / start_phase_index to execution contexts (#471)"
```

---

## Task 5: Executor seek + frame-walk redirect

**Files:**
- Modify: `src/pluggable_protocol_tree/execution/executor.py`

Add the `seek()` method, track the live `ProtocolContext` and current position, and make `_run_steps` honor the resume target (different-step redirect → re-enter target frame with `start_phase_index`).

- [ ] **Step 1: Add seek state + method**

Add traits beside `_start_step_path` (~line 79):

```python
    # Live ProtocolContext for the current run; seek() writes resume_target on
    # it. None between runs.
    _active_proto_ctx = Any
    # Position the frame walk last reported (path tuple) — used to decide
    # same-step vs different-step on resume.
    _current_step_path = Union(None, Tuple)
```

Add the public method beside `pause`/`resume` (~line 190):

```python
    def seek(self, step_path, phase_index) -> None:
        """Record a mid-run resume target (issue #471). Only meaningful while
        paused; ignored otherwise. The frame walk / phase loop consult it on
        resume. Qt-free: writes a plain tuple onto the live ProtocolContext."""
        if not self.pause_event.is_set():
            return
        if self._active_proto_ctx is not None:
            self._active_proto_ctx.resume_target = (tuple(step_path),
                                                    int(phase_index))
```

- [ ] **Step 2: Store the live ctx in run()**

In `run()`, right after `proto_ctx = ProtocolContext(...)` is built (~line 214), add:

```python
        self._active_proto_ctx = proto_ctx
```

And in the `finally:` block of `run()` (~line 292), clear it:

```python
            self._active_proto_ctx = None
```

- [ ] **Step 3: Make `_run_steps` seek-aware**

Replace the frame loop body's pause block and add the redirect. The current loop (lines 316–334) walks frames and blocks at the top. Rework the frame walk so that, after a pause→resume, a pending `resume_target` for a **different** step restarts the walk at that frame with a `start_phase_index`.

```python
    def _run_steps(self, handlers, cols, proto_ctx, skip_until) -> None:
        """Run one repetition. Honors stop_event, pause_event (step + phase
        checkpoints), skip_until (start-of-run), and resume_target (#471
        mid-run seek)."""
        frames = list(self.row_manager.iter_execution_frames())
        frame_paths = [tuple(row.path) for row, _ in frames]

        i = 0
        step_index = 0
        start_phase_index = 0
        if skip_until is not None:
            # Generalised skip: jump to the first frame matching skip_until.
            for j, p in enumerate(frame_paths):
                if p == skip_until:
                    i = j
                    break
            else:
                return  # skip target absent -> nothing to run

        while i < len(frames):
            if self.stop_event.is_set():
                break
            row, rep_chain = frames[i]
            self._current_step_path = tuple(row.path)

            if self.pause_event.is_set():
                logger.info(f"Protocol paused at step {step_index + 1}")
                self.qsignals.protocol_paused.emit()
                self.pause_event.wait_cleared()
                if self.stop_event.is_set():
                    break
                self.qsignals.protocol_resumed.emit()
                logger.info("Protocol resumed")
                # On resume, honor a mid-run seek to a DIFFERENT step here at
                # the step boundary (same-step seeks are handled inside the
                # phase loop). resolve_seek clamps + locates the target frame.
                target = proto_ctx.resume_target
                resolved = resolve_seek(frame_paths, target)
                if resolved is not None and tuple(target[0]) != tuple(row.path):
                    i, start_phase_index = resolved
                    proto_ctx.resume_target = None
                    step_index = i  # keep the counter roughly aligned
                    continue

            step_index += 1
            self._run_one_frame(handlers, cols, proto_ctx, row, rep_chain,
                                step_index, start_phase_index)
            start_phase_index = 0

            # A seek raised DURING the step (different step) aborts the phase
            # loop; redirect from here.
            target = proto_ctx.resume_target
            resolved = resolve_seek(frame_paths, target)
            if resolved is not None:
                i, start_phase_index = resolved
                proto_ctx.resume_target = None
                step_index = i
                continue
            i += 1
```

Extract the existing per-frame body (lines 336–366) into `_run_one_frame`, adding `start_phase_index` onto the step ctx:

```python
    def _run_one_frame(self, handlers, cols, proto_ctx, row, rep_chain,
                       step_index, start_phase_index) -> None:
        step_started_at = time.monotonic()
        rep_str = (
            " | " + ", ".join(f"rep {i}/{n} of {name!r}"
                              for name, i, n in rep_chain)
            if rep_chain else ""
        )
        logger.info(
            f"Step {step_index} started: {row.name!r} "
            f"(path {row.dotted_path()}, "
            f"duration_s={getattr(row, 'duration_s', None)}){rep_str}"
        )
        step_ctx = self._build_step_ctx(row, cols, proto_ctx)
        step_ctx.start_phase_index = int(start_phase_index)
        set_active_step(step_ctx)
        try:
            self.qsignals.step_repetition.emit(rep_chain)
            self.qsignals.step_started.emit(row)
            self._run_hooks("on_pre_step",  handlers, step_ctx, row)
            self._run_hooks("on_step",      handlers, step_ctx, row)
            self._run_hooks("on_post_step", handlers, step_ctx, row)
            self.qsignals.step_finished.emit(row)
        finally:
            clear_active_step()
        logger.info(
            f"Step {step_index} finished: {row.name!r} in "
            f"{time.monotonic() - step_started_at:.2f}s"
        )
```

Add the import near the top of `executor.py`:
```python
from pluggable_protocol_tree.execution.seek import resolve_seek
```

- [ ] **Step 4: Smoke-check + run existing executor tests**

Run: `cd /c/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/ -q -k "executor or end_to_end"`
Expected: PASS (no regression in existing executor/e2e tests — the no-seek path is unchanged behavior).

- [ ] **Step 5: Commit**

```bash
git add src/pluggable_protocol_tree/execution/executor.py
git commit -m "Executor: mid-run seek state + frame-walk redirect on resume (#471)"
```

---

## Task 6: Routes phase loop — start_phase_index + same-step jump

**Files:**
- Modify: `src/pluggable_protocol_tree/builtins/routes_column.py` (static path in `on_step`, ~lines 380–403)

Make the static (materialized) phase loop start at `ctx.start_phase_index`, and on a pause→resume within the loop consult `seek_decision`: same-step → jump to the target phase index; different-step → return (abort) so the executor's frame walk redirects.

- [ ] **Step 1: Rework the static loop**

Replace the `for phase_idx, phase in enumerate(phases, start=1):` block with an index-driven loop that owns the pause/seek checkpoint:

```python
            from pluggable_protocol_tree.execution.seek import seek_decision
            total_phases = len(phases)
            phase_i = max(0, min(int(getattr(ctx, "start_phase_index", 0)),
                                 max(0, total_phases - 1)))
            seek_abort = False
            while phase_i < total_phases:
                if stop_event.is_set():
                    break
                # Pause/seek checkpoint at the phase boundary (this replaces
                # _run_phase's internal pause block for the static path; pass
                # honor_pause=False so it doesn't block again).
                if pause_event.is_set():
                    pause_event.wait_cleared()
                    if stop_event.is_set():
                        break
                    action, target_phase = seek_decision(
                        ctx.protocol.resume_target, tuple(row.path), phase_i)
                    if action == "jump":
                        ctx.protocol.resume_target = None
                        phase_i = max(0, min(target_phase, total_phases - 1))
                        continue
                    if action == "abort":
                        seek_abort = True
                        break
                if not self._run_phase(
                        phases[phase_i], ctx=ctx, mapping=mapping,
                        static_routes=routes, step_uuid=step_uuid,
                        step_label=step_label, preview_mode=preview_mode,
                        per_phase_dwell=per_phase_dwell, stop_event=stop_event,
                        pause_event=pause_event, qsignals=qsignals,
                        phase_index=phase_i + 1, phase_total=total_phases,
                        hold_for_buffer=phase_hold, honor_pause=False):
                    break
                phase_i += 1
            if seek_abort:
                # Leave resume_target set; the executor's frame walk redirects.
                ctx.step_phases_done_event.set()
                return
```

- [ ] **Step 2: Add `honor_pause` to `_run_phase`**

`_run_phase` currently always blocks on pause (lines 160–163). Add a `honor_pause: bool = True` kwarg so the static loop (which now owns the checkpoint) can skip the internal block. The dynamic-duration path keeps `honor_pause=True` (default) — duration-mode seek is deferred (#477).

Change the signature (line 129–132) to add `honor_pause=True`, and guard the pause block (line 160):

```python
        if honor_pause and pause_event.is_set():
            pause_event.wait_cleared()
            if stop_event.is_set():
                return False
```

- [ ] **Step 3: Run existing routes/e2e tests**

Run: `cd /c/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/ -q -k "routes or phase or end_to_end"`
Expected: PASS — the default no-seek, start_phase_index=0 path reproduces the prior loop (phases run 1..N, pause blocks once).

- [ ] **Step 4: Manual integration check**

Run the widget demo, start a protocol, Pause mid-run, click Next Phase a few times and select a different step, then Resume. Confirm: counters follow, the chosen step/phase timer shows 0 then ticks on resume, and playback continues from the chosen position. (Document any deviation; this is the threaded path the unit tests can't cover.)

- [ ] **Step 5: Commit**

```bash
git add src/pluggable_protocol_tree/builtins/routes_column.py
git commit -m "Routes: honor start_phase_index + same-step phase jump on resume (#471)"
```

---

## Task 7: Thin the pane — delegate nav to the controller

**Files:**
- Modify: `src/pluggable_protocol_tree/services/protocol_status_controller.py`
- Modify: `src/pluggable_protocol_tree/views/protocol_tree_pane.py`

The pane currently owns paused-phase state (`_pause_phases`, `_pause_phase_idx`, `_compute_pause_phase_state`, `_publish_paused_phase`, `_update_phase_nav_buttons`). The phase materialization + display/hardware publish move into the controller; the pane's nav handlers become controller calls. Step navigation while paused reuses the existing step-cursor buttons (enabled only while paused), seeking via `_select_step` and suppressing the at-end "duplicate" behavior.

- [ ] **Step 1: Controller — materialize phases + publish display/hardware**

Add to the top imports of `protocol_status_controller.py`:

```python
import json

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    ELECTRODE_TO_CHANNEL_KEY, ELECTRODES_STATE_CHANGE,
    PROTOCOL_TREE_DISPLAY_STATE,
)
from pluggable_protocol_tree.models.display_state import ProtocolTreeDisplayMessage
from pluggable_protocol_tree.services.phase_math import iter_phases
```

Add a module logger after the imports:

```python
logger = get_logger(__name__)
```

Replace the Task 3 `_phase_total_for` staticmethod with a list-returning helper and a thin total wrapper, and add `preview_phase`:

```python
    @staticmethod
    def _phases_for(row):
        """Materialized phase sequence for a row, mirroring the executor's
        iter_phases call (count/fixed steps). [] on failure. Duration-mode
        precise phases are deferred (#477)."""
        try:
            in_duration_mode = (
                bool(getattr(row, "repeat_duration_controls", False))
                and float(getattr(row, "repeat_duration", 0.0) or 0.0) > 0
            )
            return list(iter_phases(
                static_electrodes=list(getattr(row, "electrodes", []) or []),
                routes=list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                soft_start=bool(getattr(row, "soft_start", False)),
                soft_end=bool(getattr(row, "soft_end", False)),
                repeat_duration_s=(float(getattr(row, "repeat_duration", 0.0))
                                   if in_duration_mode else 0.0),
                linear_repeats=bool(getattr(row, "linear_repeats", False)),
                n_repeats=int(getattr(row, "route_repetitions", 1)),
                step_duration_s=float(getattr(row, "duration_s", 1.0)),
            ))
        except Exception:
            return []

    def _phase_total_for(self, row):
        return max(1, len(self._phases_for(row)))

    def preview_phase(self, step_path, phase_index, preview):
        """Publish the selected phase's electrodes to the DV overlay (always)
        and to hardware (unless ``preview``) while paused. ``phase_index`` is
        0-based. Best-effort — publish failures are logged, never raised. This
        is the body lifted from the pane's old ``_publish_paused_phase``."""
        row = self._row_at(step_path)
        if row is None:
            return
        phases = self._phases_for(row)
        if not phases:
            return
        idx = max(0, min(int(phase_index), len(phases) - 1))
        try:
            mapping = self.manager.protocol_metadata.get(
                ELECTRODE_TO_CHANNEL_KEY, {})
        except Exception:
            mapping = {}
        electrodes = sorted(phases[idx])
        channels = sorted(mapping[e] for e in electrodes if e in mapping)
        display_msg = ProtocolTreeDisplayMessage(
            electrodes=electrodes,
            routes=list(getattr(row, "routes", []) or []),
            step_id=getattr(row, "uuid", "") or "",
            step_label=f"Step {row.dotted_path()}",
            free_mode=False,
            editable=False,
        )
        try:
            publish_message(topic=PROTOCOL_TREE_DISPLAY_STATE,
                            message=display_msg.serialize())
        except Exception as e:
            logger.warning(f"seek display publish failed: {e}")
        if not preview:
            try:
                publish_message(
                    topic=ELECTRODES_STATE_CHANGE,
                    message=json.dumps(
                        {"electrodes": electrodes, "channels": channels}))
            except Exception as e:
                logger.warning(f"seek hardware publish failed: {e}")
```

Note: `seek_to` (Task 3) already calls `self._phase_total_for(row)`; it now resolves to the instance method above with no signature change at the call site. `seek_to` stays publish-free so its pure unit test (Task 3) is unaffected — the pane calls `preview_phase` separately.

- [ ] **Step 2: Pane — declarations (lines ~247-250)**

Replace:
```python
        self._current_row = None
        self._current_run_preview_mode = False
        self._pause_phases: list = []
        self._pause_phase_idx: int = 0
```
with:
```python
        self._current_row = None
        self._current_run_preview_mode = False
        self.status_controller = None  # set by the composition root (#471)
```

- [ ] **Step 3: Pane — pause/resume enable step buttons (lines ~550-567)**

Replace `_on_protocol_paused`:
```python
    def _on_protocol_paused(self):
        logger.info("Protocol paused")
        self.navigation_bar.show_resume_state()
        if self._wait_active:
            self.loading_overlay.pause()
        # Enable step-cursor navigation while paused so the operator can seek
        # to a different step (#471).
        nb = self.navigation_bar
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(True)
        if self._current_row is not None:
            nb.split_play_button_to_phase_controls()
            self._update_phase_nav_buttons()
```
Replace `_on_protocol_resumed`:
```python
    def _on_protocol_resumed(self):
        logger.info("Protocol resumed")
        self.navigation_bar.show_pause_state()
        if self._wait_active:
            self.loading_overlay.resume()
        nb = self.navigation_bar
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(False)
        nb.merge_phase_controls_to_play_button()
```

- [ ] **Step 4: Pane — remove the moved phase machinery**

Delete `_compute_pause_phase_state` (lines ~692-709) and `_publish_paused_phase` (lines ~724-766) entirely. In `_on_protocol_terminated`, delete the two lines (lines ~595-596):
```python
        self._pause_phases = []
        self._pause_phase_idx = 0
```

- [ ] **Step 5: Pane — phase nav handlers become seeks (lines ~711-722)**

Replace `_on_prev_phase` / `_on_next_phase`:
```python
    def _on_prev_phase(self):
        self._seek_relative_phase(-1)

    def _on_next_phase(self):
        self._seek_relative_phase(+1)

    def _seek_relative_phase(self, delta):
        sc = self.status_controller
        if sc is None or self._current_row is None:
            return
        # model.phase_index is 1-based; seek_to takes 0-based.
        target0 = (sc.model.phase_index - 1) + delta
        path = tuple(self._current_row.path)
        sc.seek_to(path, target0)
        sc.preview_phase(path, target0, self._current_run_preview_mode)
        self._update_phase_nav_buttons()
```

- [ ] **Step 6: Pane — `_update_phase_nav_buttons` reads the model (lines ~768-776)**

Replace with:
```python
    def _update_phase_nav_buttons(self):
        m = self.status_controller.model if self.status_controller else None
        if m is None:
            self.navigation_bar.set_phase_navigation_enabled(False, False)
            return
        prev_enabled = m.phase_index > 1
        next_enabled = 0 < m.phase_index < m.phase_total
        self.navigation_bar.set_phase_navigation_enabled(prev_enabled, next_enabled)
```

- [ ] **Step 7: Pane — `_select_step` seeks while paused (lines ~881-886)**

Replace `_select_step` with:
```python
    @attempt_func_execution_with_error_dialog
    def _select_step(self, row):
        self.widget.set_current_row(row)
        # While paused, selecting a step seeks the run to it (#471). Update
        # _current_row so subsequent phase-nav targets the navigated step.
        sc = self.status_controller
        if sc is not None and sc.model.paused:
            self._current_row = row
            path = tuple(row.path)
            sc.seek_to(path, 0)
            sc.preview_phase(path, 0, self._current_run_preview_mode)
            self._update_phase_nav_buttons()
```

- [ ] **Step 8: Pane — don't duplicate at end while paused (lines ~821-822)**

Replace the tail of `navigate_to_next_step`:
```python
        logger.info(f"Nav: next at end — duplicating [{steps[cur].dotted_path()}]")
        self._duplicate_step_after(steps[cur])
```
with:
```python
        # While paused the step buttons are seek controls — never duplicate.
        if self.status_controller is not None and self.status_controller.model.paused:
            return
        logger.info(f"Nav: next at end — duplicating [{steps[cur].dotted_path()}]")
        self._duplicate_step_after(steps[cur])
```

- [ ] **Step 9: Run pane/window tests (migrate any that asserted removed internals)**

Run: `cd /c/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/ -q -k "pane or demo_window or navigation or status"`
Expected: PASS. Any test asserting `_pause_phases` / `_pause_phase_idx` / `_compute_pause_phase_state` / `_publish_paused_phase` is migrated to drive `status_controller` and assert `status_controller.model` (or deleted if superseded by Tasks 1-3 unit tests).

- [ ] **Step 10: Manual integration check (DV-sync ordering)**

Pause mid-run; use Prev/Next Phase and the step buttons to navigate; resume. Confirm counters follow, the chosen step/phase timer reads 0 then ticks on resume, and playback continues from the chosen position. Note specifically: `_select_step` fires `currentChanged`, which the device-viewer sync also reacts to — verify `preview_phase` (published right after) is the last word on the DV overlay. If the sync overwrites it, gate the sync's `currentChanged` publish while `model.paused` (follow-up note, not a blocker for the executor seek itself).

- [ ] **Step 11: Commit**

```bash
git add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/services/protocol_status_controller.py
git commit -m "Thin pane: delegate paused step/phase navigation to the status controller (#471)"
```

---

## Task 8: Wire executor into the controller at the composition roots

**Files:**
- Modify: `src/pluggable_protocol_tree/views/dock_pane.py`
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py`

- [ ] **Step 1: Pass executor + set controller on the pane (dock pane)**

In `PluggableProtocolDockPane.create_contents`, update the controller construction:

```python
        self.status_controller = ProtocolStatusController(
            qsignals=pane.executor.qsignals,
            manager=self.manager,
            executor=pane.executor,
        )
        pane.status_controller = self.status_controller
        pane.status_bar.bind(self.status_controller.model)
```

- [ ] **Step 2: Same in the demo window**

In `BasePluggableProtocolDemoWindow`, after building `self.pane`, construct the controller with `executor=self.pane.executor` and set `self.pane.status_controller = self.status_controller`.

- [ ] **Step 3: Run the full plugin test suite**

Run: `cd /c/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/ -q`
Expected: PASS (whole suite green).

- [ ] **Step 4: Commit**

```bash
git add src/pluggable_protocol_tree/views/dock_pane.py src/pluggable_protocol_tree/demos/base_demo_window.py
git commit -m "Wire executor into ProtocolStatusController at composition roots (#471)"
```

---

## Final verification

- [ ] Full suite green: `cd microdrop-py && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/ -q`
- [ ] Manual: pause mid-run, navigate step + phase, resume → continues from chosen (step, phase); chosen step/phase timer reset; counters follow; elapsed-vs-active semantics from #467 intact.
- [ ] `ProtocolTreePane` holds no `_pause_phases`/`_pause_phase_idx`; nav/seek logic lives in the controller/executor.
- [ ] Duration-mode steps re-enter at phase 1 on a phase-seek (deferred precise behavior tracked in #477).
