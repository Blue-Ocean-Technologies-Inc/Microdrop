# Guaranteed-loop duration mode with unique-phase navigation (#477)

**Issue:** [#477](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/477) — Precise phase-granular resume for duration-mode steps (follow-up to #471).
**Date:** 2026-06-22
**Status:** Design approved; ready for implementation plan.

> **Direction change vs. the issue text.** Issue #477 proposed resolving a *phase index*
> for duration-mode resume. This spec supersedes that with a simpler model: keep the loop
> running only while a full loop is *guaranteed* to finish within the user-set rep time,
> then idle; let the operator toggle the loop's unique phases while paused and resume from
> there; and warn (rather than silently misbehave) when navigation would strand the run
> mid-loop. There is **no** time-domain scrubbing, no time axis, and no per-phase actual-
> duration recording.

---

## 1. Scope

Applies only to **route-rep-by-time (duration-mode) steps** — rows where
`repeat_duration_controls is True and repeat_duration > 0`. Within those, the work targets the
**dynamic loop** `RoutesHandler._run_dynamic_duration_loop`
(`builtins/routes_column.py:263–349`), which runs when `in_duration_mode and phase_hold`
(the volume-threshold path; `phase_hold = ctx.scratch.get(PHASE_HOLD_REQUESTED_KEY)`).

Out of scope / unchanged:
- Count-mode steps (discrete materialized phases) keep their current phase bar and navigation.
- Duration-mode steps **without** volume-threshold (the static `iter_phases` path with a
  trailing hold-pad, `routes_column.py:393–461`) already precompute their loop count and
  idle pad and already honor the seek cursor; they get only the shared idle-cell rendering
  and the two warning dialogs (§5) for consistency, no loop-gate surgery.

## 2. Definitions

For a duration-mode dynamic step:

| Symbol | Meaning | Source |
|---|---|---|
| `cycle_len` | number of phases in one unit loop (the unique phases) | `len(unit_cycle)` from `duration_loop_parts(...)` (`phase_math.py:136–179`) |
| `phase_dwell` | per-phase dwell / max hold, seconds | `row.duration_s` |
| `worst_loop` | worst-case time for one full loop | `cycle_len * phase_dwell` |
| `budget` | the user-set rep time | `row.repeat_duration` |
| `raw_elapsed()` | wall-clock since step start | `monotonic() - step_start`, **including pauses and holds; NOT pause-aware and NOT extension-credited** |

`phase_dwell` is also the per-phase volume-threshold hold timeout (per product decision: the
threshold timeout equals the duration-column value). Therefore each phase takes **at most**
`phase_dwell`, which makes `worst_loop` a true upper bound on a full loop.

## 3. Loop-continuation gate (core behavior change)

In `_run_dynamic_duration_loop`, the decision to run another loop happens at each **loop
boundary** (the moment execution is back at the loop's start position):

```
if raw_elapsed() + worst_loop <= budget:
    run another full loop
else:
    enter idle
```

- Because every phase ≤ `phase_dwell`, any loop admitted by the gate is *guaranteed* to
  complete within `budget`. The run never starts a loop it cannot finish.
- This replaces today's continuation check
  (`_budget_elapsed() + cycle_full_time <= budget`, `routes_column.py:327–340`), which used
  `_budget_elapsed() = monotonic - step_start - phase_extension_total` (pause/extension
  credit-back). The new gate uses **raw elapsed** — pauses and holds count against the budget.
- `cycle_full_time` in today's code already equals `cycle_len * phase_dwell = worst_loop`; the
  change is dropping the credit-back term, plus moving the idle decision to the loop boundary.

### Idle
When the gate fails, the step enters **idle**:
- Electrodes **off** (publish an empty actuation set, preview-gated like other hardware
  publishes).
- Cooperative-sleep (stop/pause-aware) until `raw_elapsed() >= budget`, then the step ends and
  the executor advances to the next step.
- Idle is a real, navigable position on the phase bar (§4).

## 4. Phase bar: unique phases + idle cell

Today the dynamic loop emits `phase_total = 0`, which hides the phase track
(`timeline_bar._phase_track_visible` requires `> 1`). Instead:

- Feed the bar `phase_total = cycle_len + 1` — the `cycle_len` unique phases plus a single
  trailing **idle** cell — and a playhead at the current unit-cycle index (or the idle cell
  when idle). Source the count/position from the running loop via the status model
  (`models/protocol_status.py`) and `_refresh_timeline_position` (`dock_pane.py:425–467`).
- The trailing idle cell renders in **dark yellow** (new color key in `timeline_bar.py`’s
  color set, applied via the existing `cell_colors` channel in `_paint_track`,
  `timeline_bar.py:288–324`).
- Count-mode steps are unaffected.

Navigation maps a clicked/▶◀ cell to a unique-phase index `k` (or the idle cell). The three
existing input paths (`timeline_bar.phase_seek_requested`, nav-bar prev/next-phase buttons,
phase-rep combo) funnel through `dock_pane._seek_to_phase(target0)`
(`dock_pane.py:362–372`) as today.

## 5. Seek re-entry into the dynamic loop (closes the #477 gap)

Currently `_run_dynamic_duration_loop` always starts `running_idx = 0` and ignores
`cursor.phase_index`, so a phase-seek re-enters at phase 1 (`routes_column.py:299`). Change:

- `_run_dynamic_duration_loop` reads `cursor.phase_index` on entry and resumes the loop at
  `unit_cycle[k]`, running phases `k…cycle_len-1` to complete the loop back to start, then
  evaluates the gate (§3).
- The seek plumbing is unchanged: `executor.seek` → `cursor.request_seek` →
  `cursor.frame_for_seek` / `decision_at_phase` (`cursor.py`, `seek.py`,
  `protocol_status_controller.seek_to`). Only the dynamic loop's *consumption* of the cursor
  phase index is new.
- A pure helper resolves a unique-phase index `k` to its `unit_cycle` position (and back),
  unit-tested independently.

## 6. Warning dialogs

Both use the project dialog wrapper (`microdrop_application.dialogs.pyface_wrapper`), returning
pyface YES/NO directly. Both are triggered on the GUI thread from the navigation/resume flow.

### (a) Mid-loop-expiry warning
On **resume** after the operator navigated to phase `k`, if completing the loop from `k` would
exceed the budget:

```
remaining_to_loop_end = (cycle_len - k) * phase_dwell
if raw_elapsed() + remaining_to_loop_end > budget:  # won't fit
    warn("We need more time to reach the loop's end point.")
```

- **OK / Yes** → run `k…end` ignoring the budget, then advance to the next step (the intended
  time is up; do not start another loop).
- **No / Cancel** → leave the protocol paused so the operator can toggle to a safe phase, stop,
  or otherwise decide. The step is not advanced and no loop is run.

### (b) Leaving-idle warning
Once the step has reached **idle**, if the operator navigates back to a real phase `k`:

- Warn first: "We've already reached the idle phase. Toggling phases may leave the electrodes
  in a non-start position mid-loop, because there may not be time to complete a full loop."
- **OK / Yes** → run the loop from `k`; on completion (back at start), return to idle.
- **No / Cancel** → stay idle; no navigation applied.

When both conditions apply (navigating away from idle *and* the loop won't fit), warning (b) is
shown; an OK there proceeds under warning (a)'s "run to loop end, then next step" semantics.

## 7. What is explicitly NOT in this design

Removed relative to the earlier time-domain brainstorm:
- No time scrubbing / moving the playhead forward or backward in time.
- No "time increment" float spin box in the timeline controls.
- No `phase_finished` signal or per-phase actual-duration record.
- No proportional time-axis rendering (the bar stays discrete unique-phase cells + idle).
- No standalone auto-overrun pause; the loop-gate (§3) plus mid-loop-expiry warning (§6a)
  cover overrun.

## 8. Components touched

| Area | File(s) | Change |
|---|---|---|
| Loop gate + idle + seek re-entry | `builtins/routes_column.py` (`_run_dynamic_duration_loop`, `_run_phase`) | raw-elapsed guaranteed-loop gate; idle-on-fail; read `cursor.phase_index`; cap phase hold at `phase_dwell` |
| Unique-phase + idle resolution | `services/phase_math.py` | pure helper: unit-cycle length, `k → unit_cycle` position, idle-cell index |
| Bar state during dynamic loop | `models/protocol_status.py`, `services/protocol_status_controller.py`, `views/dock_pane.py` (`_refresh_timeline_position`) | emit `cycle_len + 1` and current cell instead of `phase_total = 0` |
| Idle cell color | `views/timeline_bar.py` | dark-yellow idle cell via `cell_colors` |
| Warnings | `views/dock_pane.py` (navigation/resume handlers) | mid-loop-expiry + leaving-idle dialogs |

## 9. Testing

Pure-unit coverage (no Redis/hardware):
- Loop-continuation gate: `raw_elapsed + worst_loop <= budget` boundary cases (exact fit,
  just-over, idle-from-start when budget < worst_loop).
- Mid-loop-expiry predicate: `(cycle_len - k) * phase_dwell` vs. remaining budget across `k`.
- Seek re-entry: `k → unit_cycle` position resolution, including `k = 0`, `k = cycle_len-1`,
  and the idle cell.
- Idle entry/exit transitions on the status model.

## 10. Open implementation note

For the worst-case bound to hold, the dynamic loop must treat `duration_s` as the per-phase
hold ceiling. If the current volume-threshold hold logic
(`volume_threshold_protocol_controls`, `ctx.note_phase_extension`,
`StepContext` phase-buffer) can extend a phase beyond `duration_s`, the implementation must cap
it (or surface the discrepancy). Confirm during implementation.
