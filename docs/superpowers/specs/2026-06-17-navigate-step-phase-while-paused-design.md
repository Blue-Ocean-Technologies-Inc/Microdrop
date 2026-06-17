# Navigate step/phase while paused → resume from there (#471)

Deferred follow-up from #467 (PR #470). While a protocol is **paused**, let the
operator navigate to a different step and/or phase; the counters and timers
follow the navigation, and **resume continues from the chosen (step, phase)**
with that step/phase timer reset.

Builds on the #467 MVC split (`ScopeStopwatch`, `ProtocolStatusModel`,
`ProtocolStatusController`, `StatusBar.bind`) and keeps the executor **Qt-free**.

## Acceptance (from the issue)

- While paused, selecting a different **step** updates `Step n/N` and, on resume,
  the run continues from that step with the step timer reset.
- While paused, selecting a different **phase** updates `Phase n/N` and, on
  resume, continues from that phase with the phase timer reset.
- The executor gains a documented mid-run **seek** capability, distinct from the
  start-of-run `start_step_path`.
- Logic lives in the model/controller/execution layers; `ProtocolTreePane` stays
  a thin view. Covered by pure (no-Qt) unit tests.
- Elapsed-vs-active semantics from #467 preserved (elapsed ignores pause; active
  freezes).

## Current state (what exists)

- **Executor** (`execution/executor.py`): a `threading.Thread` running `run()`.
  `_run_steps()` walks `iter_execution_frames()`; `skip_until` (= `_start_step_path`)
  is a one-shot skip honored only on rep 0. **Two pause checkpoints:** the
  frame-loop top (`_run_steps`, ~line 323, between steps) and mid-phase inside
  `RoutesHandler._run_phase` (`builtins/routes_column.py`, ~line 160). No mid-run
  seek exists.
- **Phases**: `RoutesHandler.on_step` runs a step's phases. Two paths — a **static
  materialized list** (count / fixed-duration; phase index well-defined) and a
  **dynamic duration loop** (`_run_dynamic_duration_loop`; phase total unknown
  while looping).
