# Volume-Threshold × Route-Duration-Mode Dynamic Looping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a step has both route-duration mode and a volume threshold, loop route cycles dynamically (re-deciding after each cycle whether another full-duration cycle fits the budget) instead of running a precalculated count and idling the freed time — and keep the status bar showing the advancing phase.

**Architecture:** A new pure helper `duration_loop_parts` in `phase_math.py` decomposes a step into (soft-start ramp, one unit cycle, return-to-start phase) — no soft-end ramp. `RoutesHandler.on_step` is refactored to extract a shared `_run_phase` method; when duration-mode + volume-threshold are both active it drives a time-based loop over the unit cycle via `_run_phase`, dropping the ramp-down and emitting a running (denominator-less) phase index. `ProtocolTreePane._refresh_status` gains a middle branch to render that running index. Non-VT and count-mode paths are untouched.

**Tech Stack:** Python 3, Traits/PySide6, pytest. Pure-function phase math + threaded handler driven by `threading.Event`s.

---

## File Structure

- `pluggable_protocol_tree/services/phase_math.py` — add `duration_loop_parts` (pure helper). No change to existing helpers.
- `pluggable_protocol_tree/builtins/routes_column.py` — add module-level `_monotonic` seam; extract `_run_phase`; split `on_step` into `_run_static_phases` (existing behaviour) + `_run_dynamic_duration_loop` (new); import `duration_loop_parts`.
- `pluggable_protocol_tree/views/protocol_tree_pane.py` — add running-index branch to `_refresh_status`.
- `pluggable_protocol_tree/tests/test_phase_math.py` — tests for `duration_loop_parts`.
- `pluggable_protocol_tree/tests/test_electrodes_routes_columns.py` — tests for the dynamic loop + running index; update two MagicMock-row tests to set `row.volume_threshold = 0`.
- `pluggable_protocol_tree/tests/test_protocol_tree_pane.py` — tests for the `_refresh_status` running-index branch.

All test commands assume CWD `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src` and the project's pixi-invoked pytest. Use the verified invocation from memory (`reference_pixi_python_invocation`); shown here as `pytest ...` for brevity.

---

### Task 1: `duration_loop_parts` phase-math helper

**Files:**
- Modify: `pluggable_protocol_tree/services/phase_math.py` (add function after `_route_with_repeats`, ~line 134)
- Test: `pluggable_protocol_tree/tests/test_phase_math.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_phase_math.py`:

```python
# --- duration_loop_parts ---

from pluggable_protocol_tree.services.phase_math import duration_loop_parts


def test_duration_loop_parts_loop_route_basic():
    """One loop route, trail 1: unit cycle is the two windows; the return
    phase closes back to the first window; no soft-start ramp."""
    ramp, cycle, ret = duration_loop_parts(
        static_electrodes=[], routes=[["a", "b", "a"]],
        trail_length=1, trail_overlay=0, soft_start=False)
    assert cycle == [{"a"}, {"b"}]
    assert ret == {"a"}
    assert ramp == []


def test_duration_loop_parts_soft_start_ramps_first_unit_phase():
    """soft_start grows 1->N toward the first unit phase (sorted order),
    just like _ramp_up, but as an explicit list."""
    ramp, cycle, ret = duration_loop_parts(
        static_electrodes=["s1", "s2"], routes=[["a", "b", "a"]],
        trail_length=1, trail_overlay=0, soft_start=True)
    first = cycle[0]
    assert first == {"s1", "s2", "a"}            # static unioned into window
    ordered = sorted(first)
    assert ramp == [set(ordered[:1]), set(ordered[:2])]
    assert ret == first


def test_duration_loop_parts_no_routes_static_only():
    """No routes: the unit cycle is the single static phase and there is
    no return phase (nothing to close)."""
    ramp, cycle, ret = duration_loop_parts(
        static_electrodes=["x"], routes=[], trail_length=1,
        trail_overlay=0, soft_start=True)
    assert cycle == [{"x"}]
    assert ret is None
    assert ramp == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest pluggable_protocol_tree/tests/test_phase_math.py -k duration_loop_parts -v`
Expected: FAIL with `ImportError: cannot import name 'duration_loop_parts'`.

