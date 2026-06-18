# Protocol Timeline Seek Bar — Design

**Date:** 2026-06-18
**Plugin:** `pluggable_protocol_tree`
**Status:** Approved (brainstorming) — pending implementation plan

## Goal

Add a video-style **timeline seek bar** to the pluggable protocol tree: a
horizontal track with a tick per protocol step and a draggable playhead, so the
user can scrub between steps (and, for the current step, between its phases) the
way they would seek a video. It is a thin **view**; all navigation intent is
redirected through the existing controller, which moves the protocol's current
step first and then the phase within it. The rest of the UI reacts to those
model changes in the existing event-driven way.

## Scope decisions

- **Granularity:** steps-only track; **phase sub-ticks appear only for the
  current step** (like a video chapter expanding). No group tier.
- **Run interaction:** seeking is always interactive. While a protocol is
  **actively running** (not paused), a scrub is **preview-only** — it updates
  the model position and the DeviceViewer overlay, but the live executor keeps
  running and reasserts its real position at the next step/phase boundary.
  Execution-affecting seeks happen when **paused/idle**, reusing the executor's
  existing paused-guard. No executor changes.
- **Form factor:** a **sub-widget of the existing dock pane**, sibling to
  `NavigationBar` and `QuickActionBar` — *not* a new dock pane. This means the
  dock pane already owns the live `RowManager`, `ProtocolExecutor`, and
  `ProtocolStatusController`/`ProtocolStatusModel`; there is no instance-sharing
  problem to solve.
- **Rendering:** custom `paintEvent` (full control over the two-tier
  major/minor ticks and playhead), not a styled `QSlider`.
- **Placement:** directly under the nav bar, above the tree.

## What already exists (reused, not rebuilt)

Built for issue #471 ("navigate step/phase while paused"):

- `RowManager.iter_execution_frames()` — the canonical ordered step sequence
  (groups flattened, repetitions expanded). Index → row mapping for scrubbing.
- `ProtocolStatusController.seek_to(step_path, phase_index)` — Qt-free
  orchestration: records an executor resume target (paused-guarded) and SETs the
  model's step/phase counters. Calling it while actively running updates the
  model + preview only; the executor ignores the seek. (= the B1 behavior.)
- `ProtocolStatusController.preview_phase(step_path, phase_index, preview_mode)`
  — publishes the phase's electrodes to the DeviceViewer overlay (and hardware
  unless in preview mode).
- `ProtocolStatusController._phase_total_for(row)` / `_phases_for(row)` —
  enumerate a step's phases (the count drives the phase sub-ticks).
- `ProtocolStatusModel` single source of truth: `current_step_path`,
  `step_index`, `step_total`, `phase_index`, `phase_total`, `running`, `paused`.
- `PluggableProtocolDockPane` already observes these model traits with
  `dispatch="ui"` and already builds/wires the sibling bars in
  `create_contents`.

## Architecture (MVC)

```
TimelineBar (View, Qt)                PluggableProtocolDockPane (Controller)        ProtocolStatusModel / RowManager (Model, Qt-free)
─────────────────────                 ──────────────────────────────────────        ────────────────────────────────────────────────
emits step_seek_requested(i)  ─────▶  resolve i → row via iter_execution_frames()
emits phase_seek_requested(p) ─────▶  status_controller.seek_to(path, phase)  ────▶  current_step_path / phase_index SET
                                      status_controller.preview_phase(...)            (executor honored only when paused)
set_position(...) ◀───────────────── @observe(model: step/phase counters) ◀────────  trait change events (dispatch="ui")
rebuild(labels)   ◀───────────────── @observe(manager: rows_changed)      ◀────────  structural change
set_running(bool) ◀───────────────── @observe(model: running)            ◀────────  run-state change
```

The View knows nothing about the executor or controller; it emits intent and
exposes push methods. The Controller is the existing dock pane — no new
controller class. The Model is unchanged.

## Component 1 — `TimelineBar` (new: `views/timeline_bar.py`)

