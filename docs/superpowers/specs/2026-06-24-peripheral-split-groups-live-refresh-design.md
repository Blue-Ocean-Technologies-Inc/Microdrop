# Peripheral plugins: split into two toggle groups + live UI refresh

**Date:** 2026-06-24
**Status:** Approved (design)
**Builds on:** the runtime plugin hot load/unload work (commits `fb48baef`..`d1fd9678` on
`feature/peripheral-hot-load`), which added `PluginGroupManager`, the live dock-pane helper,
protocol-tree column reactivity, and a single Tools → Peripherals toggle.

## Problem

The first cut shipped a single **Tools → Peripherals** toggle that hot loads/unloads the
whole magnet-peripheral trio as one group. Field use surfaced four gaps:

1. **No backend/UI separation.** A user may want the magnet *UI* (dock pane, protocol
   column) without the hardware *backend*, or vice-versa. One toggle can't express that.
2. **Backend doesn't start searching.** When the controller is loaded normally, the app's
   `application_initialized` hook publishes `START_DEVICE_MONITORING_PERIPHERAL`. On a
   runtime hot-load that hook is long past, so the controller loads but never begins
   polling for the magnet board.
3. **Status-bar icon never appears/disappears.** The Z-Stage status icon is wired by
   `@observe("task:window:status_bar_manager")` on `PeripheralStatusDockPane`. On normal
   startup the pane is created *before* the status bar, so the observer fires when the bar
   is set. On a hot-mount the status bar already exists, so the observer never fires and
   the icon is never installed (and thus nothing to remove on unload).
4. **Tools submenu and Preferences tab don't refresh.** The peripheral plugin's
   "Peripherals → Z-Stage → Search Connection" submenu (a `SchemaAddition`) and its
   Preferences tab are gathered once at window/dialog creation. Pyface never updates
   `task.extra_actions` after a plugin starts/stops, and the Preferences dialog is a cached
   singleton service whose `categories`/`panes` are snapshotted at first build. So neither
   reflects a hot-loaded/unloaded plugin.

## Goals

- Replace the single toggle with **two independent toggles** — "Magnet UI" and "Magnet
  Backend" — surfaced in a **Tools-menu dialog** with two checkboxes.
- Enabling the **backend** starts the magnet search immediately.
- The **status-bar icon**, the **Tools submenu**, and the **Preferences tab** appear/
  disappear live as their owning plugin loads/unloads.

## Non-goals

- Distributed/remote backend: the group loads into whatever process runs the toggle (the
  GUI). Correct for single-process / mock / local-full runs; a remote backend process is
  out of scope (deferred, as before).
- Backend-swapping (DropBot ↔ OpenDrop): still the eventual goal, not this change.

## Decisions (locked)

- Selection surface: a **dialog launched from the Tools menu** (not a preferences tab or a
  permanent dock pane).
- The two toggles are **fully independent**. UI can run without the backend (magnet column
  present, just no hardware acks).
- The **magnet protocol column** (`PeripheralProtocolControlsPlugin`) belongs to the **UI
  group**. The backend group is the controller only.
- The dialog **applies on OK** (Cancel is a no-op), not live-per-toggle.
- The menu bar is rebuilt on every enable/disable (cheap; harmless when a group
  contributes no menu actions).
- The old single `magnet_peripherals` group and `PERIPHERALS_ENABLED_KEY` are removed.

## Architecture

Two named plugin groups managed by the existing `PluginGroupManager`, driven by a
Tools-menu dialog, plus three "refresh a startup-snapshotted UI surface against the live
extension set" mechanisms (status icon, menu bar, preferences tabs).

```
Tools menu
  └─ "Manage Peripherals…"  (ManagePeripheralsAction, a TaskAction)
        └─ opens PeripheralsManagerDialog (livemodal, 2 checkboxes)
              └─ on OK → PluginGroupManager.apply(task, {magnet_ui: bool, magnet_backend: bool})
                            ├─ enable/disable "magnet_ui"      group
                            └─ enable/disable "magnet_backend" group
PluginGroupManager.enable(group):
   add+start plugins → capture service ids → mount dock panes (→ pane.on_live_mounted())
   → rebuild_menu_bar_live → publish post_enable_publish_topic (backend only) → set flag
PluginGroupManager.disable(group):
   remove dock panes → stop+remove plugins → unregister services
   → rebuild_menu_bar_live → clear flag
```

### Component 1 — Two plugin groups (`plugin_group_manager.py`, `consts.py`)

`PluginGroup` gains two fields:
- `enabled_key: Str` — the app-globals flag for persistence/restore.
- `post_enable_publish_topic: Str` — optional; if set, the manager publishes an empty
  message to it after a successful enable.

