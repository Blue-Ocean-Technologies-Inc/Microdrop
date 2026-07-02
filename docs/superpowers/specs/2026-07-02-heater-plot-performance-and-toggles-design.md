# Heater Plot: Performance + Line Toggles + Pause/Stop — Design

**Date:** 2026-07-02
**Scope:** `heater_controls_ui/plots/` (model, canvas, dock pane, consts) and
its tests.
**Goal:** the live plot must never drag the GUI down, individual lines must be
toggleable (e.g. show only heater1's PID), and the user must be able to pause
or fully stop the plot. MVC separation: pause/stop/visibility are model traits;
the canvas polls and draws; buttons in the pane just set traits.

## Performance problems in the current draft

1. `_redraw` clears both axes, recreates every Line2D, re-styles both axes and
   rebuilds both legends every 500 ms tick — the classic matplotlib
   anti-pattern; cost grows with series count and runs even when nothing
   changed.
2. Redraws continue while the pane is hidden or tabbed-behind.
3. Redraws continue when telemetry has stalled (identical data).

## Design

### Model (`plots/model.py`) — Qt-free HasTraits, proper traits

Convert the plain instance variables to class-level trait declarations
(`_lock = Instance(threading.Lock)` with the `__lock_default` method, `Dict()`
/ `List()` buffers, `Any` t0) per the always-Traits directive. New public
traits:

- `paused = Bool(False)` — freeze the plot. The canvas skips sampling and
  drawing; telemetry still folds into the latest values, so resuming continues
  seamlessly (with a visible time gap).
- `enabled = Bool(True)` — full stop when False: `apply()` ignores telemetry
  and an `@observe("enabled")` handler clears all history (blanking the plot).
  Re-enabling starts fresh.
- `hidden_series = Set()` — role-prefixed series keys (`"sensor:inlet"`,
  `"pid:tec1"`, `"pwm:tec1"`) the user has hidden via the legend. Role
  prefixes are required because a heater's PID and PWM series share the
  heater name.
- `revision = Int(0)` — bumped (under the lock) whenever the drawable buffers
  change: on every appended sample and on clear. The canvas redraws only when
  the revision moved.

### Canvas (`plots/canvas.py`) — persistent artists

- **Artists created once per series, updated with `line.set_data()`**; colors
  reassigned by sorted index so they match the old per-tick behavior. Vanished
  series get their lines removed. None values map to NaN for `set_data`.
- **Axes styled once** at init and again only when the theme flips
  (dark/light checked per tick — a cheap comparison).
- **Legends rebuilt only when the series set changes**, not per tick.
- **Tick early-outs:** hidden widget (plus `hideEvent` stops / `showEvent`
  restarts the QTimer), `model.paused`, and unchanged `model.revision`.
  Sampling only runs while `model.enabled`.
- **Clickable legend:** legend lines/labels get pickers; a pick toggles the
  series key in `model.hidden_series`, applies visibility immediately
  (hidden line + 25 %-alpha legend entry), rescales via
  `relim(visible_only=True)` + `autoscale_view()`, and `draw_idle()`s.
  Hidden lines cost nothing to draw, so toggling is also a perf tool.
- Axis limits: temperature axis autoscales both; PWM keeps its fixed
  −5..105 y (autoscale x only).

### Dock pane (`plots/dock_pane.py`) — Pause + Stop buttons

A toolbar row: NavigationToolbar + stretch + two checkable QToolButtons using
the icon font (`ICON_PAUSE`, `ICON_STOP`):

- **Pause** → `model.paused = checked`. Tooltip explains data keeps arriving.
- **Stop** → `model.enabled = not checked`; also disables the Pause button
  while stopped. Tooltip warns history is dropped.

### Consts (`plots/consts.py`)

- Remove the `plot_listener_name` re-export (one-constant-one-name directive);
  the dock pane imports it from its owner `heater_controls_ui.consts`.
- Fix `SENSOR_PALETTE`: drop the duplicated `WARNING_COLOR` entry.
- Add button tooltip constants.

## Testing

Extend `heater_controls_ui/tests/test_plot_model.py`: `enabled=False` ignores
telemetry and clears history; `revision` bumps on sample/clear and not on
empty ticks; `paused`/`hidden_series` traits exist and default sanely. The
canvas/pane are verified by import smoke + the user's manual app run (no
pytest runs per project preference).

## Out of scope

Persisting hidden-series/pause state across sessions; blitting (unnecessary at
2 Hz once artists are reused); downsampling (500-point window is small).