Pure `QWidget`, no business logic. Follows `NavigationBar` conventions:
theme-aware styling re-applied on `QApplication.styleHints().colorSchemeChanged`
(deferred one event-loop tick, per the existing `_on_color_scheme_changed`
pattern); `QSizePolicy(Expanding, Fixed)` so it hugs its height.

**Render (`paintEvent`):**
- A horizontal track spanning the widget width.
- One **major tick per execution step**, evenly spaced across `step_total`.
- A **playhead** marker at `step_index`.
- For the **current step only**, if `phase_total > 1`, finer **minor ticks**
  subdividing that step's segment into `phase_total` slots, with the phase
  playhead at `phase_index`.
- Step name / dotted-path shown as a hover tooltip (reuse the row's
  `dotted_path()` / `name`).

**Outward signals (the only coupling):**
- `step_seek_requested = Signal(int)` — emitted with the 0-based execution step
  index nearest the click/drag-release on the major track.
- `phase_seek_requested = Signal(int)` — emitted with the 0-based phase index
  nearest the click/drag-release within the current step's segment.

Drag is debounced/coalesced so a scrub emits on meaningful change (and on
release), not per pixel.

**Push API (called by the controller):**
- `rebuild(step_labels: list[str])` — set/refresh the major-tick count and
  per-tick labels when the protocol structure changes.
- `set_position(step_index, step_total, phase_index, phase_total)` — move the
  playhead and (re)draw phase sub-ticks for the current step.
- `set_running(running: bool)` — toggle the preview-mode visual hint (e.g. a
  subtle "preview" accent while running); the bar stays interactive regardless.

## Component 2 — Controller wiring (in `views/dock_pane.py`)

No new class. In `PluggableProtocolDockPane`:

1. **Build & place.** In `create_contents`, construct `TimelineBar` and add it to
   the layout directly under the nav bar, above the tree.
2. **Intent → model.**
   - `step_seek_requested(i)` → resolve `row = nth execution frame i` (from
     `manager.iter_execution_frames()`), then
     `status_controller.seek_to(row.path, 0)` + `preview_phase(row.path, 0, preview)`.
     This converges on the *same* path the nav-bar prev/next buttons already use
     (`_select_step`), so move the tree selection there too for consistency.
   - `phase_seek_requested(p)` → keep the current step path,
     `status_controller.seek_to(path, p)` + `preview_phase(path, p, preview)`.
   - Both are safe while running (model + preview update only) and execution-
     affecting only when paused — no extra run-state branching needed beyond
     what `seek_to` already enforces.
3. **Model → view.** Extend the existing `dispatch="ui"` observers:
   - on `current_step_path` / `[step_index, step_total, phase_index, phase_total]`
     change → `timeline.set_position(...)`.
   - on `manager.rows_changed` → `timeline.rebuild(...)`.
   - on `running` change → `timeline.set_running(...)`.

### Index ↔ position alignment (must verify in the plan)

The timeline scrubs by linear step index and must use the **same indexing the
executor uses** when it emits `step_started (row, step_index, step_total)` —
otherwise the playhead and a scrub target can disagree. The plan must confirm
that `iter_execution_frames()` enumeration order and the executor's
`step_index`/`step_total` are the same sequence, and reuse one helper for the
index→row resolution rather than recomputing it.

## Testing

- **`TimelineBar` unit (Qt, no engine):** construct, `rebuild` with N labels,
  `set_position`, and assert the emitted signal index for a synthesized click at
  a known x (major track and phase sub-track). Pure-view, fast.
- **Controller wiring (integration):** with a small built protocol and a
  `ProtocolStatusController`, drive `step_seek_requested`/`phase_seek_requested`
  and assert the model's `current_step_path`/`phase_index` move and a
  `PROTOCOL_TREE_DISPLAY_STATE` preview is published; assert that while running
  (not paused) the executor position is unaffected (B1).
- Place tests per the project's Redis/hardware partitioning; the view test needs
  neither.

## Out of scope (follow-ups)

- Group bands / a third visual tier.
- Mid-run execution redirection (B2: auto-pause/seek/resume, or a live executor
  jump). Dynamic duration loops can't resume mid-phase precisely until #477.
- Fast-preview throttling beyond a simple drag debounce.