- [ ] **Step 3: Implement the helper**

In `phase_math.py`, after `_route_with_repeats` (before `_ramp_up`), add:

```python
def duration_loop_parts(
    static_electrodes: List[str],
    routes: List[List[str]],
    *,
    trail_length: int = 1,
    trail_overlay: int = 0,
    soft_start: bool = False,
):
    """Decompose a step into the pieces the RoutesHandler needs to drive a
    *dynamic* duration-mode loop under volume threshold:

        (ramp_up_phases, unit_cycle, return_phase)

    ``unit_cycle`` is ONE pass of the zipped route windows + static set
    (the repeatable unit). ``ramp_up_phases`` is the soft-start ramp toward
    ``unit_cycle[0]`` (empty when soft_start is False or the first phase has
    <= 1 electrode). ``return_phase`` is ``unit_cycle[0]`` (to close the loop
    back to its origin) or None when there are no routes.

    There is deliberately NO soft-end ramp: volume threshold reaching its
    target guarantees the droplet's position, so the gentle-release ramp is
    dropped. See the design spec.
    """
    static = set(static_electrodes or [])
    if not routes:
        # Static-only step: the single static set is the repeatable unit;
        # nothing to "return to", so no closing phase.
        return [], [set(static)], None
    per_route = [_route_windows(r, trail_length, trail_overlay)
                 for r in routes]
    unit_cycle = list(_zip_with_static(per_route, static))
    if not unit_cycle:
        return [], [set(static)], None
    ramp_up: List[Set[str]] = []
    first = unit_cycle[0]
    if soft_start and len(first) > 1:
        ordered = sorted(first)
        ramp_up = [set(ordered[:size]) for size in range(1, len(first))]
    return ramp_up, unit_cycle, unit_cycle[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest pluggable_protocol_tree/tests/test_phase_math.py -k duration_loop_parts -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/services/phase_math.py pluggable_protocol_tree/tests/test_phase_math.py
git commit -m "[PPT-25] Add duration_loop_parts phase-math helper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Extract `_run_phase` from `RoutesHandler.on_step` (behaviour-preserving)

**Files:**
- Modify: `pluggable_protocol_tree/builtins/routes_column.py` (`on_step` body ~lines 100-228; add `_run_phase` method)
- Test: `pluggable_protocol_tree/tests/test_electrodes_routes_columns.py` (existing tests must still pass)

This task is a pure refactor: the per-phase work moves into `_run_phase`, and the existing phase loop calls it. No behaviour change. The existing routes tests are the regression suite.

- [ ] **Step 1: Add the `_monotonic` time seam**

In `routes_column.py`, just below the existing `_SLICE_S` constant (~line 63), add:

```python
# Indirection so the dynamic duration loop's wall-clock reads can be
# replaced with a deterministic fake clock in tests. Production uses
# time.monotonic unchanged.
_monotonic = time.monotonic
```

- [ ] **Step 2: Add the `_run_phase` method**

Inside `RoutesHandler`, add this method directly above `on_step`:

```python
    def _run_phase(self, phase, *, ctx, mapping, static_routes, step_uuid,
                   step_label, preview_mode, per_phase_dwell, stop_event,
                   pause_event, qsignals, phase_index, phase_total):
        """Run ONE phase: clear the early-advance event, honour stop/pause,
        publish display (+ hardware when not preview), wait the ack, and
        dwell (cut short by phase_advance_event). Returns False if a Stop
        landed before/at this phase (caller should break its loop), True
        otherwise.

        ``phase_total`` is 0 for the dynamic loop (total unknown while
        looping); callers in the static path pass the materialized count.
        """
        # Fresh slate: a handler set in phase N-1 must NOT carry over into
        # phase N. Cleared before the stop/pause checks so a stale set
        # doesn't accidentally fire here.
        ctx.phase_advance_event.clear()
        if stop_event.is_set():
            return False
        # Pause check at the phase boundary — block so the next phase's
        # actuation doesn't fire until the user resumes.
        if pause_event.is_set():
            pause_event.wait_cleared()
            if stop_event.is_set():
                return False

        electrodes = sorted(phase)
        channels = sorted(mapping[e] for e in electrodes if e in mapping)
        for e in electrodes:
            if e not in mapping:
                logger.warning(
                    f"electrode {e!r} has no channel mapping; "
                    f"actuation channel skipped"
                )

        if qsignals is not None:
            qsignals.phase_started.emit(
                phase_index, phase_total, per_phase_dwell,
            )

        # 1. Display: synchronous, no ack. editable=False so the DV won't
        # echo a hardware publish back at us during a run.
        display_msg = ProtocolTreeDisplayMessage(
            electrodes=electrodes,
            routes=static_routes,
            step_id=step_uuid,
            step_label=step_label,
            free_mode=False,
            editable=False,
        )
        publish_message(
            topic=PROTOCOL_TREE_DISPLAY_STATE,
            message=display_msg.serialize(),
        )

        # 2. Hardware: only when not preview. Gating happens on the sender
        # side by simply not publishing.
        if not preview_mode:
            payload = {"electrodes": electrodes, "channels": channels}
            publish_message(
                topic=ELECTRODES_STATE_CHANGE,
                message=json.dumps(payload),
            )
            ctx.wait_for(ELECTRODES_STATE_APPLIED, timeout=5.0)

        _cooperative_sleep(per_phase_dwell, stop_event, pause_event,
                           phase_advance_event=ctx.phase_advance_event)
        return True
