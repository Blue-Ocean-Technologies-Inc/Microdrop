# Status-Bar Extension Point (`microdrop_status_bar`) — Design

**Date:** 2026-07-03
**Scope:** new `microdrop_status_bar` plugin;
`template_status_and_controls/base_dock_pane.py`;
`microdrop_application/task.py`; the five contributing device plugins
(`dropbot_status_and_controls`, `opendrop_status_and_controls`,
`mock_dropbot_status`, heater `heater_controls_ui`, magnet
`peripherals_ui`); frontend plugin registration (`plugin_consts.py` /
run scripts).
**Goal:** status-bar icons become Envisage extension-point contributions
managed by one central plugin — no pane ever touches the `QStatusBar`
directly, spacing is uniform by construction, and hot load/unload cleans
the bar automatically. Zero visible behavior change beyond spacing
consistency.

## Problems

1. **Every pane hand-places its own widgets.** `_populate_status_bar`
   computes an insert index (`STATUS_BAR_INSERT_INDEX = 2`), manufactures
   a spacer per widget (`STATUS_BAR_SPACER_WIDTH`), and pokes
   `task.window.status_bar_manager.status_bar` directly.
2. **Every pane hand-tracks teardown.** `_status_bar_inserted_widgets`
   exists only so `destroy()` can remove exactly what was added — per-pane
   bookkeeping for what is really a central concern.
3. **Spacing is emergent, not guaranteed.** Each pane inserts its own
   spacers; nothing ensures one uniform gap between adjacent icons.
4. **Status-bar code is scattered.** The bar itself is created in
   `MicrodropTask.activated()`; icon placement lives in the pane template;
   no single point of change.

The codebase already has the exact mechanism for this:
`MessageRouterPlugin` declares an `ExtensionPoint`, calls
`connect_extension_point_traits()` in `start()`, applies current
contributions, then observes `<name>_items` deltas for runtime changes.
This design replicates that shape for status-bar icons.

## Design

### 1. New plugin: `microdrop_status_bar`

```
microdrop_status_bar/
├── __init__.py
├── consts.py    # PKG, PKG_name, STATUS_BAR_ICONS extension-point id,
│                # ICON_SPACING (10), DEFAULT_MESSAGES (["Free Mode"])
└── plugin.py    # StatusBarPlugin
```

`StatusBarPlugin(Plugin)`:

- **Extension point** (mirrors `MessageRouterPlugin.actor_topic_routing`):

  ```python
  status_bar_icons = ExtensionPoint(
      List(),  # QWidget instances, contributed at runtime
      id=STATUS_BAR_ICONS,
      desc="Widgets to show in the app status bar; the manager owns "
           "placement, spacing, and removal",
  )
  ```

- **Creates the status bar.** `start()` calls
  `connect_extension_point_traits()`; a null-guarded, idempotent
  `@observe("application:application_initialized")` sets
  `window.status_bar_manager = StatusBarManager(
  messages=[DEFAULT_STATUS_MESSAGE], size_grip=True)`, applies the
  `setContentsMargins(30, 0, 30, 0)` margins, and appends **one
  container widget** (`QWidget` +
  `QHBoxLayout` with `spacing=ICON_SPACING`, zero contents margins) as a
  permanent widget. This wholly replaces the status-bar block in
  `MicrodropTask.activated()`, which is deleted.
- **Applies current + observes deltas.** After building the container it
  adds every widget already in `self.status_bar_icons` (contributions can
  arrive before the window exists), then reacts to changes:
  - `@on_trait_change("status_bar_icons_items")` — plugin-driven
    contribution changes (a contributing plugin mutating its trait,
    plugins added/removed from the manager). Added widgets →
    `layout.addWidget`; removed widgets → `layout.removeWidget` +
    `deleteLater()`.
  - `@observe("status_bar_icons")` — index-less wholesale replacement,
    covered for completeness exactly as in the router.
- **Ownership rule:** once contributed, the manager owns a widget's
  status-bar lifecycle — removal from the extension point means removal
  from the bar and `deleteLater()`. Contributors keep behavior wiring
  (signals, observers, tooltips) but never delete contributed widgets
  themselves.

Equal spacing is a property of the single `QHBoxLayout` — no spacer
widgets exist anywhere.

### 2. Contributing plugins

All five contributors subclass
`template_status_and_controls.base_plugin.BaseStatusPlugin`, so the
initially-empty runtime contribution is declared **once** there:

```python
status_bar_icons = List(contributes_to=STATUS_BAR_ICONS)
```

No per-device `plugin.py` changes are needed.

### 3. `base_dock_pane.py` — panes build widgets, never place them

- `_populate_status_bar` keeps its trigger points (the
  `@observe("task:window:status_bar_manager")` decorator and the
  `on_live_mounted()` hot-mount path) and its idempotence guard, but its
  body becomes: build `self.status_bar_icon`, apply tooltip, wire
  `colorSchemeChanged` → `_refresh_status_bar_tooltip`, then

  ```python
  self._contribution_plugin.status_bar_icons.extend(
      self._create_status_bar_widgets())
  ```

  Mutating the plugin's list fires the extension-point `_items` event →
  the manager inserts the widgets.
- **Plugin lookup:** `_contribution_plugin` resolves via
  `self.task.window.application.get_plugin(plugin_id)`. Default
  `plugin_id` is derived from the pane id — `"<pkg>.dock_pane"` →
  `"<pkg>.plugin"` — overridable via a class-level trait for panes that
  don't follow the convention (all current panes do).
