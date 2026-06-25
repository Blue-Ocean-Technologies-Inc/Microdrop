# Reactive `TASK_EXTENSIONS` mounting (decouple panes/menu from the manager)

**Date:** 2026-06-25
**Status:** Approved (design discussed + approved in conversation)
**Refactors:** `plugin_management/` (`group_manager.py`, `plugin.py`) + a new view-layer controller.

## Problem & goal

`PluginGroupManager.enable/disable` imperatively mounts dock panes (`_mount_dock_panes`) and
rebuilds the menu bar (`rebuild_menu_bar_live`). That couples the orchestrator to Pyface view
concerns and means **only** plugins loaded through our group manager get their panes/menus
mounted at runtime.

Make it **reactive instead**, mirroring how `message_router` reacts to `ACTOR_TOPIC_ROUTES`
and the protocol tree reacts to `PROTOCOL_COLUMNS`: a component listens to the
**`TASK_EXTENSIONS`** extension point and, when contributions are added/removed at runtime,
mounts/unmounts the contributed dock panes and rebuilds the menu bar — **debounced** so a
multi-plugin group load triggers one reconcile. Any runtime-loaded plugin (not just ours) then
gets its panes/menus automatically, and the manager shrinks to plugin + service lifecycle.

## What stays hand-rolled (unchanged)

Pyface still has **no public API** to add/remove a dock pane or rebuild a menu on a live
window, so `microdrop_utils/tasks_runtime_helpers.py` (`add_dock_pane_live`,
`remove_dock_pane_live`, `rebuild_menu_bar_live`) is still required. We only change *what
triggers* it — from imperative manager calls to a reactive, debounced extension-point listener.

## Key framework facts (verified in installed envisage)

- `application.add_extension_point_listener(listener, extension_point_id)`
  (`envisage/application.py:196` → `extension_registry.py:94`) is the public consumer hook;
  the registry calls `listener(extension_registry, event)` (`extension_registry.py:178`) with
  an `ExtensionPointChangedEvent` carrying `.extension_point_id`, `.added`, `.removed`,
  `.index`. This is exactly the machinery `connect_extension_point_traits()` uses — applied
  directly because we are a *consumer* of `TASK_EXTENSIONS` (the `TasksApplication` owns/declares
  it at `tasks_application.py:88`; declaring a duplicate `ExtensionPoint` trait would conflict).
- Listeners are stored via `_saferef` (`extension_registry.py:98`), which keeps a bound-method
  listener alive as long as its **instance** lives. So the listener must be a method on a
  long-lived object — `PluginManagementPlugin` (held by envisage for the app's life).
- Contributions register at **`add_plugin`** (`plugin_extension_registry.py:57`
  `_on_plugin_added`), i.e. possibly *before* `start_plugin`. So pane creation must be
  **deferred** past the manager's synchronous add+start loop → the debounce timer does this for
  free (it fires on the next GUI-event-loop turn, after `enable()` returns).
- `TasksApplication` does **nothing** with `task_extensions` at runtime: `create_task` reads
  them once (`:204`) and `create_with_extensions` copies them into the task one time
  (`task_factory.py:41‑43`). No observer re-applies them — hence this work.

## Architecture

```
PluginManagementPlugin.start():
    application.add_extension_point_listener(self._on_task_extensions_changed, TASK_EXTENSIONS)

_on_task_extensions_changed(registry, event):       # listener(reg, ExtensionPointChangedEvent)
    self._live_task_exts.on_changed(event.added, event.removed)

LiveTaskExtensionsController (Qt view-layer):
    on_changed(added, removed):  accumulate into pending; (re)start the debounce QTimer
    _reconcile() [debounce fired, on GUI thread, after the enable loop]:
        window = application.active_window; if None: clear pending, return
        task = window.active_task
        for ext in pending_removed (matching task): remove its dock panes (by tracked pane id)
        for ext in pending_added   (matching task): mount its dock panes (add_dock_pane_live)
        rebuild_menu_bar_live(window, task, application)        # ONCE
        clear pending
```

### Component 1 — `LiveTaskExtensionsController` (`plugin_management/live_task_extensions.py`, new)

A view-layer controller (Qt allowed here, like `tasks_runtime_helpers`). Plain object holding a
`QTimer` (single-shot debounce) + pending/added-removed lists + a `factory → mounted pane id`
map.

- `__init__(self, application)` — stores the app; creates a single-shot `QTimer`
  (`DEBOUNCE_MS = 50`) connected to `_reconcile`.
- `on_changed(self, added, removed)` — extend `self._pending_added`/`self._pending_removed`
  with the event's TaskExtensions; `self._timer.start(DEBOUNCE_MS)` (restart → coalesces a
  burst into one reconcile).