```

- [ ] **Step 3: Rewrite `on_step` to use `_run_phase` (static path only, same behaviour)**

Replace the body of `on_step` from the `total_phases = len(phases)` line through `ctx.step_phases_done_event.set()` (current lines ~143-228) with:

```python
        total_phases = len(phases)
        qsignals = getattr(ctx.protocol, "qsignals", None)
        for phase_idx, phase in enumerate(phases, start=1):
            if not self._run_phase(
                    phase, ctx=ctx, mapping=mapping,
                    static_routes=static_routes, step_uuid=step_uuid,
                    step_label=step_label, preview_mode=preview_mode,
                    per_phase_dwell=per_phase_dwell, stop_event=stop_event,
                    pause_event=pause_event, qsignals=qsignals,
                    phase_index=phase_idx, phase_total=total_phases):
                break
        # Route Reps Dur mode: after the full cycles, hold the last phase's
        # electrodes (no new publish) for the exact leftover so total step
        # time lands on the budget precisely. Based on the ACTUAL emitted
        # phase count so it accounts for loop cycles, ramps, and routes.
        if in_duration_mode and not stop_event.is_set():
            pad = max(0.0, float(getattr(row, "repeat_duration", 0.0))
                          - len(phases) * per_phase_dwell)
            if pad > 0:
                _cooperative_sleep(pad, stop_event, pause_event)
        # Tell DurationColumnHandler we already covered the dwell.
        ctx.scratch[DURATION_CONSUMED_KEY] = True
        # Signal sibling parallel-bucket handlers (e.g. VolumeThresholdHandler)
        # that the per-phase loop is done so they can exit their wait loops.
        ctx.step_phases_done_event.set()
```

(The lines above `total_phases` — `mapping`, `per_phase_dwell`, `in_duration_mode`, the `phases = list(iter_phases(...))` materialization, etc. — stay exactly as they are.)

- [ ] **Step 4: Run the existing routes tests to verify no regression**

Run: `pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -v`
Expected: all existing tests PASS (display/hardware per phase, preview skip, unmapped warning, route_repetitions, hold-pad, count-mode, gating, clears-event, done-event, cooperative-sleep).

- [ ] **Step 5: Run the phase-math + pane suites as a smoke check**

Run: `pytest pluggable_protocol_tree/tests/test_phase_math.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/builtins/routes_column.py
git commit -m "[PPT-25] Extract RoutesHandler._run_phase + add _monotonic seam

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Dynamic duration-mode loop under volume threshold

**Files:**
- Modify: `pluggable_protocol_tree/builtins/routes_column.py` (import `duration_loop_parts`; branch in `on_step`; add `_run_dynamic_duration_loop`)
- Test: `pluggable_protocol_tree/tests/test_electrodes_routes_columns.py`

- [ ] **Step 1: Write the failing tests**