- `_teardown_status_bar` removes the pane's contributed widgets from the
  plugin's `status_bar_icons` list (the manager pulls them from the bar
  and deletes them), disconnects `colorSchemeChanged`, and drops
  references. Removal is idempotent: widgets already gone from the list
  (e.g. the plugin was hot-unloaded first) are skipped.
- **Deleted:** `STATUS_BAR_INSERT_INDEX`, `STATUS_BAR_SPACER_WIDTH`, the
  `horizontal_spacer_widget` import, the `_status_bar_inserted_widgets`
  trait, and all direct `status_bar` access.
- **Unchanged:** widget factories (`_create_status_bar_icon`,
  `_create_status_bar_widgets`), tooltip builders, model→color observers.
  `RealtimeModeIconMixin` and the heater's overrides work as-is — they
  only override factories.

### 4. Hot load/unload

- Pane teardown removes its widgets from its plugin's contribution list →
  manager removes them from the bar.
- Independently, removing a plugin from the plugin manager makes Envisage
  fire removed-contribution events for everything that plugin contributed
  — the manager cleans the bar even if a pane's teardown never ran. Both
  paths are safe to run in either order (list removal is idempotent;
  the manager ignores widgets it no longer holds).

### 5. Wiring & edge cases

- `StatusBarPlugin` is added to the frontend plugin list in
  `plugin_consts.py` (and any run script that assembles plugins
  explicitly). It has no ordering dependency: contributions before the
  window exists are applied when the container is built.
- **Icon order** = contribution arrival order (deterministic from pane
  creation order). The current insert-at-index-2 behavior wasn't
  meaningfully ordered either; no one depends on a specific order.
- **App shutdown:** the container dies with the window; the manager
  guards removal with the same `RuntimeError`/broad-`Exception` guards
  the pane teardown uses today.
- **Single window:** the app is single-window; the manager binds once at
  `application_initialized` and ignores later re-fires.
- **Why `application_initialized`, not `active_window`:** `active_window`
  fires on the first Qt focus-activation, mid `window.open()` — before
  dock-pane contents exist (their `task:window:status_bar_manager`
  observers would run against half-built panes), and before pyface's
  task-activation sweep (`TaskWindow._update_traits_given_new_active_state`)
  overwrites `window.status_bar_manager` with `task.status_bar` (None),
  discarding an early-installed manager. This is also why the legacy code
  ran in `task.activated()` — that timing was load-bearing.
  `application_initialized` fires via `set_trait_later` after
  `_create_windows()` returns, safely past both hazards.
- ~~Other status-bar citizens are untouched~~ — superseded by Phase 2
  (below): the joystick and recording icons are migrated too.

## Phase 2 (same branch): icon priorities + last two direct inserts

User-approved follow-up 2026-07-03: every icon flows through the
extension point; no `insertPermanentWidget` outside `microdrop_status_bar`.

- **Priority:** contributions stay bare QWidgets. An optional plain
  attribute `status_bar_icon_priority` (int, default 0) orders the
  container: sorted by `(priority, arrival order)`, lower = further
  left; positives land right of defaults. `consts.py` adds
  `ICON_PRIORITY_DEFAULT = 0`, `ICON_PRIORITY_LEFT = -1`,
  `ICON_PRIORITY_LEFTMOST = -2`. `_apply_icon_changes` inserts at the
  index of the first existing widget with a strictly greater priority.
- **Joystick → device_viewer** (owner of the gamepad service): the
  dock pane creates the QLabel (same glyph/font/colors), tags it
  `ICON_PRIORITY_LEFTMOST`, hands it to the gamepad service
  (`svc.gamepad_icon`), and contributes it via a new
  `DeviceViewerPlugin.status_bar_icons` trait. The service colors the
  icon directly (green/controller-name vs grey/"Gamepad disconnected",
  logic moved from `StatusBarManager._apply_gamepad_label_state`); its
  re-apply observer watches `gamepad_icon`. The deferred
  `QTimer.singleShot(0, attach_gamepad_indicator)` ordering hack is
  deleted — priority replaces timing.
- **Recording icon → contribution**, tagged `ICON_PRIORITY_LEFT`
  (right of joystick, left of device icons), still hidden until the
  record toggle fires; the `insertPermanentWidget(1, ...)` call is
  deleted.
- **StatusBarManager slims down:** `gamepad_label`, `gamepad_status`,
  `_gamepad_attached`, `attach_gamepad_indicator`,
  `_gamepad_status_updated`, `_apply_gamepad_label_state`,
  `STATUSBAR_ICON_SPACING`, `STATUSBAR_FIRST_PERMANENT_INDEX`, and the
  joystick-related imports are deleted; the manager handles messages,
  the center label, and theming only. HUD messages keep using the
  manager unchanged.
- **Visible change (accepted):** joystick/recording gaps become the
  container's uniform `ICON_SPACING` instead of the old style-default
  gaps.

## Testing

Manual (per project preference — no automated test runs):

1. Launch the app — the dropbot status icon + realtime toggle appear with
   even spacing; tooltips and theme switching work.
2. Toggle the magnet group via Tools → Peripherals — its icon appears on
   load and disappears on unload, spacing stays uniform.
3. Quit the app — no teardown errors in the log.