`PluginGroupManager._groups_default` returns two groups:

| group id | plugins (load order) | enabled_key | post_enable_publish_topic |
|---|---|---|---|
| `magnet_ui` | `PeripheralProtocolControlsPlugin`, `PeripheralUiPlugin` | `PERIPHERAL_UI_ENABLED_KEY` | — |
| `magnet_backend` | `PeripheralControllerPlugin` | `PERIPHERAL_BACKEND_ENABLED_KEY` | `START_DEVICE_MONITORING_PERIPHERAL` |

New constants in `microdrop_application/consts.py` (replacing `MAGNET_PERIPHERALS_GROUP` /
`PERIPHERALS_ENABLED_KEY`):
```
MAGNET_UI_GROUP = "magnet_ui"
MAGNET_BACKEND_GROUP = "magnet_backend"
PERIPHERAL_UI_ENABLED_KEY = "microdrop.peripheral_ui_enabled"
PERIPHERAL_BACKEND_ENABLED_KEY = "microdrop.peripheral_backend_enabled"
```
`START_DEVICE_MONITORING_PERIPHERAL` is imported from `peripheral_controller.consts`
(re-exported there as `START_DEVICE_MONITORING`).

`enable()` / `disable()` changes:
- `enable()`: after `_mount_dock_panes(...)` → call `rebuild_menu_bar_live(window, task, application)`
  → if `group.post_enable_publish_topic`, `publish_message(topic=..., message="")`
  → `app_globals[group.enabled_key] = True`.
- `disable()`: after unregistering services → `rebuild_menu_bar_live(...)`
  → `app_globals[group.enabled_key] = False`.
- The per-group `enabled_key` replaces the single hard-coded `PERIPHERALS_ENABLED_KEY`.

New `apply(task, desired: dict[str, bool])`: for each `group_name, want` in `desired`, if
`want != is_loaded(group_name)`, call `enable`/`disable` accordingly. Backend-before-UI on
enable and UI-before-backend on disable is preserved by ordering the dict iteration
(enable backend first so its services/topics exist; disable UI first). Implementation:
process a fixed ordered list — on enable `[backend, ui]`, on disable `[ui, backend]` —
filtering to those whose desired state differs.

### Component 2 — Live menu-bar rebuild (`tasks_runtime_helpers.py`)

New `rebuild_menu_bar_live(window, task, application)`. Pyface never updates
`task.extra_actions` after a plugin start/stop; the menu bar is built once in
`TaskWindow.add_task`. The helper (grounded in the pyface/envisage source):

1. Recompute additions from the live extension point (reflects only started plugins):
   ```python
   task.extra_actions = [a
       for ext in application.task_extensions
       if (not ext.task_id) or ext.task_id == task.id
       for a in ext.actions]
   ```
2. Rebuild the manager: `builder = window.action_manager_builder_factory(task=task);
   new_mgr = builder.create_menu_bar_manager()`. The builder's `additions` is a `Property`
   sourced live from `task.extra_actions`, so the fresh builder sees the updated list.
3. Swap onto the live window: locate the `TaskState` via `window._get_state(task)`, set
   `state.menu_bar_manager = new_mgr`, and if it is the active state, assign
   `window.menu_bar_manager = new_mgr` — which triggers Pyface's Qt observer
   `_menu_bar_manager_updated → _create_menu_bar → control.setMenuBar(...)` (QMainWindow
   replaces and owns the old bar). Destroy the old manager (`old_mgr.destroy()`).

The static menu items in `task.menu_bar` (File/Edit/Advanced Mode, our "Manage
Peripherals…", View/Help) are preserved — only plugin-contributed `SchemaAddition`s change.

### Component 3 — Status-bar icon fix (`peripherals_ui/dock_pane.py`)

Extract the icon-installation body of `_setup_app_statusbar_with_device_status_icon` into a
param-less, **idempotent** `_install_status_bar_icon()`:
- returns early if `self.status_bar_icon is not None` (already installed) or the window has
  no `status_bar_manager` yet.
The existing `@observe("task:window:status_bar_manager")` observer delegates to it (covers
any non-hot-load path). Add an `on_live_mounted()` hook on the pane that also calls it.
`add_dock_pane_live` (Component 4) calls `pane.on_live_mounted()` after mounting. Removal
is already handled by the pane's `destroy()` (removes the icon + spacer widgets,
disconnects theme callbacks, drops the model observer).

### Component 4 — `add_dock_pane_live` hook (`tasks_runtime_helpers.py`)