First, update the two existing MagicMock-row tests so the new volume-threshold read doesn't see a truthy auto-attribute. In `test_routes_handler_clears_phase_advance_event_each_iteration` and `test_routes_handler_sets_step_phases_done_event_when_loop_finishes`, add this line where the other `row.*` attributes are set (e.g. right after `row.linear_repeats = False`):

```python
    row.volume_threshold = 0           # no VT -> static path
```

Then append the new dynamic-loop tests to `test_electrodes_routes_columns.py`:

```python
def test_dynamic_vt_loop_runs_more_cycles_than_precalc(qapp):
    """Duration mode + volume_threshold > 0: the handler loops the unit
    cycle dynamically based on a fake clock that advances slower than the
    full per-phase dwell (simulating VT cutting phases short), running far
    more cycles than the precalc (budget / cycle_full_time) would.

    Deterministic clock: each phase advances the fake clock by 0.5s; the
    full per-phase dwell is 1.0s, so the precalc would do budget/cycle_time
    = 8/2 = 4 cycles, but the dynamic loop fits ~7."""
    from unittest.mock import MagicMock, patch
    import threading
    import pluggable_protocol_tree.builtins.routes_column as mod
    from pluggable_protocol_tree.builtins.routes_column import RoutesHandler

    handler = RoutesHandler()
    row = MagicMock()
    row.routes = [["a", "b", "a"]]      # loop route -> unit cycle [{a},{b}]
    row.electrodes = []
    row.duration_s = 1.0                # full per-phase dwell
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = True                 # MUST be ignored (ramp-down dropped)
    row.repeat_duration = 8.0
    row.repeat_duration_controls = True
    row.linear_repeats = False
    row.route_repetitions = 1
    row.volume_threshold = 50           # VT active
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True           # skip hardware publish + ack wait
    proto.scratch = {"electrode_to_channel": {"a": 0, "b": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()
    ctx.scratch = {}
    ctx.wait_for = MagicMock()

    clock = {"t": 0.0}

    def fake_sleep(secs, *a, **k):
        clock["t"] += 0.5               # each phase "really" takes 0.5s

    displays = []

    def fake_publish(**kw):
        from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
        if kw.get("topic") == PROTOCOL_TREE_DISPLAY_STATE:
            displays.append(kw)

    # iter_phases must NOT be used on the dynamic path.
    iter_spy = MagicMock(side_effect=AssertionError("iter_phases used on VT path"))

    with patch.object(mod, "_monotonic", lambda: clock["t"]), \
         patch.object(mod, "_cooperative_sleep", side_effect=fake_sleep), \
         patch.object(mod, "publish_message", side_effect=fake_publish), \
         patch.object(mod, "iter_phases", iter_spy):
        handler.on_step(row, ctx)

    # Unit cycle = 2 phases; loop runs while t + 2.0 <= 8.0 (t <= 6.0),
    # advancing 1.0/cycle -> cycles at t=0,1,2,3,4,5,6 = 7 cycles = 14
    # phases, plus the single return-to-start phase = 15 display publishes.
    assert len(displays) == 15
    # Precalc equivalent would be 4 cycles + return = 9; dynamic ran more.
    assert len(displays) > 9
    assert ctx.step_phases_done_event.is_set() is True
    assert ctx.scratch.get(mod.DURATION_CONSUMED_KEY) is True


def test_dynamic_vt_loop_emits_running_index_with_zero_total(qapp):
    """Each phase emits phase_started with a monotonically increasing index
    and phase_total == 0 (unknown while looping)."""
    from unittest.mock import MagicMock, patch
    import threading
    import pluggable_protocol_tree.builtins.routes_column as mod
    from pluggable_protocol_tree.builtins.routes_column import RoutesHandler

    handler = RoutesHandler()
    row = MagicMock()
    row.routes = [["a", "b", "a"]]
    row.electrodes = []
    row.duration_s = 1.0
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 4.0
    row.repeat_duration_controls = True
    row.linear_repeats = False
    row.route_repetitions = 1
    row.volume_threshold = 50
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True
    proto.scratch = {"electrode_to_channel": {"a": 0, "b": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()
    ctx.scratch = {}
    ctx.wait_for = MagicMock()

    clock = {"t": 0.0}
    with patch.object(mod, "_monotonic", lambda: clock["t"]), \
         patch.object(mod, "_cooperative_sleep",
                      side_effect=lambda s, *a, **k: clock.__setitem__("t", clock["t"] + 0.5)), \
         patch.object(mod, "publish_message", lambda **kw: None):
        handler.on_step(row, ctx)

    calls = proto.qsignals.phase_started.emit.call_args_list
    indices = [c.args[0] for c in calls]
    totals = [c.args[1] for c in calls]
    assert indices == list(range(1, len(indices) + 1))   # 1,2,3,... no gaps
    assert all(t == 0 for t in totals)                   # total unknown


def test_dynamic_vt_loop_not_taken_when_no_volume_threshold(qapp):
    """Duration mode WITHOUT volume threshold: the static precalc path runs
    (iter_phases is used), proving the dynamic loop is gated on VT."""
    from unittest.mock import MagicMock, patch
    import threading
    import pluggable_protocol_tree.builtins.routes_column as mod
    from pluggable_protocol_tree.builtins.routes_column import RoutesHandler

    handler = RoutesHandler()
    row = MagicMock()
    row.routes = [["a", "b", "a"]]
    row.electrodes = []
    row.duration_s = 0.0
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 8.0
    row.repeat_duration_controls = True
    row.linear_repeats = False
    row.route_repetitions = 1
    row.volume_threshold = 0            # NO VT
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True
    proto.scratch = {"electrode_to_channel": {"a": 0, "b": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()
    ctx.scratch = {}
    ctx.wait_for = MagicMock()

    real_iter = mod.iter_phases
    iter_spy = MagicMock(side_effect=real_iter)
    with patch.object(mod, "iter_phases", iter_spy), \
         patch.object(mod, "publish_message", lambda **kw: None):
        handler.on_step(row, ctx)

    assert iter_spy.called          # precalc path used
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -k "dynamic_vt" -v`
Expected: FAIL — `test_dynamic_vt_loop_runs_more_cycles_than_precalc` and `_emits_running_index` fail because `on_step` currently always takes the precalc path (so `iter_phases` IS called → the `iter_spy` AssertionError fires, or the display count is the precalc 9 not 15). `_not_taken_when_no_volume_threshold` should already PASS.

