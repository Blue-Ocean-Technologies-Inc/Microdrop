# PPT-25 follow-up: Volume Threshold × Route-Duration Mode — Design

**Date:** 2026-06-03
**Branch:** `feat/ppt-25_volume_threshold`
**Related:** #437 (volume threshold column)

## Goal

Resolve the conflict between the **volume-threshold** column (cuts each
phase short when measured capacitance reaches the target) and
**route-duration mode** (loops the routes to fill a fixed time budget).

In duration mode the loop count is *precalculated* from the assumption
that each phase dwells its full `duration_s`. Volume threshold breaks
that assumption: phases end early, so the precalculated cycles finish
well before the budget elapses and the freed time is wasted idling.

Desired behaviour: when volume threshold is active, keep running loop
cycles *dynamically* — re-deciding after each cycle whether another full
cycle still fits in the remaining budget — so the accelerated phases
translate into **more loops**, not idle time.

## Background

### Current duration-mode behaviour (`builtins/routes_column.py`)

`RoutesColumnHandler.on_step` materialises the full phase list up front:

```python
phases = list(iter_phases(..., repeat_duration_s=<budget> if in_duration_mode else 0, ...))
```

For a loop route, `_route_with_repeats` (phase_math.py) precalculates a
**fixed** cycle count:

```python
cycles = max(1, int(repeat_duration_s / (cycle_phases * step_duration_s)))
```

and yields `[soft-start ramp] + cycle×cycles + return-to-start + [soft-end ramp]`.
The for-loop dwells `per_phase_dwell` (= `duration_s`) per phase — or
returns early when `ctx.phase_advance_event` is set (volume threshold).
After the loop a **hold-pad** idles `repeat_duration − len(phases)×per_phase_dwell`
so total step time lands exactly on the budget.

### The conflict

With volume threshold cutting phases short, actual elapsed time per
phase < `per_phase_dwell`. The `cycles` count is fixed, so the
precalculated phases complete in less than `repeat_duration`, and the
hold-pad idles the (now-large) remainder. The user expected more loops,
not a long idle.

### Key existing pieces reused

- `ctx.phase_advance_event` — set by `VolumeThresholdHandler` (priority
  30, parallel with Routes); `_cooperative_sleep` returns early on it.
- `ctx.step_phases_done_event` — Routes sets it after its loop so
  sibling handlers (VolumeThreshold) exit.
- `phase_math._route_windows`, `_zip_with_static` — build one cycle of
  zipped route windows + static electrodes.
- The hold-pad / `_cooperative_sleep` idle.

## Design

### Scope / trigger

The new dynamic behaviour engages **only** when a step has BOTH:
1. duration mode: `repeat_duration_controls` is True AND `repeat_duration > 0`, and
2. volume threshold active: `getattr(row, "volume_threshold", 0) > 0`.

