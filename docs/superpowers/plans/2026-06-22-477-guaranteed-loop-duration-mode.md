# Guaranteed-loop Duration Mode with Unique-Phase Navigation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For route-rep-by-time (duration-mode) steps, keep looping only while a full loop is *guaranteed* to finish within the user-set rep time, then idle; let the operator toggle the loop's unique phases while paused and resume from there; warn on mid-loop-expiry and on leaving the idle phase.

**Architecture:** The dynamic duration loop (`RoutesHandler._run_dynamic_duration_loop`) is changed to (a) gate each loop on raw wall-clock elapsed plus the worst-case loop time, (b) enter an explicit electrodes-off idle phase when no further loop fits, (c) re-enter at the cursor's phase index after a paused seek (closing the #477 gap), and (d) raise a mid-loop-expiry dialog on resume. The phase timeline bar shows the loop's unique phases plus one dark-yellow idle cell; navigating away from idle raises a warning on the GUI side.

**Tech Stack:** Python 3, Traits/TraitsUI, PySide6/Qt, pytest. Run Python/pytest via `pixi run` (see `reference_pixi_python_invocation`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-22-477-guaranteed-loop-duration-mode-design.md`. Every task implicitly includes its requirements.
- Scope is the **dynamic** duration loop only (`in_duration_mode and phase_hold`). Count-mode and static-duration paths are untouched except for the shared idle-cell rendering and warnings.
- `raw_elapsed = monotonic() - step_start` — **includes pauses and holds; never pause-aware, never extension-credited.**
- `phase_dwell = row.duration_s`; `worst_loop = cycle_len * phase_dwell`; `budget = row.repeat_duration`.
- Use f-strings for all logging/messages. Use `microdrop_application.dialogs.pyface_wrapper` for all dialogs (returns pyface `YES`/`NO`). No cross-plugin class imports.
- Voltage/frequency are ints elsewhere — not relevant here; durations are floats (seconds).

---

### Task 1: Pure duration-loop decision helpers

**Files:**
- Modify: `pluggable_protocol_tree/services/phase_math.py` (append helpers near `duration_loop_parts`, line ~136–179)
- Test: `pluggable_protocol_tree/tests/test_phase_math.py` (add cases; create if absent)

**Interfaces:**
- Consumes: `duration_loop_parts(...)` (existing).
- Produces:
  - `unit_cycle_len(static_electrodes, routes, *, trail_length=1, trail_overlay=0, soft_start=False) -> int`
  - `another_loop_fits(raw_elapsed: float, cycle_len: int, phase_dwell: float, budget: float) -> bool`
  - `loop_completion_fits(raw_elapsed: float, phase_in_cycle: int, cycle_len: int, phase_dwell: float, budget: float) -> bool`
  - `idle_cell_index(cycle_len: int) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# pluggable_protocol_tree/tests/test_phase_math.py  (add to file)
from pluggable_protocol_tree.services.phase_math import (
    unit_cycle_len, another_loop_fits, loop_completion_fits, idle_cell_index,
)

def test_unit_cycle_len_loop_route():
    # one loop route a-b-c-d, trail_length 1 -> 4 windows in the unit cycle
    n = unit_cycle_len([], [["a", "b", "c", "d"]], trail_length=1, trail_overlay=0)
    assert n == 4

def test_unit_cycle_len_static_only_is_one():
    assert unit_cycle_len(["a", "b"], []) == 1

def test_another_loop_fits_boundary():
    # cycle_len 4 * dwell 2.0 = 8.0 worst loop; budget 20
    assert another_loop_fits(raw_elapsed=12.0, cycle_len=4, phase_dwell=2.0, budget=20.0) is True   # 12+8=20 exact fit
    assert another_loop_fits(raw_elapsed=12.001, cycle_len=4, phase_dwell=2.0, budget=20.0) is False
    assert another_loop_fits(raw_elapsed=0.0, cycle_len=0, phase_dwell=2.0, budget=20.0) is False    # no phases -> never

def test_loop_completion_fits_from_mid_cycle():
    # from phase k=1 of a 4-phase loop, 3 phases remain * 2.0 = 6.0
    assert loop_completion_fits(raw_elapsed=14.0, phase_in_cycle=1, cycle_len=4, phase_dwell=2.0, budget=20.0) is True  # 14+6=20
    assert loop_completion_fits(raw_elapsed=14.5, phase_in_cycle=1, cycle_len=4, phase_dwell=2.0, budget=20.0) is False

def test_idle_cell_index_is_cycle_len():
    assert idle_cell_index(4) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_phase_math.py -k "loop or idle or unit_cycle_len" -v`
Expected: FAIL with `ImportError`/`AttributeError` (helpers not defined).

- [ ] **Step 3: Implement the helpers**

```python
# pluggable_protocol_tree/services/phase_math.py  (append after duration_loop_parts)
def unit_cycle_len(static_electrodes, routes, *, trail_length=1,
                   trail_overlay=0, soft_start=False) -> int:
    """Number of phases in one unit loop (the unique, navigable phases)."""
    _ramp, unit_cycle, _ret = duration_loop_parts(
        static_electrodes, routes, trail_length=trail_length,
        trail_overlay=trail_overlay, soft_start=soft_start)
    return len(unit_cycle)


def another_loop_fits(raw_elapsed: float, cycle_len: int,
                      phase_dwell: float, budget: float) -> bool:
    """True if a FULL fresh loop is guaranteed to finish within budget.

    Worst case assumes every phase runs its full ``phase_dwell`` (the
    volume-threshold timeout equals the duration-column value). Uses raw
    wall-clock elapsed (pauses/holds already spent count against budget)."""
    if cycle_len <= 0:
        return False
    return raw_elapsed + cycle_len * phase_dwell <= budget


def loop_completion_fits(raw_elapsed: float, phase_in_cycle: int,
                         cycle_len: int, phase_dwell: float,
                         budget: float) -> bool:
    """True if finishing the CURRENT loop from ``phase_in_cycle`` (0-based)
    back to the start still fits the budget. Used for the mid-loop-expiry
    check on resume after a seek."""
    remaining = max(0, cycle_len - phase_in_cycle)
    return raw_elapsed + remaining * phase_dwell <= budget


def idle_cell_index(cycle_len: int) -> int:
    """0-based index of the trailing idle cell on the phase bar
    (the bar shows ``cycle_len`` unique phases + this idle cell)."""
    return cycle_len
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_phase_math.py -k "loop or idle or unit_cycle_len" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/services/phase_math.py pluggable_protocol_tree/tests/test_phase_math.py
git commit -m "feat(#477): pure duration-loop gate + idle-cell helpers"
```

---

### Task 2: Status model — dynamic-loop unique-phase + idle state

**Files:**
- Modify: `pluggable_protocol_tree/models/protocol_status.py` (add fields + methods; reset at line 74–80)
- Test: `pluggable_protocol_tree/tests/test_protocol_status_model.py` (add cases; create if absent)

**Interfaces:**
- Produces (on `ProtocolStatusModel`):
  - field `dyn_idle = Bool(False)` — True while the running step is parked in its idle phase.
  - `on_dyn_phase(now, cycle_pos, cycle_len, phase_target_s)` — cycle_pos is 1-based within the unit loop.
  - `on_dyn_idle(now, cycle_len)` — park on the idle cell.
- Consumes: nothing new.

Note: the bar shows `cycle_len + 1` cells (unique phases + idle). `phase_total` therefore holds `cycle_len + 1`; the idle cell is the last one (`phase_index == cycle_len + 1`, 1-based).

- [ ] **Step 1: Write the failing tests**

```python
# pluggable_protocol_tree/tests/test_protocol_status_model.py  (add)
from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel

def test_on_dyn_phase_sets_unique_phase_plus_idle_total():
    m = ProtocolStatusModel()
    m.on_dyn_phase(now=0.0, cycle_pos=2, cycle_len=4, phase_target_s=2.0)
    assert m.phase_index == 2
    assert m.phase_total == 5          # 4 unique + 1 idle cell
    assert m.dyn_idle is False

def test_on_dyn_idle_parks_on_idle_cell():
    m = ProtocolStatusModel()
    m.on_dyn_idle(now=0.0, cycle_len=4)
    assert m.phase_index == 5          # idle cell is the last (1-based)
    assert m.phase_total == 5
    assert m.dyn_idle is True

def test_reset_clears_dyn_idle():
    m = ProtocolStatusModel()
    m.on_dyn_idle(now=0.0, cycle_len=4)
    m.reset()
    assert m.dyn_idle is False
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_protocol_status_model.py -k dyn -v`
Expected: FAIL (`AttributeError: dyn_idle` / methods missing).

- [ ] **Step 3: Implement**

```python
# protocol_status.py — add field next to run state (after line 53 `paused = Bool(False)`)
    # True while a dynamic duration-mode step is parked in its idle phase
    # (the trailing dark-yellow cell). Drives the leaving-idle warning (#477).
    dyn_idle = Bool(False)
```

```python
# protocol_status.py — in reset(), add dyn_idle=False to the trait_set(...) call (line 74-80)
            phase_target_s=0.0, running=False, paused=False, dyn_idle=False,
```

```python
# protocol_status.py — add methods after on_phase_start (line ~116)
    def on_dyn_phase(self, now, cycle_pos, cycle_len, phase_target_s):
        """Dynamic duration loop: park the bar on unique phase ``cycle_pos``
        (1-based) of a ``cycle_len``-phase loop. phase_total carries the extra
        trailing idle cell so the bar renders cycle_len + 1 cells (#477)."""
        self.dyn_idle = False
        self.on_phase_start(now, cycle_pos, cycle_len + 1, phase_target_s)

    def on_dyn_idle(self, now, cycle_len):
        """Dynamic duration loop: park on the trailing idle cell (electrodes
        off). The idle cell is the last of cycle_len + 1 cells (#477)."""
        self.on_phase_start(now, cycle_len + 1, cycle_len + 1, 0.0)
        self.dyn_idle = True
```

- [ ] **Step 4: Run to verify pass**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_protocol_status_model.py -k dyn -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/protocol_status.py pluggable_protocol_tree/tests/test_protocol_status_model.py
git commit -m "feat(#477): status model unique-phase + idle state for dynamic loops"
```

---

### Task 3: ExecutorSignals + controller wiring for dynamic phase/idle

**Files:**
- Modify: `pluggable_protocol_tree/execution/signals.py` (add two Events near `phase_started`, line ~52–58)
- Modify: `pluggable_protocol_tree/services/protocol_status_controller.py` (observe them, near `_on_phase_started` line ~119–125)
- Test: `pluggable_protocol_tree/tests/test_protocol_status_controller.py` (add cases)

**Interfaces:**
- Produces on `ExecutorSignals`:
  - `dyn_phase_started = Event` — payload `(cycle_pos:int, cycle_len:int, phase_dwell:float)`
  - `dyn_idle_entered = Event` — payload `cycle_len:int`
- Consumes: `ProtocolStatusModel.on_dyn_phase`, `on_dyn_idle` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
# test_protocol_status_controller.py  (add)
def test_dyn_phase_and_idle_signals_update_model(make_controller):
    # make_controller: existing fixture returning (controller, signals) with a
    # fake clock; mirror the existing phase_started test in this file.
    ctrl, signals = make_controller()
    signals.dyn_phase_started = (2, 4, 2.0)
    assert ctrl.model.phase_index == 2
    assert ctrl.model.phase_total == 5
    assert ctrl.model.dyn_idle is False
    signals.dyn_idle_entered = 4
    assert ctrl.model.dyn_idle is True
    assert ctrl.model.phase_index == 5
```

If no `make_controller` fixture exists, construct the controller as the existing `_on_phase_started` test does in this file (match its setup exactly).

- [ ] **Step 2: Run to verify failure**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_protocol_status_controller.py -k dyn -v`
Expected: FAIL (Event attrs / handlers missing).

- [ ] **Step 3: Implement signals + handlers**

```python
# execution/signals.py — add near phase_started / phase_extended
    #: Dynamic duration loop: (cycle_pos 1-based, cycle_len, phase_dwell_s).
    dyn_phase_started = Event()
    #: Dynamic duration loop entered its idle phase; payload = cycle_len.
    dyn_idle_entered = Event()
```

```python
# services/protocol_status_controller.py — add observers next to _on_phase_started
    @observe("signals:dyn_phase_started")
    def _on_dyn_phase_started(self, event):
        cycle_pos, cycle_len, phase_dwell = event.new
        self.model.on_dyn_phase(self.clock(), cycle_pos, cycle_len, phase_dwell)

    @observe("signals:dyn_idle_entered")
    def _on_dyn_idle_entered(self, event):
        self.model.on_dyn_idle(self.clock(), int(event.new))
```

(Match the existing observer style in this file — it already uses `@observe("signals:...")` with `self.clock()`; confirm the exact decorator/clock accessor against `_on_phase_started` at lines 119–125 and copy it.)

- [ ] **Step 4: Run to verify pass**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_protocol_status_controller.py -k dyn -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/execution/signals.py pluggable_protocol_tree/services/protocol_status_controller.py pluggable_protocol_tree/tests/test_protocol_status_controller.py
git commit -m "feat(#477): executor signals + controller wiring for dynamic phase/idle"
```

---

### Task 4: Dynamic loop — raw-elapsed guaranteed-loop gate, explicit idle, seek re-entry, mid-loop-expiry

**Files:**
- Modify: `pluggable_protocol_tree/builtins/routes_column.py` — `_run_dynamic_duration_loop` (lines 263–349)
- Test: `pluggable_protocol_tree/tests/test_routes_dynamic_loop.py` (create) — pure-logic seams only

**Interfaces:**
- Consumes: `another_loop_fits`, `loop_completion_fits`, `idle_cell_index`, `unit_cycle_len` (Task 1); `ctx.protocol.cursor` (`phase_index`, `resume_target`, `clear_seek`, `decision_at_phase`); `signals.dyn_phase_started`, `signals.dyn_idle_entered` (Task 3); `ctx.prompt_gui` (existing, returns the dialog result on the worker thread).
- Produces: revised `_run_dynamic_duration_loop` behavior. A new module-level pure helper `dyn_resume_start(cursor_phase_index, cycle_len) -> tuple[int, bool]` → `(start_phase_in_cycle, start_idle)`.

**Behavior to implement (replace the body from line 297 onward):**

1. `cycle_len = len(unit_cycle)`; `worst = cycle_len * per_phase_dwell` (== existing `cycle_full_time`).
2. `step_start = _monotonic()`; `raw_elapsed = lambda: _monotonic() - step_start` (NO extension subtraction — drop `_budget_elapsed`).
3. Resume position from cursor: `start_k, start_idle = dyn_resume_start(int(ctx.protocol.cursor.phase_index), cycle_len)`.
4. **Mid-loop-expiry** (only when re-entering at `start_k > 0` from a seek, i.e. `resume_target` was set, and NOT coming from idle): if `not loop_completion_fits(raw_elapsed(), start_k, cycle_len, per_phase_dwell, budget)`, call `ctx.prompt_gui(...)`. On YES → run `start_k..end` then advance to next step (set `ctx.step_phases_done_event`/return after the partial loop, skipping the gate). On NO → `ctx.pause()` and return to the pause checkpoint (do not run).
5. Emit each phase via `_run` AND `signals.dyn_phase_started = (cycle_pos, cycle_len, per_phase_dwell)` where `cycle_pos` is 1-based position within the unit cycle.
6. **Gate** at each loop boundary: `if another_loop_fits(raw_elapsed(), cycle_len, per_phase_dwell, budget): run a full loop; else: break to idle`.
7. **Idle**: publish electrodes-off once (`electrode_state_change_publisher.publish(actuated_channels=[])` unless `preview_mode`), `signals.dyn_idle_entered = cycle_len`, then `_cooperative_sleep` until `raw_elapsed() >= budget` OR a seek arrives (`ctx.protocol.cursor.resume_target is not None`); if a seek arrives, loop back so the executor's pause/seek path re-enters this step.

A unit-testable seam (`dyn_resume_start`) is the only pure logic added here; the threaded loop itself is verified manually (Step 6).

- [ ] **Step 1: Write the failing test for the pure seam**

```python
# pluggable_protocol_tree/tests/test_routes_dynamic_loop.py (create)
from pluggable_protocol_tree.builtins.routes_column import dyn_resume_start

def test_dyn_resume_start_normal_phase():
    assert dyn_resume_start(0, 4) == (0, False)
    assert dyn_resume_start(2, 4) == (2, False)

def test_dyn_resume_start_idle_cell():
    # cursor index == cycle_len -> idle cell
    assert dyn_resume_start(4, 4) == (0, True)

def test_dyn_resume_start_clamps_out_of_range():
    assert dyn_resume_start(9, 4) == (0, True)   # >= cycle_len clamps to idle
    assert dyn_resume_start(-1, 4) == (0, False)
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_routes_dynamic_loop.py -v`
Expected: FAIL (`ImportError: dyn_resume_start`).

- [ ] **Step 3: Add the pure seam**

```python
# routes_column.py — module level (near other helpers, above RoutesHandler)
def dyn_resume_start(cursor_phase_index: int, cycle_len: int):
    """Resolve a paused-seek cursor phase to a dynamic-loop start.

    Returns (start_phase_in_cycle, start_idle). cursor_phase_index is the
    0-based unique-phase the operator toggled to; an index at/over cycle_len
    is the trailing idle cell. Negative clamps to phase 0 (#477)."""
    if cycle_len <= 0:
        return 0, False
    if cursor_phase_index >= cycle_len:
        return 0, True
    return max(0, int(cursor_phase_index)), False
```

- [ ] **Step 4: Run to verify the seam passes**

Run: `pixi run pytest pluggable_protocol_tree/tests/test_routes_dynamic_loop.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Rewrite `_run_dynamic_duration_loop` body**

Replace lines 297–349 with the logic below (keep the `ramp_up, unit_cycle, return_phase = duration_loop_parts(...)` block above it). Imports needed at top of file (verify present): `from electrode_controller.consts import electrode_state_change_publisher` (already imported), `another_loop_fits, loop_completion_fits` from `phase_math`.

```python
        cycle_len = len(unit_cycle)
        worst_loop = cycle_len * per_phase_dwell
        step_start = _monotonic()
        running_idx = 0

        def raw_elapsed():
            # RAW wall-clock since step start: pauses and holds count against
            # the budget (NOT pause-aware, NOT extension-credited) — #477.
            return _monotonic() - step_start

        cursor = ctx.protocol.cursor
        start_k, start_idle = dyn_resume_start(int(cursor.phase_index), cycle_len)
        came_from_seek = cursor.resume_target is not None
        cursor.clear_seek()

        def _run_cycle_phase(phase, cycle_pos):
            nonlocal running_idx
            running_idx += 1
            if signals is not None:
                signals.dyn_phase_started = (cycle_pos + 1, cycle_len, per_phase_dwell)
            return self._run_phase(
                phase, ctx=ctx, mapping=mapping, static_routes=static_routes,
                step_uuid=step_uuid, step_label=step_label,
                preview_mode=preview_mode, per_phase_dwell=per_phase_dwell,
                stop_event=stop_event, pause_event=pause_event,
                signals=signals, phase_index=cycle_pos + 1, phase_total=cycle_len + 1,
                hold_for_buffer=True, honor_pause=False)

        def _go_idle():
            if not preview_mode:
                electrode_state_change_publisher.publish(actuated_channels=[])
            if signals is not None:
                signals.dyn_idle_entered = cycle_len
            while not stop_event.is_set() and raw_elapsed() < budget:
                if cursor.resume_target is not None:
                    return  # operator toggled away from idle -> let executor re-enter
                _cooperative_sleep(min(0.1, budget - raw_elapsed()),
                                   stop_event, pause_event,
                                   seek_pending=lambda: cursor.resume_target is not None)

        # Soft-start ramp only on a fresh (non-seek) entry.
        if not came_from_seek and not start_idle:
            for phase in ramp_up:
                if not _run_cycle_phase(phase, 0):
                    return

        # Mid-loop-expiry guard: re-entry partway through the loop where
        # finishing won't fit the budget (operator toggled to a bad spot).
        if came_from_seek and not start_idle and start_k > 0 \
                and not loop_completion_fits(raw_elapsed(), start_k, cycle_len,
                                             per_phase_dwell, budget):
            proceed = ctx.prompt_gui(lambda: _confirm_finish_loop_over_budget())
            if not proceed:
                ctx.pause()
                return
            # Run the partial loop to its end, then advance to next step.
            for i in range(start_k, cycle_len):
                if not _run_cycle_phase(unit_cycle[i], i):
                    return
            ctx.step_phases_done_event.set()
            return

        if start_idle:
            _go_idle()
            return

        # First (possibly partial) loop from start_k, then full loops while
        # another guaranteed loop fits; otherwise idle.
        i = start_k
        while not stop_event.is_set():
            while i < cycle_len:
                if not _run_cycle_phase(unit_cycle[i], i):
                    return
                i += 1
            i = 0
            if not another_loop_fits(raw_elapsed(), cycle_len, per_phase_dwell, budget):
                break
        if not stop_event.is_set():
            _go_idle()
```

Where `_confirm_finish_loop_over_budget` is a small helper added to the module:

```python
# routes_column.py — module level
def _confirm_finish_loop_over_budget():
    from microdrop_application.dialogs.pyface_wrapper import confirm, YES
    return confirm(
        None,
        "The set route-rep time is up, but the current loop is not back at its "
        "start position. Finish this loop (electrodes return to start) and then "
        "move to the next step?",
        title="Loop needs more time",
        cancel=False,
    ) == YES
```

Note: drop the old `_budget_elapsed`, the old `cycle_full_time` gate (lines 327–340), the old `return_phase` tail (342–343), and the old credit-back remainder sleep (345–349) — superseded by `_go_idle()` and the guaranteed-loop gate. The loop now always ends back at the unit-cycle start, so the separate `return_phase` is unnecessary (the next loop's phase 0 IS the return).

- [ ] **Step 6: Manual verification (threaded loop)**

The dynamic loop runs on a worker thread under volume-threshold; verify in the app, not pytest:
1. Build a duration-mode loop step (`repeat_duration_controls` on, `repeat_duration` set, a volume-threshold column present), e.g. 4-phase loop, `duration_s=2`, `repeat_duration=20`.
2. Run it: confirm it loops and, when fewer than `4*2=8 s` remain, enters idle (electrodes off) until 20 s, then advances.
3. Pause mid-step, toggle to phase 2 on the bar, resume → it continues from phase 2 and completes the loop.
4. Pause near the end, toggle to a late phase so finishing won't fit → on resume the "Loop needs more time" dialog appears; YES finishes the loop then next step; NO leaves it paused.

- [ ] **Step 7: Commit**

```bash
git add pluggable_protocol_tree/builtins/routes_column.py pluggable_protocol_tree/tests/test_routes_dynamic_loop.py
git commit -m "feat(#477): guaranteed-loop gate, idle phase, seek re-entry, mid-loop-expiry"
```

---

### Task 5: Make the phase bar show unique phases + idle during the dynamic loop

**Files:**
- Modify: `pluggable_protocol_tree/views/dock_pane.py` — `_refresh_timeline_position` (lines 425–467) and `_update_phase_nav_buttons` (567–574)
- Modify: `pluggable_protocol_tree/views/timeline_bar.py` — idle-cell color (`_colors` 279–284, `_paint_track` 288–324, `set_position` 136–143)

**Interfaces:**
- Consumes: `status_controller.model.phase_total`, `phase_index`, `dyn_idle` (Tasks 2–3).
- Produces: `TimelineBar.set_idle_cell(index_or_None)` — paints that cell dark yellow regardless of playhead.

Today the dynamic loop emitted `phase_total = 0`, hiding the phase track. Task 4 now emits `phase_total = cycle_len + 1` via the status model, so the existing `_refresh_timeline_position` will show the track (it requires `> 1`). This task adds the **idle-cell color** and ensures the idle cell is reachable by the nav buttons.

- [ ] **Step 1: Add the idle-cell color + setter to TimelineBar**

```python
# timeline_bar.py — in _colors(), add an "idle" key to both branches
# dark:  idle=QColor("#9a7d0a")   light: idle=QColor("#b8860b")  (dark yellow / dark goldenrod)
```
Concretely:
```python
    def _colors(self):
        if is_dark_mode():
            return dict(track=GREY["dark"], tick=GREY["lighter"],
                        head=SECONDARY_SHADE[300], running_head=SECONDARY_SHADE[100],
                        idle="#9a7d0a")
        return dict(track=GREY["light"], tick=GREY["dark"],
                    head=SECONDARY_SHADE[700], running_head=SECONDARY_SHADE[900],
                    idle="#b8860b")
```

```python
# timeline_bar.py — add an _idle_cell attribute (init in __init__ near other state, default None)
        self._idle_cell = None

    def set_idle_cell(self, index):
        """Index of the dark-yellow idle cell on the phase track, or None."""
        if self._idle_cell != index:
            self._idle_cell = index
            self.update()
```

```python
# timeline_bar.py — in _paint_track, BEFORE the current-position box (line ~314),
# fill the idle cell when this is the phase track. Pass an `idle_cell` arg through
# from paintEvent for the phase track only.
        if idle_cell is not None and 0 <= idle_cell < count:
            left = int(SIDE_MARGIN + idle_cell * seg)
            right = int(SIDE_MARGIN + (idle_cell + 1) * seg)
            idle_fill = QColor(colors["idle"]); idle_fill.setAlpha(120)
            painter.fillRect(QRect(left, rect.top(), max(1, right - left),
                                   rect.height()), idle_fill)
```
Update `_paint_track` signature to `(..., cell_colors=None, idle_cell=None)` and pass `idle_cell=self._idle_cell` only for the phase-track call in `paintEvent` (line 335–337); the step-track call passes nothing (defaults None).

- [ ] **Step 2: Drive the idle cell + show the track from the dock pane**

In `_refresh_timeline_position` (dock_pane.py 425–467), after computing the phase track position, set the idle cell when the running step is a dynamic duration step:

```python
        # Dynamic duration step: the last phase cell is the idle phase (#477).
        m = self.status_controller.model
        tb = getattr(self._pane, "timeline_bar", None)
        if tb is not None:
            if m.running and m.phase_total > 1 and self._current_row is not None \
                    and bool(getattr(self._current_row, "repeat_duration_controls", False)):
                tb.set_idle_cell(m.phase_total - 1)
            else:
                tb.set_idle_cell(None)
```
Place this where `set_position(...)`/`show_phase` is decided (around line 463–464). Ensure `show_phase` becomes True for the dynamic loop now that `phase_total > 1` (it keys off `running or view["can_collapse"]`, so running already satisfies it — confirm no explicit `phase_total=0` override remains for this path).

- [ ] **Step 3: Allow navigating onto the idle cell**

In `_update_phase_nav_buttons` (dock_pane.py 567–574), the next-phase button currently disables at `phase_index >= phase_total`. Since the idle cell IS `phase_total`, leave as-is (idle is the last index, reachable). Confirm `prev_enabled = m.phase_index > 1` and `next_enabled = 0 < m.phase_index < m.phase_total` still let the user land on and leave the idle cell (idle index == phase_total, so `next_enabled` is False at idle — correct; `prev` leaves it). No code change expected; add a comment noting the idle cell is index `phase_total`.

- [ ] **Step 4: Manual verification**

Run a dynamic duration step; confirm the phase bar shows `cycle_len + 1` cells, the last one tinted dark yellow, the playhead advancing through the unique phases and parking on the idle cell during idle.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/views/timeline_bar.py pluggable_protocol_tree/views/dock_pane.py
git commit -m "feat(#477): phase bar shows unique phases + dark-yellow idle cell"
```

---

### Task 6: Leaving-idle warning (GUI-side, pre-seek)

**Files:**
- Modify: `pluggable_protocol_tree/views/dock_pane.py` — `_seek_to_phase` (lines 362–372)
- Test: covered by manual verification (the guard is a dialog around a Qt seek).

**Interfaces:**
- Consumes: `status_controller.model.dyn_idle` (Task 2), `pyface_wrapper.confirm`/`YES`.

- [ ] **Step 1: Add the warning to `_seek_to_phase`**

```python
# dock_pane.py — top of _seek_to_phase, before sc.seek_to(...)
        sc = self.status_controller
        if sc is None or self._current_row is None:
            return
        # Leaving the idle phase mid-run: warn before toggling back to a real
        # phase — there may not be time to complete a full loop, so resuming
        # could strand electrodes mid-loop (#477).
        idle_index = sc.model.phase_total - 1
        if sc.model.dyn_idle and target0 != idle_index:
            from microdrop_application.dialogs.pyface_wrapper import confirm, YES
            if confirm(
                None,
                "This step has already reached its idle phase. Toggling back to "
                "a phase may leave the electrodes mid-loop (not at the start "
                "position) if there isn't time to finish a full loop. Continue?",
                title="Already idle",
                cancel=False,
            ) != YES:
                return
        path = tuple(self._current_row.path)
        sc.seek_to(path, target0)
        sc.preview_phase(path, target0, self._current_run_preview_mode)
        self._update_phase_nav_buttons()
```

(This replaces the current 6-line body; the `sc`/`_current_row` guard is preserved at the top.)

- [ ] **Step 2: Manual verification**

Reach idle on a dynamic duration step, pause, click an earlier phase on the bar → the "Already idle" dialog appears; Cancel keeps idle; OK seeks and (on resume) runs the loop from there and returns to idle.

- [ ] **Step 3: Commit**

```bash
git add pluggable_protocol_tree/views/dock_pane.py
git commit -m "feat(#477): warn before leaving the idle phase"
```

---

### Task 7: Cap per-phase hold at duration_s (worst-case guarantee)

**Files:**
- Modify: `volume_threshold_protocol_controls/protocol_columns/volume_threshold_column.py` (the hold/extend path; confirm against `ctx.note_phase_extension` call site ~line 387)
- Test: manual + existing volume-threshold tests must still pass.

**Interfaces:**
- Consumes: `row.duration_s`. Ensures a phase never holds beyond `duration_s`, so `worst_loop = cycle_len * duration_s` is a true bound (spec §10).

- [ ] **Step 1: Audit the hold**

Read the volume-threshold hold/extend logic. Per the product decision, the threshold per-phase timeout equals the duration-column value (`duration_s`). Confirm the post-dwell hold (`hold_for_buffer` in `routes_column._run_phase`, lines 236–260) plus any threshold extension cannot keep a phase active longer than `duration_s`. If an explicit timeout field exists, set/clamp it to `duration_s`.

- [ ] **Step 2: Apply the cap (if needed)**

If the hold can exceed `duration_s`, clamp the wait to `max(0, duration_s - already_elapsed_in_phase)` at the hold site. Show the exact change in the PR; if the audit shows the hold already caps at `duration_s`, record that finding in the commit message and skip the code change.

- [ ] **Step 3: Run existing volume-threshold tests**

Run: `pixi run pytest volume_threshold_protocol_controls/tests/ -v`
Expected: PASS (no regressions).

- [ ] **Step 4: Commit**

```bash
git add volume_threshold_protocol_controls/
git commit -m "fix(#477): cap per-phase hold at duration_s for the worst-case loop bound"
```

---

## Self-Review

**Spec coverage:**
- §3 guaranteed-loop gate + idle → Task 1 (`another_loop_fits`) + Task 4 (gate + `_go_idle`). ✓
- §4 unique phases + dark-yellow idle cell → Task 2/3 (model+signals) + Task 5 (rendering). ✓
- §5 seek re-entry into the dynamic loop → Task 4 (`dyn_resume_start`, start_k loop). ✓
- §6a mid-loop-expiry warning → Task 4 (`loop_completion_fits` + `ctx.prompt_gui`). ✓
- §6b leaving-idle warning → Task 6. ✓
- §10 hold cap → Task 7. ✓
- §7 removed items (no time scrubbing/axis/record/spinbox) → nothing added for them. ✓

**Placeholder scan:** Task 7 Step 2 is conditional ("if needed") by design — it carries an explicit audit-then-act instruction and a definite fallback (record the finding), not a vague TODO. All other steps carry concrete code/commands.

**Type consistency:** `dyn_resume_start(idx, cycle_len) -> (int, bool)`, `another_loop_fits`/`loop_completion_fits` signatures, `on_dyn_phase(now, cycle_pos, cycle_len, phase_target_s)` and `on_dyn_idle(now, cycle_len)`, signals `dyn_phase_started=(cycle_pos, cycle_len, dwell)` / `dyn_idle_entered=cycle_len`, and `set_idle_cell(index)` are used consistently across Tasks 1–6.

**Note on testing:** the threaded dynamic loop and Qt painting are verified manually (Tasks 4–6) per project norms; pure logic (Tasks 1–3, and the `dyn_resume_start` seam in Task 4) is unit-tested.