- [ ] **Step 3: Add the import and the dynamic branch + helper**

In `routes_column.py`, change the phase_math import (~line 49) from:

```python
from pluggable_protocol_tree.services.phase_math import iter_phases
```

to:

```python
from pluggable_protocol_tree.services.phase_math import (
    duration_loop_parts, iter_phases,
)
```

In `on_step`, immediately after the `in_duration_mode = (...)` assignment (~line 125) and BEFORE the `phases = list(iter_phases(...))` materialization, insert the branch. Move the existing materialization + static loop + hold-pad into the `else`:

```python
        qsignals = getattr(ctx.protocol, "qsignals", None)
        vt_active = False
        try:
            vt_active = float(getattr(row, "volume_threshold", 0) or 0) > 0
        except (TypeError, ValueError):
            vt_active = False

        if in_duration_mode and vt_active:
            self._run_dynamic_duration_loop(
                row, ctx=ctx, mapping=mapping, static_routes=static_routes,
                step_uuid=step_uuid, step_label=step_label,
                preview_mode=preview_mode, per_phase_dwell=per_phase_dwell,
                stop_event=stop_event, pause_event=pause_event,
                qsignals=qsignals,
                budget=float(getattr(row, "repeat_duration", 0.0) or 0.0))
        else:
            phases = list(iter_phases(
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
            total_phases = len(phases)
            for phase_idx, phase in enumerate(phases, start=1):
                if not self._run_phase(
                        phase, ctx=ctx, mapping=mapping,
                        static_routes=static_routes, step_uuid=step_uuid,
                        step_label=step_label, preview_mode=preview_mode,
                        per_phase_dwell=per_phase_dwell, stop_event=stop_event,
                        pause_event=pause_event, qsignals=qsignals,
                        phase_index=phase_idx, phase_total=total_phases):
                    break
            if in_duration_mode and not stop_event.is_set():
                pad = max(0.0, float(getattr(row, "repeat_duration", 0.0))
                              - len(phases) * per_phase_dwell)
                if pad > 0:
                    _cooperative_sleep(pad, stop_event, pause_event)

        ctx.scratch[DURATION_CONSUMED_KEY] = True
        ctx.step_phases_done_event.set()
```