When volume threshold is **not** active, duration mode is completely
unchanged (precalc cycles + ramps + hold-pad) — zero regression risk for
existing protocols. RoutesHandler detects volume threshold with a soft
attribute read (`getattr(row, "volume_threshold", 0) > 0`); no import
dependency on the `volume_threshold_protocol_controls` plugin (the
attribute is simply absent → 0 when that column isn't loaded).

### Phase structure under the dynamic path

```
[soft-start ramp]  (once, if soft_start)
unit cycle         (repeated dynamically — see loop below)
unit cycle
...
return-to-start    (once — closes the loop to its origin)
idle remainder     (hold-pad, to land on the budget)
```

- **soft-start ramp** still runs once at the start (ramp up to full
  coverage).
- **unit cycle** = one pass of the zipped route windows + static
  electrodes (`cycle_phases` phases). This is the repeated unit.
- **soft-end ramp-down is dropped.** Volume threshold guarantees the
  droplet has reached its target coverage, so the gentle-release ramp is
  unnecessary.
- **return-to-start phase** is kept (the first unit phase, re-emitted to
  close the loop back to its starting electrode position). It is about
  ending position, not the gentle ramp-release, so volume threshold does
  not negate it.
- **idle remainder** keeps the existing contract that the step occupies
  the full `repeat_duration`.

### The dynamic loop (time-driven)

```
step_start = monotonic()
budget     = repeat_duration
cycle_full_time = len(unit_cycle) * per_phase_dwell   # one cycle at FULL dwell

run each soft-start ramp phase            # via _run_phase

while not stop_event.is_set():
    elapsed = monotonic() - step_start
    if elapsed + cycle_full_time > budget:    # no room for another FULL cycle
        break
    run each unit_cycle phase                 # via _run_phase (dwell or cut short)

if not stop_event.is_set():
    run the return-to-start phase             # via _run_phase

remaining = budget - (monotonic() - step_start)
if remaining > 0 and not stop_event.is_set():
    _cooperative_sleep(remaining, stop_event, pause_event)
```

- The "room for another cycle" test uses **full** `per_phase_dwell` per
  phase (`cycle_full_time`), per the requirement: only add a loop if
  there is enough time for a complete loop with each phase taking its
  configured `duration_s`. Whether the just-run phases were actually cut
  short by volume threshold is irrelevant to the decision — the decision
  is forward-looking and conservative.
- Because volume threshold makes `elapsed` grow slower than
  `cycle_full_time` would predict, more cycles satisfy the test → more
  loops run. With no acceleration, `elapsed` grows at the full rate and
  the count matches today's precalc.
- `stop_event` / `pause_event` are honoured at every phase exactly as in
  the existing loop.

### Refactor: extract `_run_phase`

The per-phase work currently inlined in `on_step`'s for-loop (clear
`phase_advance_event`, pause check, compute electrodes/channels, emit
`phase_started`, publish display + hardware, await `ELECTRODES_STATE_APPLIED`,
`_cooperative_sleep` with `phase_advance_event`) is extracted into a
private helper `RoutesColumnHandler._run_phase(...)` so both the existing
static path and the new dynamic path share one implementation. This keeps
the two paths consistent (pause/stop/early-advance semantics identical)
and the method focused. The caller supplies the 1-based phase index and
the phase total for the `phase_started` emission, so the helper is
agnostic to which path drives it.

### Status-bar updates during dynamic looping

The status bar must keep showing which phase is running as the dynamic
loop adds phases — the total is unknown up front, but the user still
needs to see the phase advancing.

- The dynamic path keeps a **running phase counter** that increments
  across the soft-start ramp phases, every unit-cycle phase, and the
  return-to-start phase. Each `_run_phase` call emits
  `phase_started.emit(running_index, 0, per_phase_dwell)` — a real,
  monotonically increasing index with `phase_total = 0` (genuinely
  unknown while looping).
- `ProtocolTreePane._refresh_status` is extended with a middle branch so
  a zero total but non-zero index renders the running number without a
  misleading denominator:

  ```python
  if self._phase_total > 0:
      text = f"Phase {self._phase_index}/{self._phase_total}  {phase_elapsed:4.2f}s / {target:.2f}s"
  elif self._phase_index > 0:                      # dynamic loop: running count, total unknown
      text = f"Phase {self._phase_index}  {phase_elapsed:4.2f}s / {target:.2f}s"
  else:
      text = f"Phase {phase_elapsed:5.2f}s / {target:.2f}s"
  ```

  Because the existing (static / count / non-VT) paths always emit
  `phase_total > 0`, they keep the `i/N` display unchanged — this branch
  only engages for the dynamic VT path. Each `phase_started` resets
  `_phase_started_at`, so the per-phase elapsed timer restarts at every
  phase exactly as today.

A fixed estimated total is deliberately rejected: under volume threshold
the actual count exceeds the no-acceleration precalc, so a fixed
denominator would be overshot ("Phase 12/8"), which is worse than no
denominator.

### New `phase_math` helper

`duration_loop_parts(static_electrodes, routes, *, trail_length,
trail_overlay, soft_start) -> (ramp_up_phases, unit_cycle, return_phase)`:

- `unit_cycle` = `list(_zip_with_static([_route_windows(r, trail_length,
  trail_overlay) for r in routes], static))` — one pass of the zipped
  windows. When there are no routes, `unit_cycle = [static]` and
  `return_phase = None`.
- `ramp_up_phases` = the soft-start ramp toward `unit_cycle[0]` (empty
  when `soft_start` is False or the first phase has ≤ 1 electrode),
  reusing the same sorted-element ramp logic as `_ramp_up`.
- `return_phase` = `unit_cycle[0]` for a non-empty cycle, else `None`.
- It deliberately does NOT emit a soft-end ramp (dropped under VT).

The existing `iter_phases` / `_route_with_repeats` precalc path is
untouched and remains the engine for the non-VT duration-mode case and
all count-mode cases.

## Data flow