After mounting and showing the pane, if it defines `on_live_mounted`, call it (guarded with
try/except + log). This is the generic seam plugins use to finish wiring that depends on
the live window (e.g. the peripheral pane's status-bar icon). No-op for panes without it.

### Component 5 — Manage-Peripherals dialog (`microdrop_application/peripherals_manager_dialog.py`, new)

A `HasTraits` model:
```python
class PeripheralsManagerModel(HasTraits):
    magnet_ui_enabled = Bool()
    magnet_backend_enabled = Bool()
    traits_view = View(
        Item("magnet_ui_enabled",      label="Magnet UI (dock pane, status icon, protocol column)"),
        Item("magnet_backend_enabled", label="Magnet Backend (controller + connection search)"),
        buttons=["OK", "Cancel"], kind="livemodal", title="Manage Peripherals", resizable=True,
    )
```
`ManagePeripheralsAction(TaskAction)` (in `menus.py`, replacing `PeripheralsToggleAction`):
- on `perform`, fetch `manager = task.window.application.get_service(PluginGroupManager)`;
- seed `model = PeripheralsManagerModel(magnet_ui_enabled=manager.is_loaded(MAGNET_UI_GROUP),
  magnet_backend_enabled=manager.is_loaded(MAGNET_BACKEND_GROUP))`;
- `ui = model.edit_traits(kind="livemodal")`; if `ui.result`, call
  `manager.apply(task, {MAGNET_UI_GROUP: model.magnet_ui_enabled,
  MAGNET_BACKEND_GROUP: model.magnet_backend_enabled})`.
- Guard: if the service is missing, log and return.

`edit_traits(kind="livemodal")` is the established dialog pattern in this codebase
(`device_view_dock_pane.py`, `preferences_dialog.py`).

### Component 6 — Menu wiring + launch restore (`menus.py`, `task.py`)

- `menus.py`: remove `PeripheralsToggleAction`; add `ManagePeripheralsAction`; replace the
  single `is_peripherals_enabled()` with `is_peripheral_ui_enabled()` /
  `is_peripheral_backend_enabled()` reading the two new keys.
- `task.py`: Tools menu becomes `SMenu(ManagePeripheralsAction(), id="Tools", name="&Tools")`.
- `task.py` `activated()` `_restore_peripherals_if_enabled()`: restore **each** group
  independently — for each of `(MAGNET_BACKEND_GROUP, is_peripheral_backend_enabled)` and
  `(MAGNET_UI_GROUP, is_peripheral_ui_enabled)`, if its flag is set and the group isn't
  already loaded, `manager.enable(self, group)`. Restore backend before UI.

### Component 7 — Dynamic preferences tabs (`microdrop_application/preferences_dialog.py`)

The base `_PreferencesDialog` rebuilds `_tabs` reactively via
`@on_trait_change("categories, panes") → _update_tabs`. Make our `PreferencesDialog` re-pull
the contributed categories/panes from the **live** extension points each time it opens, so a
plugin-contributed tab shows only while that plugin is loaded:
- override `traits_view(self)` (invoked on each open) to first call a new
  `_refresh_from_application()` which sets
  `self.categories = self.application.get_extensions(PREFERENCES_CATEGORIES)` and
  `self.panes = [factory(dialog=self) for factory in self.application.get_extensions(PREFERENCES_PANES)]`,
  then proceed to build the View as today (reading the now-fresh `_tabs`/`_tabs_filtered`).
- Make the `_category_changed` observer's `advanced_mode_tab` append **idempotent** (skip if
  already present) so re-pulling categories on each open doesn't accumulate duplicates.
- `self.application` is already set (the dialog is constructed with `application=...`).
- `_create_preferences_dialog_service` can keep its initial population (harmless) or defer
  entirely to the open-time refresh; the open-time refresh is the source of truth.

### Component 8 — Startup-list docs (`examples/plugin_consts.py`)

The trio is already excluded from the default startup lists. Split the documentation list
`MAGNET_PERIPHERAL_PLUGINS` into `MAGNET_UI_PLUGINS`
(`PeripheralProtocolControlsPlugin`, `PeripheralUiPlugin`) and `MAGNET_BACKEND_PLUGINS`
(`PeripheralControllerPlugin`) to mirror the two groups. Documentation only — not wired into
the default plugin sets.

## Data flow

**Enable backend (from dialog OK with backend checked):**
`apply → enable("magnet_backend") → add_plugin+start_plugin(PeripheralControllerPlugin)`
(message router re-syncs the controller's topic subscriptions via its
`connect_extension_point_traits`) `→ capture services → (no dock panes) →
rebuild_menu_bar_live (no-op delta) → publish START_DEVICE_MONITORING_PERIPHERAL →
controller's on_start_device_monitoring_request creates+starts the 2 s BackgroundScheduler →
search begins → flag set.`