Notes:
- Remove the now-duplicated `qsignals = getattr(...)` and `total_phases`/loop/hold-pad lines that Task 2 left at the top level — they now live inside the `else`. The `qsignals` assignment moves up to before the branch (shown above).
- The `phases = list(iter_phases(...))` block that previously sat above the branch is now ONLY inside the `else`. Delete the original one above the branch.

Then add the dynamic-loop method to `RoutesHandler` (e.g. directly below `_run_phase`):

```python
    def _run_dynamic_duration_loop(self, row, *, ctx, mapping, static_routes,
                                   step_uuid, step_label, preview_mode,
                                   per_phase_dwell, stop_event, pause_event,
                                   qsignals, budget):
        """Duration mode + volume threshold: loop the unit cycle as long as
        another FULL-duration cycle still fits the budget, then close with
        the return-to-start phase and idle any sub-cycle remainder.

        Volume threshold cuts each phase short (via phase_advance_event), so
        wall-clock elapses slower than ``per_phase_dwell`` would predict and
        more cycles fit -> the freed time becomes more loops, not idle. The
        soft-end ramp-down is intentionally absent (duration_loop_parts does
        not produce it): reaching the threshold guarantees droplet position.
        The phase index is a running counter with total 0 (unknown while
        looping) so the status bar shows the advancing phase number."""
        ramp_up, unit_cycle, return_phase = duration_loop_parts(
            static_electrodes=list(getattr(row, "electrodes", []) or []),
            routes=list(getattr(row, "routes", []) or []),
            trail_length=int(getattr(row, "trail_length", 1)),
            trail_overlay=int(getattr(row, "trail_overlay", 0)),
            soft_start=bool(getattr(row, "soft_start", False)),
        )
        cycle_full_time = len(unit_cycle) * per_phase_dwell
        step_start = _monotonic()
        running_idx = 0

        def _run(phase):
            nonlocal running_idx
            running_idx += 1
            return self._run_phase(
                phase, ctx=ctx, mapping=mapping, static_routes=static_routes,
                step_uuid=step_uuid, step_label=step_label,
                preview_mode=preview_mode, per_phase_dwell=per_phase_dwell,
                stop_event=stop_event, pause_event=pause_event,
                qsignals=qsignals, phase_index=running_idx, phase_total=0)

        for phase in ramp_up:
            if not _run(phase):
                return

        while not stop_event.is_set():
            # Only add a cycle if there's room for a COMPLETE one at full
            # per-phase dwell. cycle_full_time <= 0 (degenerate 0-dwell
            # config) would never gate, so run a single cycle and stop.
            if cycle_full_time <= 0:
                for phase in unit_cycle:
                    if not _run(phase):
                        return
                break
            if _monotonic() - step_start + cycle_full_time > budget:
                break
            for phase in unit_cycle:
                if not _run(phase):
                    return

        if return_phase is not None and not stop_event.is_set():
            _run(return_phase)

        remaining = budget - (_monotonic() - step_start)
        if remaining > 0 and not stop_event.is_set():
            _cooperative_sleep(remaining, stop_event, pause_event)
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -k "dynamic_vt" -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full routes suite for regressions**

Run: `pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -v`
Expected: all PASS (including the two MagicMock-row tests updated with `row.volume_threshold = 0`).

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/builtins/routes_column.py pluggable_protocol_tree/tests/test_electrodes_routes_columns.py
git commit -m "[PPT-25] Dynamic duration-mode looping under volume threshold

Loop the unit cycle while another full-duration cycle fits the budget
instead of running a precalculated count and idling freed time. Drop the
soft-end ramp-down (VT guarantees position), keep the return-to-start
phase, idle the sub-cycle remainder. Gated on duration mode + a soft
volume_threshold>0 row check, so non-VT paths are unchanged.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Status-bar running-index rendering

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py` (`_refresh_status`, ~lines 562-571)
- Test: `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_protocol_tree_pane.py`:

