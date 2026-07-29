# Idle Phase Navigation — Design (issue #493)

**Issue:** [#493 — Allow navigating phases when protocol not running](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/493)
**Date:** 2026-07-29
**Branch:** `feat/493-idle-phase-navigation`

## Problem

When a protocol is not running, selecting a step only draws its route lines in the
device viewer. The user cannot step through the route phases or actuate the phase
electrodes. The phase-navigation UI already exists in two places but is gated off
when idle:

- The DV sidebar's Prev/Next-phase buttons (`RouteLayerView.run_controls`) are only
  *visible* during sidebar route playback (`route_execution_service_executing` /
  `_paused`), even though the whole toolbar is *enabled* precisely when
  `not protocol_running`.
- The protocol tree's navigation-bar phase cluster and the timeline bar's phase
  track drive `ProtocolStatusController.seek_to` / `preview_phase`, which the pane
  only wires up while a run is paused (#471/#477).

Additionally, hardware actuation from idle phase stepping is silently dropped:
`device_view_dock_pane.publish_electrode_update` gates the not-running branch on
`model.free_mode`, which is always `False` while a real step is selected, so
`ELECTRODES_STATE_CHANGE` is never published in that case.

## Goal

An **opt-in "Phase navigation" mode**, toggled by a checkbox synced between the
device viewer sidebar and the protocol tree pane. While the mode is on and no
protocol is running, the user can step/scrub through the phases of the selected
step's routes from either UI, with the phase electrodes highlighted on the device
view and actuated on hardware when realtime mode is enabled. Default behaviour
(mode off) is exactly today's behaviour.

## Decisions (from brainstorming)

- **Actuation respects realtime mode**: highlight always; publish hardware
  actuation only when realtime mode is on and a DropBot is connected — the same
  gate manual electrode clicks use (already the outer condition of
  `publish_electrode_update`).
- **Phase scope**: phases cover all routes whose "play" checkbox
  (`RouteLayer.selected_for_run`) is enabled in the DV sidebar — matching what the
  sidebar's Run button would execute.
- **Stepping UI**: reuse the existing controls — DV sidebar Prev/Next-phase
  buttons, protocol tree navigation-bar phase cluster, and the timeline bar's
  phase track. No new stepping widgets.
- **Architecture**: device-viewer-led (approach A). The DV already owns the step's
  routes, the play-enabled state, the execution params, and a working idle
  phase-stepping engine (`RouteExecutionService`). The protocol tree acts as a
  remote control over pub/sub. The paused-mid-run seek stack (#471) is untouched.

## Design

### 1. Mode toggle, synced

- New checkbox **"Phase navigation"** in both UIs:
  - DV sidebar: with the run controls in `route_selection_view.py`.
  - Protocol tree pane: by the timeline bar, next to the existing
    "show full" checkbox.
- Enabled only when no protocol is running.
- Toggling publishes new topic `ui/phase_navigation_mode` with `"true"`/`"false"`.
  Both plugins subscribe and update their checkbox **without re-publishing**
  (echo guard: only publish on genuine user toggles / forced exits, and ignore
  inbound values equal to current state).
- When a protocol run starts (`PROTOCOL_RUNNING` → true), the mode force-exits and
  publishes `"false"` so both checkboxes clear.

### 2. Engine — `RouteExecutionService` (device viewer)

- On mode-on, build the execution plan via the existing
  `PathExecutionService.calculate_execution_plan_from_params(...)` from the
  play-enabled route layers plus the sidebar execution params, and enter a
  **paused state at phase 0**, applying it through the existing `_apply_phase`.
  No timer runs — pure stepping. The sidebar Run/playback path is unchanged and
  remains available.
- Sidebar Prev/Next-phase buttons become visible while the mode is on (extend
  their `visible_when` beyond executing/paused playback).
- Rebuild triggers:
  - Step selection change → rebuild plan, reset to phase 0.
  - Route play-checkbox toggle or execution-param edit → rebuild plan, clamp the
    current index into the new plan's range.
- Mode-off (or forced exit) → restore the step's normal display: static actuated
  electrodes and route lines, exactly as a fresh step selection renders today.

### 3. Protocol tree — remote control over pub/sub

While the mode is on and idle:

- The navigation bar splits into the phase cluster (existing
  `split_play_button_to_phase_controls`) and the timeline's phase track activates.
- Prev/Next/scrub do **not** call `ProtocolStatusController.seek_to`; instead they
  publish `ui/device_viewer/phase_navigation_request` with
  `{"action": "prev" | "next" | "goto", "index": <int, goto only>}`.
- The DV engine applies the requested phase and publishes
  `ui/device_viewer/phase_navigation_state` with
  `{"phase_index": <int>, "phase_total": <int>}` (0-based index). The tree
  consumes this to move the timeline playhead, update the phase counter label,
  and enable/disable prev/next at the plan boundaries.
- In idle mode the timeline's phase track shows the **full materialized phase
  count** (no route-repeat collapse) — the collapse logic
  (`collapse_phase_view`) stays a run/paused-only concern, so `goto` indices map
  1:1 onto the DV plan.
- Paused-mid-run navigation (#471/#477) is completely unchanged: while a run
  exists, the existing seek stack keeps ownership of these controls.

### 4. Actuation gate fix

In `device_view_dock_pane.publish_electrode_update`, the idle branch becomes:
publish when `free_mode` **or phase-navigation mode is active**:

```python
if (not protocol_running and (free_mode or phase_navigation_mode)) or (
        protocol_running and editable):
```

The outer `realtime_mode and connected` gate stays, giving the agreed
highlight-always / actuate-only-in-realtime behaviour. The
`_actuation_publish_disabled_log_message` diagnostics gain the new condition.

### 5. Edge cases

- No step selected, group row selected, or no play-enabled routes → phase total
  is 0, nav controls disabled, mode stays on harmlessly; selecting a suitable
  step brings it to life.
- Duration-mode / route-repeat steps materialize through the same plan builder
  the sidebar Run already uses — no special casing in this feature.
- Realtime mode off: stepping still highlights phases on the SVG; no hardware
  publishes.
- New topics get constants in `device_viewer/consts.py` (and a re-declared
  literal in `pluggable_protocol_tree` if needed to avoid circular imports,
  matching the `PROTOCOL_TREE_DISPLAY_STATE` precedent) and are documented in
  `MESSAGES.md`.

### 6. Testing

Minimal, per project workflow (GUI is tested manually):

- Small non-GUI unit tests only where nearly free — e.g. the mode echo guard and
  the request/state message handling.
- No GUI/integration test investment.

## Out of scope

- Any change to paused-mid-run seeking (#471/#477).
- Auto-play/animation of phases while idle (the sidebar Run button already
  provides timed playback).
- Per-route solo stepping beyond the existing play checkboxes.