- `_reconcile(self)`:
  - `window = self._application.active_window`; if `None`, clear pending and return (e.g. the
    listener fired before the GUI exists — nothing to mount onto).
  - `task = window.active_task`; if `None`, clear pending and return.
  - **Removed first:** for each pending removed `ext` whose `task_id` is empty or `== task.id`,
    for each `factory` in `ext.dock_pane_factories`, look up the mounted pane id in
    `self._pane_id_by_factory` and `remove_dock_pane_live(window, pane_id)` (guarded; drop the
    map entry).
  - **Added:** for each pending added `ext` (matching task), for each `factory` in
    `ext.dock_pane_factories`, `pane = add_dock_pane_live(window, task, factory)` (guarded); if
    `pane is not None`, record `self._pane_id_by_factory[factory] = pane.id`.
  - `rebuild_menu_bar_live(window, task, self._application)` **once** (covers actions-only
    extensions too).
  - Clear both pending lists.
- A `dispose()` to stop the timer (called from the plugin's `stop()`), for hygiene.

Pane ids are read from the **mounted instance** (`pane.id`) and cached by factory class, because
a DockPane subclass's `id` is a trait whose value isn't reliably readable off the class object —
so we record it when we mount and reuse it to unmount.

### Component 2 — `PluginManagementPlugin` (`plugin.py`)

- Add `_live_task_exts = Instance(...)` (the controller) and build it lazily.
- In `start()`: create the controller (`LiveTaskExtensionsController(self.application)`) and
  `self.application.add_extension_point_listener(self._on_task_extensions_changed,
  TASK_EXTENSIONS)`.
- `_on_task_extensions_changed(self, registry, event)` → `self._live_task_exts.on_changed(
  list(event.added), list(event.removed))`.
- In `stop()` (defensive — the plugin isn't normally stopped): remove the listener and
  `dispose()` the controller.
- Import `TASK_EXTENSIONS` from `envisage.api`.

### Component 3 — `PluginGroupManager` (`group_manager.py`) — remove the view work

- `enable()`: delete the `self._mount_dock_panes(task, group)` call and the
  `rebuild_menu_bar_live(...)` block. Keep: resolve specs → add/start plugins → capture service
  ids → `post_enable_publish_topic` → set flag.
- `disable()`: delete the dock-pane removal loop (`for pane_id in reversed(group.dock_pane_ids)
  …`) and the `rebuild_menu_bar_live(...)` block. Keep: stop/remove plugins (reverse) →
  unregister captured services → clear flag.
- Delete the `_mount_dock_panes` method and the `dock_pane_ids` field on `PluginGroup` (now
  unused). Drop the `add_dock_pane_live`/`remove_dock_pane_live`/`rebuild_menu_bar_live` imports
  from this module (they move to the controller).
- The reactive controller now owns pane/menu lifecycle; the manager owns plugin + service
  lifecycle only.

### Ordering / timing notes

- **Within a group enable**, panes mount when the debounce fires — after every plugin in the
  group has been added+started (the manager's loop is synchronous; the timer fires on the next
  event-loop turn). This fixes the "mount before start" risk and coalesces.
- **Across groups**, the manager's `apply()` still enables backend-before-UI and disables
  UI-before-backend; the reactive pane/menu changes simply follow each group's plugin
  add/remove.
- **Startup panes** are never in a runtime delta (the listener registers in `start()`, after
  startup contributions are already in the registry), so the controller only manages
  runtime-added panes; Pyface still owns the startup ones. Clean separation via deltas.

## Error handling

- Each `add_dock_pane_live`/`remove_dock_pane_live`/`rebuild_menu_bar_live` call is guarded
  (try/except + log) so one bad pane doesn't abort the reconcile.
- If `active_window`/`active_task` is absent at reconcile, pending is cleared and skipped (the
  contribution is still in the registry; if a window appears later and the same extension is
  re-contributed it would re-fire — acceptable; in practice the GUI exists before any runtime
  enable).

## Files

**New:** `plugin_management/live_task_extensions.py` — `LiveTaskExtensionsController`, `DEBOUNCE_MS`.
**Edit:** `plugin_management/plugin.py` (listener + controller), `plugin_management/group_manager.py`
(remove pane/menu work + `dock_pane_ids` + `_mount_dock_panes`).

## Verification (no pytest)

- `py_compile` the changed files.
- `pixi` smokes: the manager still discovers groups + install/uninstall round-trip works
  (manager no longer references the view helpers); `LiveTaskExtensionsController` constructs and
  `on_changed` schedules a reconcile (use `QT_QPA_PLATFORM=offscreen`; with no `active_window`,
  `_reconcile` no-ops cleanly).
- Manual GUI (the real test): enable the magnet UI group → its dock pane + status icon + the
  "Search Connection" Tools submenu appear **once** (one menu rebuild, ~50 ms after the dialog
  closes); disable → they disappear; multi-group enable triggers a single coalesced reconcile;
  launch-restore still mounts an enabled group's pane.

## Known limitations (accepted)

- The hand-rolled `tasks_runtime_helpers` remain (Pyface has no API) — only the trigger changes.
- A ~`DEBOUNCE_MS` visual delay before panes/menus appear after enable — intentional (the
  coalescing point).
- The controller assumes the **single active window** (MicroDrop is single-window); multi-window
  task extensions aren't reconciled per-window (out of scope).