**Enable UI:** `enable("magnet_ui") → start PeripheralProtocolControlsPlugin (its
PROTOCOL_COLUMNS contribution appears → tree plugin's _column_extension_point_items handler
rebuilds the magnet column in place) → start PeripheralUiPlugin → mount its dock pane via
add_dock_pane_live → pane.on_live_mounted() installs the status-bar icon →
rebuild_menu_bar_live (peripheral "Search Connection" submenu now appears) → flag set.`

**Disable UI:** `remove dock pane (pane.destroy() removes the status icon) → stop+remove
PeripheralUiPlugin then PeripheralProtocolControlsPlugin (column withdraws → tree rebuilds
without magnet, stashing values by uuid) → unregister services → rebuild_menu_bar_live
(submenu disappears) → flag cleared.`

**Open Preferences (any time):** `traits_view → _refresh_from_application → categories/panes
re-pulled from live extensions → _update_tabs rebuilds _tabs → magnet tab present iff the
magnet UI plugin is loaded.`

## Error handling

- Per-plugin add/start/stop/remove and per-pane mount/unmount stay wrapped in
  try/except + log-and-continue (existing behaviour) so a partial failure leaves the group
  state consistent and retryable.
- `rebuild_menu_bar_live`, `on_live_mounted`, and the `post_enable_publish_topic` publish are
  each guarded so a failure there doesn't abort the enable/disable.
- The dialog action reverts nothing on its own (apply-on-OK); if `apply` raises, it's logged
  and the next open reflects true `is_loaded` state.

## Files

**New**
- `microdrop_application/peripherals_manager_dialog.py` — dialog model + view.

**Edit**
- `microdrop_application/plugin_group_manager.py` — two groups; `enabled_key` /
  `post_enable_publish_topic`; menu-bar rebuild + publish in enable/disable; `apply()`.
- `microdrop_utils/tasks_runtime_helpers.py` — `rebuild_menu_bar_live`; `on_live_mounted`
  call in `add_dock_pane_live`.
- `microdrop_application/menus.py` — `ManagePeripheralsAction` (replaces toggle); two
  `is_peripheral_*_enabled` helpers.
- `microdrop_application/task.py` — Tools-menu wiring; per-group launch restore.
- `microdrop_application/consts.py` — two group ids + two enabled keys (remove the single
  pair).
- `peripherals_ui/dock_pane.py` — extract idempotent `_install_status_bar_icon()`; add
  `on_live_mounted()`.
- `microdrop_application/preferences_dialog.py` — open-time `_refresh_from_application()`;
  idempotent `advanced_mode_tab` append.
- `examples/plugin_consts.py` — split the doc list into UI/backend.

## Verification (manual, Redis running, `--device mock`)

1. **Backend only.** Tools → Manage Peripherals → check *Magnet Backend* → OK. Logs show
   the controller started, the router subscribed its listener, and a 2 s search loop
   running. No dock pane, no column.
2. **UI only** (from clean). Check *Magnet UI* → OK. Magnet column appears in the protocol
   tree immediately; peripheral dock pane appears **with** the Z-Stage status-bar icon;
   "Tools → Peripherals → Z-Stage → Search Connection" submenu appears. No search loop.
3. **Both.** Enable both; magnet step actuates and the tree waits for the ack.
4. **Disable UI.** Uncheck *Magnet UI* → OK: dock pane + status icon gone, magnet column
   gone, Tools submenu gone; backend search still running.
5. **Disable backend.** Uncheck → OK: search loop stops; `service_registry._services` no
   longer holds the controller's offers (ids logged on capture/unregister).
6. **Preferences dynamism.** With UI disabled, open Preferences → no magnet tab. Enable UI,
   reopen → magnet tab present. Disable UI, reopen → gone. No duplicate "Advanced Mode" tab
   across repeated opens.
7. **Re-enable idempotency.** Toggle each group off→on twice; services register exactly
   once each cycle, panes/column/menu/icon return, no errors.
8. **Restore on launch.** Enable both, restart: both groups auto-load from their flags, the
   dialog's checkboxes match, the status icon and submenu are present.

## Known limitations (accepted)

- Single-process only (the toggle loads plugins into the GUI process; remote backend
  deferred).
- Rebuilding the menu bar re-instantiates menu managers each enable/disable; toggle/check
  state on static actions is reconstructed from their backing state (app-globals), so no
  visible regression, but it is a full menu-bar swap, not a surgical insert.
- Re-pulling preferences panes on each open rebuilds pane instances; acceptable (they bind
  to `application.preferences`); any in-flight unsaved edit in a *previous* open is already
  gone because each open is a fresh livemodal dialog.