```python
def test_refresh_status_running_index_without_total(qapp):
    """Dynamic VT loop: phase_total == 0 but phase_index > 0 -> show the
    running phase number with NO denominator."""
    import time as _t
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic="x/applied")
    pane._step_started_at = _t.monotonic()
    pane._phase_started_at = _t.monotonic()
    pane._phase_index = 7
    pane._phase_total = 0
    pane._phase_target = 1.0
    pane._refresh_status()
    text = pane._status_phase_time_label.text()
    assert "Phase 7" in text
    assert "Phase 7/" not in text          # no denominator


def test_refresh_status_index_over_total_when_known(qapp):
    """Static/count path: phase_total > 0 -> unchanged 'i/N' rendering."""
    import time as _t
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic="x/applied")
    pane._step_started_at = _t.monotonic()
    pane._phase_started_at = _t.monotonic()
    pane._phase_index = 2
    pane._phase_total = 5
    pane._phase_target = 0.5
    pane._refresh_status()
    assert "Phase 2/5" in pane._status_phase_time_label.text()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -k refresh_status -v`
Expected: `test_refresh_status_running_index_without_total` FAILs (current code shows `Phase {elapsed}s / ...` with no index when total == 0, so `"Phase 7" not in text`). The `index_over_total` test PASSes (existing behaviour).

- [ ] **Step 3: Add the middle branch in `_refresh_status`**

In `protocol_tree_pane.py`, replace the `if self._phase_total > 0: ... else: ...` block (~lines 563-571) with:

```python
            if self._phase_total > 0:
                self._status_phase_time_label.setText(
                    f"Phase {self._phase_index}/{self._phase_total}  "
                    f"{phase_elapsed:4.2f}s / {target:.2f}s"
                )
            elif self._phase_index > 0:
                # Dynamic duration loop: total is unknown while looping, so
                # show the running phase number with no misleading denominator.
                self._status_phase_time_label.setText(
                    f"Phase {self._phase_index}  "
                    f"{phase_elapsed:4.2f}s / {target:.2f}s"
                )
            else:
                self._status_phase_time_label.setText(
                    f"Phase {phase_elapsed:5.2f}s / {target:.2f}s"
                )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -k refresh_status -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full pane suite for regressions**

Run: `pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git commit -m "[PPT-25] Status bar: running phase index when total is unknown

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final Verification

- [ ] **Run the full affected-suite once more:**

Run: `pytest pluggable_protocol_tree/tests/test_phase_math.py pluggable_protocol_tree/tests/test_electrodes_routes_columns.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py pluggable_protocol_tree/tests/test_base_demo_window.py -q`
Expected: all PASS.

---

## Self-Review

**Spec coverage:**
- Scope/trigger (duration mode + `volume_threshold > 0`, soft `getattr`) → Task 3 branch + `_not_taken_when_no_volume_threshold` test. ✓
- Phase structure (soft-start once, unit cycle repeated, ramp-down dropped, return-to-start kept, idle remainder) → Task 1 `duration_loop_parts` + Task 3 `_run_dynamic_duration_loop`. ✓
- Time-driven loop with full-`per_phase_dwell` room test → Task 3 loop condition + `runs_more_cycles_than_precalc` test. ✓
- `_run_phase` extraction shared by both paths → Task 2. ✓
- Running phase index, `phase_total = 0` → Task 3 `_emits_running_index` test; `_refresh_status` branch → Task 4. ✓
- Edge: no routes (static-only) → `duration_loop_parts` returns `[static], None`; loop repeats the static phase (covered structurally; `test_duration_loop_parts_no_routes_static_only`). ✓
- Edge: budget < one cycle → while-guard fails immediately, return phase still runs (return_phase path runs unconditionally when not stopped). ✓
- Edge: degenerate `cycle_full_time <= 0` → single-cycle guard in the loop. ✓
- Stop/pause honoured via shared `_run_phase` returning False → caller breaks/returns. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✓

**Type/name consistency:** `duration_loop_parts(static_electrodes, routes, *, trail_length, trail_overlay, soft_start)` returns `(ramp_up, unit_cycle, return_phase)` — used identically in Task 3. `_run_phase(..., phase_index, phase_total)` signature matches both call sites. `_monotonic` defined in Task 2, used in Task 3. `DURATION_CONSUMED_KEY` unchanged. ✓