- **Status** (#467): `ProtocolStatusModel` (Qt-free rules + three `ScopeStopwatch`),
  `ProtocolStatusController` (executor signals → model), `StatusBar.bind`.
- **Paused phase navigation already exists but in the wrong layer**: the pane
  holds `_pause_phases`, `_pause_phase_idx`, `_compute_pause_phase_state`,
  `_publish_paused_phase`, `_on_prev_phase`/`_on_next_phase`. It updates the DV
  display/hardware but does **not** affect executor resume position. This moves
  out of the pane.

## Architecture

```
view (thin)             ProtocolStatusController            execution layer (Qt-free)
ProtocolTreePane ─nav intent─▶ seek_to(path, phase) ─▶ executor.seek(path, phase)
  (tree selection,                 │                      (records resume target)
   phase prev/next                 ├─▶ model.seek_step/seek_phase(now)   (counters + timer reset)
   while paused)                   └─▶ publish DV display (+ hw if !preview)
StatusBar ◀─observers/poll─ ProtocolStatusModel ◀─executor signals─┘   (normal flow on resume)
```

Selection intent flows view → controller → (executor + model). The executor
never references Qt/widgets beyond the existing `ExecutorSignals` emit boundary.

## Component 1 — Executor mid-run seek (`execution/executor.py`, Qt-free)

State:
- The executor tracks its **current position** `(step_path, phase_index)` as it
  runs (it already increments `step_index` and emits `phase_started`; thread it
  through as `_current_step_path` / `_current_phase_index`).
- `_resume_target: Optional[Tuple[Path, int]]`.

Methods:
- `pause()` additionally snapshots the current position into `_resume_target`.
- `seek(step_path, phase_index)` — **guarded to act only while paused** —
  overwrites `_resume_target`. Pure, no Qt.

Resume behavior — both pause checkpoints become seek-aware. After
`pause_event.wait_cleared()` returns, compare `_resume_target` to the natural
next position:

- **Same step, different phase** → the **phase loop jumps in place** to the
  target phase index and continues. **Step hooks are NOT re-run.**
- **Different step** → the phase loop returns an **abort-for-seek sentinel** so
  `on_step` unwinds to `_run_steps`, which re-resolves the target frame by path
  from `iter_execution_frames()` and runs that frame's step hooks
  (`on_pre_step`/`on_step`/`on_post_step`) with `ctx.start_phase_index = phase`.
  (Re-running step hooks is correct here precisely because the step changed.)

`StepContext` gains `start_phase_index: int = 0`; the static phase loop begins at
that index.

Pure helper: `resolve_seek(frames, target) -> (frame_index, phase_index)` (or
`None` if the path is gone), with index clamping. Unit-tested with no threads/Qt.

**Duration-mode steps**: phases are generated on the fly with unknown total, so a
precise phase index isn't well-defined. v1 re-enters a duration-mode step at
**phase 1** on a phase-seek (step timer still resets). Precise duration-mode
phase-resume is deferred to **#477**.

## Component 2 — Status model seek rules (`models/protocol_status.py`, Qt-free)

Two new rule methods, mirroring `on_step_start`/`on_phase_start` but **setting**
indices (not incrementing) and resetting the relevant clock(s). Seek only ever
happens while paused, so the fresh clock is started then immediately paused, so
both its elapsed and active read zero and stay frozen until resume.

- `seek_step(now, step_index, recent_name, next_name)` — set `step_index`; set
  names; clear phase counters + `phase_target_s`; `step_clock = fresh; start(now);
  pause(now)`; fresh unstarted `phase_clock`.
- `seek_phase(now, phase_index, phase_total, phase_target_s)` — set phase
  indices/target; `phase_clock = fresh; start(now); pause(now)` → resets that
  phase's timer (elapsed **and** active).

## Component 3 — Controller seek orchestration (`services/protocol_status_controller.py`)

`seek_to(step_path, phase_index)`:
1. `self.executor.seek(step_path, phase_index)` (records resume target),
2. `self.model.seek_step(...)` and/or `self.model.seek_phase(...)` — step index
   from the manager, names via the existing `_next_name`, `phase_total`/target
   from `iter_phases` on the target row,
3. publish the selected phase to the DV display (+ hardware if not preview).

The phase materialization for the target step (the pane's
`_compute_pause_phase_state` via `iter_phases`) and the `_publish_paused_phase`
body move here. The controller gains a reference to the executor (it already
holds `qsignals`/`manager`).

## Component 4 — View thinning (`views/protocol_tree_pane.py`)

Remove `_pause_phases`, `_pause_phase_idx`, `_compute_pause_phase_state`,
`_publish_paused_phase`, and the bodies of `_on_prev_phase`/`_on_next_phase`
(they delegate to the controller). While paused, the pane:
- enables **step selection** (tree `currentChanged` → `controller.seek_to(step_path, 0)`),
- enables **phase prev/next** (→ `controller.seek_to(current_step_path, k±1)`),
- reflects model state (counters/timers already bound via #467 `StatusBar.bind`).

The pane keeps its non-status responsibilities (button state machine, play/stop/
pause wiring, `PROTOCOL_RUNNING` publish, error dialog, loading screen).

## Data flow

```
[paused] operator selects a step / clicks Next Phase
  → pane → controller.seek_to(step_path, phase)
      → executor.seek(...)              (records resume target; no execution yet)
      → model.seek_step / seek_phase    (Step n/N, Phase n/N update; timer resets)
      → publish DV display (+ hw)
[resume] operator clicks Play/Resume
  → executor.resume() → checkpoint consults _resume_target
      same step  → phase loop jumps to target phase (no step-hook rerun)
      diff step  → unwind to _run_steps → run target frame from start_phase_index
  → step_started/phase_started → controller → model (normal #467 flow)
```

## Error handling / edge cases

- `seek` while **not paused** is a no-op (guarded) — selection during a live run
  doesn't perturb execution.
- Target path no longer exists (tree edited while paused): `resolve_seek` returns
  `None`; `seek_to` logs and leaves the resume target unchanged.
- Stop while paused already clears `pause_event`; the resume-target is irrelevant
  on a stop (terminal `reset()`).
- Seeking past the last phase / before the first is clamped.

## Testing (pure, no Qt/threads)

- `tests/test_executor_seek.py` — `resolve_seek` (target resolution, clamping,
  missing path); `seek()` guarded to paused-only; the same-step-vs-different-step
  decision logic (extracted pure).
- `tests/test_protocol_status_model.py` (extend) — `seek_step`/`seek_phase`: a
  paused sequence asserts counters set (not incremented) and the relevant
  clock(s) read 0 for both elapsed and active and stay frozen until `resume`.
- `tests/test_protocol_status_controller.py` (extend) — `seek_to` with a stub
  executor + manager asserts `executor.seek` called and the model updated.

Full pause→seek→resume threading is integration-level (out of unit scope).

## Scope / non-goals

- Precise phase-resume for **duration-mode** steps → **#477**.
- No change to pause/stop semantics beyond the resume redirect.
- No persistence of seek state across app restarts.

## References

- Predecessor: #467 / PR #470; design `docs/superpowers/specs/2026-06-16-protocol-status-trackers-design.md`.
- Follow-up: #477 (duration-mode precise phase-resume). Umbrella: #361.