```
on_step
  in_duration_mode = repeat_duration_controls and repeat_duration > 0
  vt_active        = getattr(row, "volume_threshold", 0) > 0

  if in_duration_mode and vt_active:
      ramp_up, unit_cycle, return_phase = duration_loop_parts(...)
      run ramp_up (each via _run_phase)
      loop unit_cycle while room for another full cycle remains
      run return_phase
      idle remainder
  else:
      phases = iter_phases(...)            # unchanged precalc
      for phase in phases: _run_phase(...)
      if in_duration_mode: hold-pad idle   # unchanged

  ctx.step_phases_done_event.set()         # always, both paths
```

## Error handling / edge cases

- **No routes (static-only step) + VT + duration mode:** `unit_cycle =
  [static]`, `return_phase = None`. The dynamic loop repeats the single
  static phase while the budget allows — i.e. holds the static actuation,
  re-checking volume threshold each `duration_s` window, until the budget
  is met. Reasonable: a static droplet-merge step keeps actuating until
  its volume target is reached or the budget elapses.
- **Budget smaller than one cycle:** the `while` guard fails immediately;
  no unit cycle runs; the return phase still runs (one closing phase),
  then idle. (Matches the `max(1, ...)` "at least something runs"
  spirit of the precalc, scaled to the dynamic model — at minimum the
  return-to-start fires so the step isn't a no-op.) NOTE: if even the
  return phase would overrun the budget, it still runs once — a single
  phase is the minimum meaningful actuation.
- **Stop / pause:** honoured at every phase via the shared `_run_phase`
  and the `while not stop_event` guards, identical to today.
- **Volume-threshold handler absent / inactive mid-run:** if
  `phase_advance_event` never fires, each phase dwells its full
  `per_phase_dwell`; `elapsed` grows at the full rate; the dynamic loop
  runs the same number of cycles the precalc would have — no behavioural
  change beyond the dropped ramp-down.

## Testing

**`phase_math` (`test_phase_math.py` or equivalent):**
- `duration_loop_parts` with a single loop route: `unit_cycle` length ==
  the cycle window count; `return_phase == unit_cycle[0]`; `ramp_up`
  empty when `soft_start=False`.
- With `soft_start=True` and a multi-electrode first phase: `ramp_up`
  ramps 1→full toward `unit_cycle[0]`.
- No routes: `unit_cycle == [static]`, `return_phase is None`,
  `ramp_up == []`.

**RoutesHandler (`test_electrodes_routes_columns.py`):**
- **Dynamic extension fires under VT:** duration mode + `volume_threshold>0`;
  drive `phase_advance_event` so phases end "instantly" (a fake
  `_cooperative_sleep` / injected clock); assert the number of unit
  cycles run exceeds the precalc count and that total wall-budget logic
  idles the remainder. (Use a deterministic monotonic-time seam so the
  test isn't wall-clock-flaky — e.g. inject a `time_fn` or monkeypatch
  the handler's clock.)
- **No VT → unchanged:** duration mode, `volume_threshold == 0`; assert
  the precalc path runs (same phase count as today) and the soft-end ramp
  still appears.
- **Ramp-down dropped under VT:** with `soft_end=True` + VT active, assert
  no ramp-down phases are emitted.
- **Static-only step under VT:** no routes → repeats the static phase
  within budget; `step_phases_done_event` set at the end.
- **Running phase index emitted under VT:** assert `phase_started` is
  emitted once per phase with a monotonically increasing index across
  ramp-up + unit cycles + return phase, and `phase_total == 0`.
- `_run_phase` extraction: existing per-phase tests (display + hardware
  publish, preview skip, unmapped electrode warning, phase_advance early
  return) still pass.

**`ProtocolTreePane._refresh_status` (`test_protocol_tree_pane.py`):**
- **Running-index branch:** with `_phase_total == 0` and
  `_phase_index > 0`, the label shows `Phase <index>` (no `/total`) plus
  the elapsed/target timing.
- **Regression:** with `_phase_total > 0` the label still shows
  `Phase <index>/<total>` exactly as before.

A deterministic time source is required for the dynamic-loop tests —
specify the seam in the implementation plan (inject the clock used for
`step_start` / `elapsed`, defaulting to `time.monotonic`).

## Out of scope

- Open (non-loop) routes under duration mode + VT: they fall through the
  same `duration_loop_parts` machinery (one forward pass repeated), but
  the feature is designed for loop routes ("loop all the loopable
  routes"). No special open-route handling beyond what the general zip
  produces.
- Changing count-mode behaviour or non-duration-mode behaviour.
- The cross-phase target-staleness note from the base PPT-25 spec
  (separate concern; unchanged here).
