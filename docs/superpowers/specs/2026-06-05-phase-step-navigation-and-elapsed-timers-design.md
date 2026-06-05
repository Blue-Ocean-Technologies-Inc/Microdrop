# Phase/step navigation + pause-aware elapsed timers — design

Date: 2026-06-05
Area: `pluggable_protocol_tree` (executor, RoutesHandler, ProtocolTreePane, StatusBar/NavigationBar)

## Problem

The pluggable protocol tree's pause-time navigation is broken, and the status
bar reports nonsensical times.

1. **Navigation doesn't reposition the run.** On pause, the pane rebuilds a
   phase list with `iter_phases(...)` and prev/next-phase only *publishes* that
   phase's electrodes. Resume continues from wherever the worker froze
   mid-dwell, ignoring the navigation. The re-derived list also excludes
   **dynamically-added** phases (duration-loop) and can't cross step boundaries.
2. **No phase-level seek.** The executor knows only *steps* (`_start_step_path`);
   phases live inside `RoutesHandler` on the worker thread, with no phase index
   anyone can seek to.
3. **Status `x/y` overflows `y`.** `step_elapsed = now - _step_started_at` keeps
   counting through a pause (the start timestamp isn't shifted), so after resume
   elapsed jumps past the target.

## Goals

- While **paused**, the user can navigate **phases** (prev/next) and **steps**
  (first/prev/next/last). Navigation **actuates live** (drives device + DV to
  that phase's electrode state) and updates the status to that phase.
- Pressing **play** after navigating **restarts the run from the selected
  phase** (`0s / phase_duration`), continuing the protocol forward from there
  with full live behavior — "as if continuing from that phase".
- Pressing **resume** when the user did **not** navigate continues exactly where
  the worker froze; timers pick up where they left off.
- The user can navigate through the **whole history of the current step's
  phases**, including dynamically-added ones.
- Status never shows elapsed `x` greater than target `y`. Add ticking
  **Elapsed Phase / Elapsed Step / Elapsed Protocol** labels beside the existing
  readouts; all timers are **pause-aware** (paused time is not counted).

## Non-goals

- Whole-run phase history. Memory is bounded to the **current step's** phases
  only (see Timeline lifecycle).
- Resuming a dynamic duration loop on its *original* time budget after a seek —
  a seek-restart into a duration-loop step uses a **fresh** budget from the
  chosen phase.
- Keyboard-shortcut redesign (existing shortcuts may map to the same handlers,
  but the spec is about the prev/next buttons' behavior).

## Design

### 1. Per-step phase timeline (recording)

`PhaseRecord` (small value object): `step_path: tuple`, `phase_index: int`
(0-based within the step), `electrodes: list[str]`, `channels: list[int]`,
`duration_s: float`.

New executor signal: **`phase_recorded = Signal(object)`** carrying a
`PhaseRecord`. `RoutesHandler._run_phase` emits it as each phase starts (it
already computes `electrodes`/`channels` and knows `per_phase_dwell` and the
row path). The existing `phase_started(int,int,float)` signal stays for the
status index; `phase_recorded` adds the per-phase electrode payload + step path
the pane needs to navigate and to actuate live.

**Pane store + lifecycle (memory-bounded):**
- `self._phase_timeline: list[PhaseRecord]` — the **current step's** phases.
- Appended on `phase_recorded`.
- **Cleared on `step_started`** (a new step begins) — so only one step's phases
  are ever held.
- On pause, `self._phase_timeline` is a snapshot of the phases the paused step
  has emitted so far; it is also cached as `self._recorded_step_timeline`
  (keyed by the paused step's path) so navigating away and back to the paused
  step restores the *recorded* (dynamic-inclusive) list rather than a derived one.

### 2. Navigation while paused

A single **navigation cursor** describes where the user is currently looking:
`(cursor_step_path, cursor_phase_index)`. The phase list under the cursor is
`self._phase_timeline`.

- **Prev/next phase** move `cursor_phase_index` within `self._phase_timeline`
  (clamped to its bounds).
- **First/prev/next/last step** (while paused) move `cursor_step_path` to
  another step and **rebuild** `self._phase_timeline` for it:
  - If the target step is the **paused step**, restore the cached recorded
    timeline.
  - Otherwise **derive** it via `iter_phases(...)` (structural phases; a
    not-yet-run step has no recording). "If they exist" — an empty derivation
    (no electrodes/routes) yields an empty timeline and the phase controls
    disable.
  - Reset `cursor_phase_index` to 0.

On every cursor move:
- **Actuate live:** publish `PROTOCOL_TREE_DISPLAY_STATE` (always) and
  `ELECTRODES_STATE_CHANGE` (gated on the run's preview mode) for the cursor
  phase's electrodes/channels — same publish path the current
  `_publish_paused_phase` already uses.
- **Update status to the cursor phase:** phase index = cursor (+1 for display),
  phase target = cursor phase's `duration_s`, **Elapsed Phase resets to 0 and is
  not running** (waits for play). Elapsed Step/Protocol are left frozen at their
  paused values (navigation doesn't advance wall-clock).
- **Arm a pending seek:** `self._pending_seek = (cursor_step_path,
  cursor_phase_index)`.

Navigation is only active while paused; entering pause arms the cursor at the
frozen phase, `_pending_seek = None` until the user actually moves.

### 3. Play = seek-restart; Resume = continue

- **Resume** (no navigation, `_pending_seek is None`): `executor.resume()` as
  today; the worker unparks and continues the frozen phase. Pause-aware timers
  continue.
- **Play after navigating** (`_pending_seek` set): the pane calls
  `executor.seek_restart(step_path, phase_offset, preview_mode)`:
  - Stops the paused worker (`stop_event` + clear pause) and **joins** it
    (bounded; cooperative sleep makes the stop land within ~`_SLICE_S`).
  - **Suppresses the terminal signal** for this internal stop (no
    `protocol_aborted` → no teardown / run-summary dialog).
  - Starts a fresh run with `start_step_path=step_path` and the new
    `start_phase_offset=phase_offset`.
  - Timers reset (Protocol/Step/Phase elapsed start at 0 for the new run).

**Executor `start_phase_offset`:**
- `start(start_step_path, start_phase_offset, preview_mode)` stores
  `_start_phase_offset`; `run()` passes it into the **start step's** StepContext
  (e.g. `step_ctx.start_phase_offset`), then clears it so later steps are
  unaffected — mirroring how `skip_until` works for `_start_step_path`.
- `RoutesHandler.on_step` reads `ctx.start_phase_offset` (default 0) and begins
  at that phase:
  - **Static path:** run `phases[offset:]`; the first emitted phase carries
    `phase_index = offset` so the status continues from the navigated number.
  - **Dynamic path:** fast-forward the deterministic phase generation by
    `offset` (advance the generator, no publish/dwell/hold for skipped phases),
    set the loop's `step_start` after the skip (fresh budget from that phase),
    and number `running_idx` from `offset`.

### 4. Pause-aware timers + elapsed labels

Replace "start timestamp, elapsed = now − start" with an accumulator per timer.
Introduce a tiny helper (e.g. `ElapsedTimer`): `accum: float`,
`running_since: float|None`; `start()`, `pause()` (folds the running interval
into `accum`, clears `running_since`), `reset()`, and `value()` = `accum +
(now − running_since if running else 0)`.

Three instances on the pane: **protocol**, **step**, **phase**.
- `step_started` → reset+start step timer and phase timer; protocol timer starts
  at `protocol_started`.
- `phase_started` → reset+start the phase timer.
- **Pause** → `pause()` all three (display freezes at the frozen values).
- **Resume** (continue) → `start()` all three (pick up where left off).
- **Manual phase navigation** → `reset()` the phase timer and leave it **not
  running** (Elapsed Phase shows 0 until play).
- **Seek-restart** → reset all three for the new run.

Status labels (in `StatusBar`):
- **Keep** existing readouts, now driven by the pause-aware timers:
  - `Phase i/N  e / t` (or `Phase i  e / t` when total unknown). `e` is the
    pause-aware phase elapsed; `t` is the phase target (already grown by
    `phase_extended` for held phases), so `e` never exceeds `t` from pausing.
    Belt-and-suspenders: clamp the displayed `e` to `t`.
  - `Step Time`, `Total Time` — pause-aware.
- **Add** three ticking labels beside them: **Elapsed Phase**, **Elapsed Step**,
  **Elapsed Protocol** (pure wall-clock, pause-aware). (If this duplicates
  `Step Time`/`Total Time`, those may be dropped during implementation review;
  the phase-elapsed label is the genuinely new one.)

### 5. NavigationBar

- While paused, step buttons (`btn_first/prev/next/last`) reposition the
  protocol cursor (build timeline + arm seek) instead of only selecting a tree
  row. While **not running**, they keep their current free-mode select behavior.
- Phase controls (`btn_prev_phase/next_phase`) already appear on pause via
  `split_play_button_to_phase_controls`; their enable state follows the cursor
  bounds.
- The "resume" control restarts-from-cursor when `_pending_seek` is set, else
  continues.

## Components / files touched

- `execution/signals.py` — add `phase_recorded(object)`.
- `execution/step_context.py` — add `start_phase_offset` field (default 0).
- `execution/executor.py` — `start(..., start_phase_offset=0)`,
  `_start_phase_offset`, pass into start step ctx + clear; `seek_restart(...)`
  with terminal-signal suppression.
- `builtins/routes_column.py` — emit `phase_recorded` in `_run_phase`; honor
  `ctx.start_phase_offset` in static + dynamic paths (skip/fast-forward, phase
  numbering, fresh budget).
- `views/protocol_tree_pane.py` — timeline store + lifecycle; cursor model;
  paused step/phase navigation; `_pending_seek`; resume-vs-restart; pause-aware
  `ElapsedTimer`s; status rendering.
- `views/navigation_bar.py` / `StatusBar` — three elapsed labels; step buttons'
  paused behavior wiring.

## Edge cases

- **Navigate to an empty/derive-less step** → empty timeline, phase controls
  disabled; play seeks to that step at phase 0.
- **Navigate away from and back to the paused step** → recorded timeline
  restored from cache (dynamic phases preserved).
- **Stop while paused/navigating** → normal abort/teardown (seek suppression
  only applies to the internal `seek_restart`).
- **Preview mode** → navigation actuates DV only (no hardware), matching the
  run's preview flag; seek-restart preserves preview mode.
- **Dynamic-loop seek** → fresh budget from the chosen phase; `t`/`i` reflect
  that phase; subsequent steps run in full.

## Testing

- `RoutesHandler` emits `phase_recorded` with correct electrode/channel/path per
  phase (static + dynamic), and honors `start_phase_offset` (static slice;
  dynamic fast-forward + fresh budget + numbering) — deterministic `_monotonic`.
- `ElapsedTimer`: accumulate/pause/resume/reset; `value()` excludes paused time.
- Pane: pause builds cursor at frozen phase; prev/next phase + step move the
  cursor, rebuild timeline (recorded vs derived), arm `_pending_seek`, actuate;
  resume (no nav) continues; play (nav) calls `seek_restart`; status never shows
  `e > t`.
- Executor: `seek_restart` stops+restarts seeked without emitting
  `protocol_aborted`.

## Out of scope (future)

- Whole-protocol scrubbing across completed steps' real (dynamic) phases.
- Persisting/visualizing the timeline beyond the current step.
