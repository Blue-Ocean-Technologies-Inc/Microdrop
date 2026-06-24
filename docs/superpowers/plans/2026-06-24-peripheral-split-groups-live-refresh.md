# Peripheral Split Groups + Live UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single Tools→Peripherals toggle with two independent toggles (Magnet UI / Magnet Backend) in a Tools-menu dialog, start the magnet search when the backend is enabled, and make the status-bar icon, Tools submenu, and Preferences tab appear/disappear live as their plugin loads/unloads.

**Architecture:** Two named `PluginGroup`s driven by the existing `PluginGroupManager` and a livemodal Tools-menu dialog. Three UI surfaces that snapshot Envisage extension points at startup (status icon, menu bar, preferences tabs) are refreshed against the live (started-plugin) set on each load/unload or open.

**Tech Stack:** Envisage 7.0.4, Traits 7.1.0, TraitsUI 8.0.0, Pyface 8.0.0 (Tasks), PySide6, Python 3.13, Dramatiq+Redis.

**Spec:** `docs/superpowers/specs/2026-06-24-peripheral-split-groups-live-refresh-design.md`

## Global Constraints

- **Working directory for all commands:** `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src` (the submodule). Commits land in the submodule on branch `feature/peripheral-hot-load`.
- **Testing convention (this project):** Do NOT add or run pytest. Each task's gate is (a) `python -m py_compile <files>` for syntax, then (b) a `pixi run` import/introspection smoke from the parent dir, then (c) manual GUI verification at the end (Task 9). Run Python only through pixi: `cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '...'"`. Redis must be running for any import that pulls dramatiq (`pixi run python examples/start_redis_server.py`).
- **Conventions:** HasTraits + `traits_init`/`_x_default`; `@observe` (except synthetic `_items` events → `on_trait_change`); constants UPPER_SNAKE in package `consts.py`; logger via `from logger.logger_service import get_logger`; no Qt in model/service layers (only views + `tasks_runtime_helpers`); dialogs via TraitsUI `edit_traits(kind="livemodal")` or `microdrop_application/dialogs/pyface_wrapper`; f-strings only; reuse existing names, never alias.
- **Commit trailer:** end every commit message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **No cross-plugin imports** beyond what already exists; the orchestrator importing plugin classes in `_groups_default` is sanctioned (mirrors `examples/plugin_consts.py`).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `microdrop_utils/tasks_runtime_helpers.py` | Runtime Qt helpers: live dock-pane add/remove (exists), **new** live menu-bar rebuild, **new** `on_live_mounted` hook call | Modify |
| `microdrop_application/consts.py` | Two group ids + two enabled-flag keys (replace the single pair) | Modify |
| `microdrop_application/plugin_group_manager.py` | Two groups; per-group flag + post-enable publish; menu rebuild in enable/disable; `apply()` | Modify |
| `peripherals_ui/dock_pane.py` | Idempotent status-icon install + `on_live_mounted` hook | Modify |
| `microdrop_application/peripherals_manager_dialog.py` | Two-checkbox dialog model + view | Create |
| `microdrop_application/menus.py` | `ManagePeripheralsAction` (replaces toggle) + two `is_peripheral_*_enabled` helpers | Modify |
| `microdrop_application/task.py` | Tools-menu wiring + per-group launch restore | Modify |
| `microdrop_application/preferences_dialog.py` | Open-time refresh of categories/panes from live extensions; idempotent advanced tab | Modify |
| `examples/plugin_consts.py` | Split the doc list into UI/backend (documentation only) | Modify |

---

## Task 1: Live menu-bar rebuild + dock-pane mount hook

**Files:**
- Modify: `microdrop_utils/tasks_runtime_helpers.py`

**Interfaces:**
- Produces: `rebuild_menu_bar_live(window, task, application) -> None`; `add_dock_pane_live` now invokes `pane.on_live_mounted()` if present.

- [ ] **Step 1: Add the menu-bar hook to `add_dock_pane_live`**

In `microdrop_utils/tasks_runtime_helpers.py`, locate the tail of `add_dock_pane_live`:

```python
    state.dock_panes = state.dock_panes + [pane]
    window.dock_panes = state.dock_panes
    logger.info(f"add_dock_pane_live: mounted dock pane '{pane.id}'")
    return pane
```

Replace it with:

```python
    state.dock_panes = state.dock_panes + [pane]
    window.dock_panes = state.dock_panes

    # Let the pane finish any wiring that needs the live window (e.g. the
    # peripheral pane installs its status-bar icon here — its
    # task:window:status_bar_manager observer never fires on a hot-mount
    # because the status bar already exists).
    on_live_mounted = getattr(pane, "on_live_mounted", None)
    if callable(on_live_mounted):
        try:
            on_live_mounted()
        except Exception:
            logger.exception(
                f"add_dock_pane_live: on_live_mounted hook failed for '{pane.id}'"
            )

    logger.info(f"add_dock_pane_live: mounted dock pane '{pane.id}'")
    return pane
```

- [ ] **Step 2: Add `rebuild_menu_bar_live`**

Append at the end of `microdrop_utils/tasks_runtime_helpers.py`:

```python
def rebuild_menu_bar_live(window, task, application):
    """Rebuild a live ``TaskWindow``'s menu bar from the CURRENT started
    plugins' TaskExtension actions.

    Pyface gathers SchemaAdditions into ``task.extra_actions`` once at window
    creation (``TaskWindow.add_task``) and never updates them when a plugin
    starts/stops, so a hot-loaded plugin's menu contributions never appear (and
    an unloaded plugin's never disappear). We recompute ``extra_actions`` from
    the live ``application.task_extensions`` extension point (which reflects
    only started plugins), rebuild the menu-bar manager, and assign it so
    Pyface's Qt observer (``_menu_bar_manager_updated`` -> ``setMenuBar``) swaps
    it onto the QMainWindow. Static items in ``task.menu_bar`` are preserved;
    only plugin-contributed additions change.
    """
    task.extra_actions = [
        addition
        for extension in application.task_extensions
        if (not extension.task_id) or extension.task_id == task.id
        for addition in extension.actions
    ]

    builder = window.action_manager_builder_factory(task=task)
    new_manager = builder.create_menu_bar_manager()

    state = window._get_state(task)
    if state is None:
        logger.warning("rebuild_menu_bar_live: no task state; cannot rebuild menu bar")
        return

    old_manager = state.menu_bar_manager
    state.menu_bar_manager = new_manager

    # If this task is the active one, push to the window trait — that triggers
    # Pyface's _menu_bar_manager_updated, which calls setMenuBar on the live
    # control (QMainWindow replaces and owns the old menu bar).
    if window._active_state is state:
        window.menu_bar_manager = new_manager

    if old_manager is not None and old_manager is not new_manager:
        try:
            old_manager.destroy()
        except Exception:
            logger.exception(
                "rebuild_menu_bar_live: failed to destroy old menu bar manager"
            )
    logger.info("rebuild_menu_bar_live: menu bar rebuilt")
```

- [ ] **Step 3: Compile**

Run: `python -m py_compile microdrop_utils/tasks_runtime_helpers.py`
Expected: no output (success).

- [ ] **Step 4: Import smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c 'from microdrop_utils.tasks_runtime_helpers import add_dock_pane_live, remove_dock_pane_live, rebuild_menu_bar_live; print(\"OK\", callable(rebuild_menu_bar_live))'"
```
Expected: a line ending `OK True` (ignore Qt/deprecation warnings).

- [ ] **Step 5: Commit**

```bash
git add microdrop_utils/tasks_runtime_helpers.py
git commit -m "Add live menu-bar rebuild + on_live_mounted hook to tasks helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Two group ids + two enabled-flag constants

**Files:**
- Modify: `microdrop_application/consts.py`

**Interfaces:**
- Produces: `MAGNET_UI_GROUP`, `MAGNET_BACKEND_GROUP`, `PERIPHERAL_UI_ENABLED_KEY`, `PERIPHERAL_BACKEND_ENABLED_KEY`. Removes `MAGNET_PERIPHERALS_GROUP`, `PERIPHERALS_ENABLED_KEY`.

- [ ] **Step 1: Replace the constants**

In `microdrop_application/consts.py`, replace this block:

```python
# Runtime plugin-group hot load/unload (the optional magnet-peripheral group).
# PERIPHERALS_ENABLED_KEY is an app-globals flag the menu toggle reads to show
# its checkmark and that activated() reads to auto-restore the group on launch.
MAGNET_PERIPHERALS_GROUP = "magnet_peripherals"
PERIPHERALS_ENABLED_KEY = "microdrop.peripherals_enabled"
```

with:

```python
# Runtime plugin-group hot load/unload. The optional magnet peripheral is split
# into two independently-toggled groups (see the Tools -> Manage Peripherals
# dialog / PluginGroupManager): a UI group (dock pane, status icon, protocol
# column) and a backend group (controller + connection search). The
# *_ENABLED_KEY app-globals flags persist each group's state so the dialog
# checkboxes and the launch-restore in MicrodropTask.activated() stay in sync
# across runs.
MAGNET_UI_GROUP = "magnet_ui"
MAGNET_BACKEND_GROUP = "magnet_backend"
PERIPHERAL_UI_ENABLED_KEY = "microdrop.peripheral_ui_enabled"
PERIPHERAL_BACKEND_ENABLED_KEY = "microdrop.peripheral_backend_enabled"
```

- [ ] **Step 2: Compile**

Run: `python -m py_compile microdrop_application/consts.py`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add microdrop_application/consts.py
git commit -m "Split peripheral group consts into UI + backend group ids/keys

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Two groups in `PluginGroupManager` + `apply()`

**Files:**
- Modify: `microdrop_application/plugin_group_manager.py`

**Interfaces:**
- Consumes: Task 1 `rebuild_menu_bar_live`; Task 2 consts; existing `add_dock_pane_live`/`remove_dock_pane_live`.
- Produces: `PluginGroup` with `enabled_key: Str`, `post_enable_publish_topic: Str`; `PluginGroupManager.groups` keyed `"magnet_ui"`/`"magnet_backend"`; `PluginGroupManager.apply(task, desired: dict[str, bool]) -> None`; `enable`/`disable` set the per-group flag, rebuild the menu bar, and (enable) publish `post_enable_publish_topic`.

- [ ] **Step 1: Update imports**

In `microdrop_application/plugin_group_manager.py`, replace the import block:

```python
from microdrop_application.consts import (
    MAGNET_PERIPHERALS_GROUP, PERIPHERALS_ENABLED_KEY,
)
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.tasks_runtime_helpers import (
    add_dock_pane_live, remove_dock_pane_live,
)
from logger.logger_service import get_logger
```

with:

```python
from microdrop_application.consts import (
    MAGNET_BACKEND_GROUP, MAGNET_UI_GROUP,
    PERIPHERAL_BACKEND_ENABLED_KEY, PERIPHERAL_UI_ENABLED_KEY,
)
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.tasks_runtime_helpers import (
    add_dock_pane_live, rebuild_menu_bar_live, remove_dock_pane_live,
)
from peripheral_controller.consts import (
    START_DEVICE_MONITORING as START_DEVICE_MONITORING_PERIPHERAL,
)
from logger.logger_service import get_logger
```

- [ ] **Step 2: Add the two new `PluginGroup` fields**

In the `PluginGroup` class, after the `loaded = Bool(False)` line, add:

```python
    #: App-globals flag persisting this group's enabled state across runs.
    enabled_key = Str()
    #: Optional topic published (empty message) right after a successful
    #: enable — e.g. the backend group kicks off the magnet connection search.
    post_enable_publish_topic = Str()
```

- [ ] **Step 3: Replace `_groups_default` with two groups**

Replace the whole `_groups_default` method:

```python
    def _groups_default(self):
        # Importing plugin classes from a loader module is sanctioned here —
        # examples/plugin_consts.py already does exactly this.
        from peripheral_controller.plugin import PeripheralControllerPlugin
        from peripheral_protocol_controls.plugin import (
            PeripheralProtocolControlsPlugin,
        )
        from peripherals_ui.plugin import PeripheralUiPlugin

        ui = PluginGroup(
            name=MAGNET_UI_GROUP,
            plugin_factories=[
                PeripheralProtocolControlsPlugin,  # magnet protocol column
                PeripheralUiPlugin,                # dock pane + status icon + tools submenu
            ],
            enabled_key=PERIPHERAL_UI_ENABLED_KEY,
        )
        backend = PluginGroup(
            name=MAGNET_BACKEND_GROUP,
            plugin_factories=[PeripheralControllerPlugin],
            enabled_key=PERIPHERAL_BACKEND_ENABLED_KEY,
            post_enable_publish_topic=START_DEVICE_MONITORING_PERIPHERAL,
        )
        return {ui.name: ui, backend.name: backend}
```

- [ ] **Step 4: Update the tail of `enable()`**

In `enable()`, replace this tail:

```python
        group.service_ids = sorted(set(registry._services.keys()) - before)
        logger.info(f"enable: captured service ids {group.service_ids}")

        self._mount_dock_panes(task, group)

        group.loaded = True
        app_globals[PERIPHERALS_ENABLED_KEY] = True
        logger.info(f"enable: group '{group_name}' loaded")
```

with:

```python
        group.service_ids = sorted(set(registry._services.keys()) - before)
        logger.info(f"enable: captured service ids {group.service_ids}")

        self._mount_dock_panes(task, group)

        # The plugin's menu contributions (e.g. the peripheral Search Connection
        # submenu) are gathered once at window creation; rebuild so they appear.
        try:
            rebuild_menu_bar_live(task.window, task, application)
        except Exception:
            logger.exception("enable: menu bar rebuild failed")

        # Optional post-enable kick — the backend group starts the magnet search.
        if group.post_enable_publish_topic:
            try:
                publish_message(topic=group.post_enable_publish_topic, message="")
                logger.info(f"enable: published {group.post_enable_publish_topic}")
            except Exception:
                logger.exception(
                    f"enable: failed to publish {group.post_enable_publish_topic}"
                )

        group.loaded = True
        if group.enabled_key:
            app_globals[group.enabled_key] = True
        logger.info(f"enable: group '{group_name}' loaded")
```

- [ ] **Step 5: Update the tail of `disable()`**

In `disable()`, replace this tail:

```python
        group.service_ids = []

        group.loaded = False
        app_globals[PERIPHERALS_ENABLED_KEY] = False
        logger.info(f"disable: group '{group_name}' unloaded")
```

with:

```python
        group.service_ids = []

        try:
            rebuild_menu_bar_live(window, task, application)
        except Exception:
            logger.exception("disable: menu bar rebuild failed")

        group.loaded = False
        if group.enabled_key:
            app_globals[group.enabled_key] = False
        logger.info(f"disable: group '{group_name}' unloaded")
```

- [ ] **Step 6: Add `apply()`**

Add this method to `PluginGroupManager`, right after `is_loaded`:

```python
    def apply(self, task, desired):
        """Reconcile group load state to ``desired`` ({group_name: bool}).

        Enables run backend-before-UI (services/topics exist before the column/
        UI consume them); disables run UI-before-backend (UI dies before the
        backend it observes). Only groups whose desired state differs from
        their current state are touched."""
        for group_name in (MAGNET_BACKEND_GROUP, MAGNET_UI_GROUP):
            if desired.get(group_name) and not self.is_loaded(group_name):
                self.enable(task, group_name)
        for group_name in (MAGNET_UI_GROUP, MAGNET_BACKEND_GROUP):
            if (group_name in desired
                    and not desired[group_name]
                    and self.is_loaded(group_name)):
                self.disable(task, group_name)
```

- [ ] **Step 7: Compile**

Run: `python -m py_compile microdrop_application/plugin_group_manager.py`
Expected: no output.

- [ ] **Step 8: Import + structure smoke (Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
from microdrop_application.plugin_group_manager import PluginGroupManager, PluginGroup
m = PluginGroupManager()
g = m.groups
ui, be = g[\"magnet_ui\"], g[\"magnet_backend\"]
print(\"ui plugins:\", [f.__name__ for f in ui.plugin_factories])
print(\"backend plugins:\", [f.__name__ for f in be.plugin_factories])
print(\"ui key:\", ui.enabled_key, \"| backend key:\", be.enabled_key)
print(\"backend post-publish set:\", bool(be.post_enable_publish_topic))
print(\"apply present:\", hasattr(m, \"apply\"))
'"
```
Expected: ui plugins `['PeripheralProtocolControlsPlugin', 'PeripheralUiPlugin']`, backend `['PeripheralControllerPlugin']`, both keys non-empty, `backend post-publish set: True`, `apply present: True`.

- [ ] **Step 9: Commit**

```bash
git add microdrop_application/plugin_group_manager.py
git commit -m "Split magnet group into UI + backend; add apply() + post-enable kick

Backend enable now publishes START_DEVICE_MONITORING_PERIPHERAL to start the
magnet search; both enable/disable rebuild the menu bar so plugin-contributed
submenus appear/disappear live. apply() reconciles desired vs loaded state.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Idempotent status-bar icon install + `on_live_mounted`

**Files:**
- Modify: `peripherals_ui/dock_pane.py`

**Interfaces:**
- Consumes: Task 1 (`add_dock_pane_live` calls `on_live_mounted`).
- Produces: `PeripheralStatusDockPane.on_live_mounted()` and idempotent `_install_status_bar_icon()`; the `task:window:status_bar_manager` observer delegates to the latter.

- [ ] **Step 1: Replace the status-bar observer method with delegating + idempotent versions**

In `peripherals_ui/dock_pane.py`, replace the entire `_setup_app_statusbar_with_device_status_icon` method (the one decorated `@observe("task:window:status_bar_manager")`, ending just before `def destroy(self):`) with:

```python
    @observe("task:window:status_bar_manager")
    def _setup_app_statusbar_with_device_status_icon(self, event):
        # Normal-startup path: the pane exists before the status bar, so this
        # observer fires when the bar is set. Delegate to the idempotent
        # installer (the hot-mount path calls the same installer via
        # on_live_mounted, where this observer never fires).
        self._install_status_bar_icon()

    def on_live_mounted(self):
        """Hook called by add_dock_pane_live after the pane is mounted on a live
        window. On a hot-mount the status bar already exists, so the
        task:window:status_bar_manager observer never fires — install the icon
        explicitly here."""
        self._install_status_bar_icon()

    def _install_status_bar_icon(self):
        """Add the Z-Stage status icon (+ spacer) to the window status bar and
        wire its connection-state colour + themed tooltip. Idempotent: no-op if
        the icon is already installed or the window has no status bar yet."""
        if self.status_bar_icon is not None:
            return
        window = self.task.window if self.task is not None else None
        status_bar_manager = (
            getattr(window, "status_bar_manager", None)
            if window is not None else None
        )
        if status_bar_manager is None:
            return

        _model = self.dramatiq_controller.ui.model

        device_status = QLabel(ICON_STAIRS)

        _font = QFont(ICON_FONT_FAMILY)
        _font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        device_status.setFont(_font)
        device_status.setStyleSheet(f"color: {disconnected_color};")

        spacer = horizontal_spacer_widget(10)
        status_bar_manager.status_bar.addPermanentWidget(spacer)
        status_bar_manager.status_bar.addPermanentWidget(device_status)
        self._status_bar_spacer = spacer

        def set_status_color(event):
            color = connected_color if event.new else disconnected_color
            device_status.setStyleSheet(f"color: {color}")

        _model.observe(set_status_color, "status")
        # Keep refs so destroy() can drop this model observer on hot-unload.
        self._status_model = _model
        self._set_status_color = set_status_color

        self.status_bar_icon = device_status

        ### update tooltip based on dark / light mode
        def _apply_theme_style():
            self.status_bar_icon.setToolTip(get_status_icon_tooltip_themed())

        _apply_theme_style()  # initial setting
        QApplication.styleHints().colorSchemeChanged.connect(_apply_theme_style)
        self._theme_callbacks.append(_apply_theme_style)
```

- [ ] **Step 2: Compile**

Run: `python -m py_compile peripherals_ui/dock_pane.py`
Expected: no output.

- [ ] **Step 3: Import + introspection smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import peripherals_ui.dock_pane as d
P = d.PeripheralStatusDockPane
print(\"on_live_mounted:\", hasattr(P, \"on_live_mounted\"))
print(\"_install_status_bar_icon:\", hasattr(P, \"_install_status_bar_icon\"))
'"
```
Expected: both `True`.

- [ ] **Step 4: Commit**

```bash
git add peripherals_ui/dock_pane.py
git commit -m "Install peripheral status icon idempotently via on_live_mounted hook

The task:window:status_bar_manager observer never fires on a hot-mount (the
status bar already exists), so the icon was never added. Extract an idempotent
installer the observer and the new on_live_mounted hook both call.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Manage-Peripherals dialog model

**Files:**
- Create: `microdrop_application/peripherals_manager_dialog.py`

**Interfaces:**
- Produces: `PeripheralsManagerModel` (HasTraits) with `magnet_ui_enabled: Bool`, `magnet_backend_enabled: Bool`, and a livemodal `traits_view`.

- [ ] **Step 1: Create the dialog model**

Create `microdrop_application/peripherals_manager_dialog.py`:

```python
"""Tools-menu dialog model for hot loading/unloading the magnet-peripheral
plugin groups.

Two independent checkboxes — Magnet UI and Magnet Backend — applied on OK by
the caller (ManagePeripheralsAction) via PluginGroupManager.apply(). The model
is intentionally Qt-free TraitsUI; the action owns the orchestration.
"""

from traits.api import Bool, HasTraits
from traitsui.api import Item, View


class PeripheralsManagerModel(HasTraits):
    """Checkbox state for the Manage Peripherals dialog."""

    magnet_ui_enabled = Bool()
    magnet_backend_enabled = Bool()

    traits_view = View(
        Item(
            "magnet_ui_enabled",
            label="Magnet UI (dock pane, status icon, protocol column)",
        ),
        Item(
            "magnet_backend_enabled",
            label="Magnet Backend (controller + connection search)",
        ),
        buttons=["OK", "Cancel"],
        kind="livemodal",
        title="Manage Peripherals",
        resizable=True,
    )
```

- [ ] **Step 2: Compile**

Run: `python -m py_compile microdrop_application/peripherals_manager_dialog.py`
Expected: no output.

- [ ] **Step 3: Import smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
from microdrop_application.peripherals_manager_dialog import PeripheralsManagerModel
m = PeripheralsManagerModel(magnet_ui_enabled=True)
print(\"ui:\", m.magnet_ui_enabled, \"| backend:\", m.magnet_backend_enabled)
'"
```
Expected: `ui: True | backend: False`.

- [ ] **Step 4: Commit**

```bash
git add microdrop_application/peripherals_manager_dialog.py
git commit -m "Add Manage Peripherals dialog model (two magnet-group checkboxes)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Tools-menu action + helpers + per-group launch restore

**Files:**
- Modify: `microdrop_application/menus.py`
- Modify: `microdrop_application/task.py`

**Interfaces:**
- Consumes: Task 2 consts; Task 3 `PluginGroupManager.apply`/`is_loaded`/`enable`; Task 5 `PeripheralsManagerModel`.
- Produces: `ManagePeripheralsAction(TaskAction)`; `is_peripheral_ui_enabled()`, `is_peripheral_backend_enabled()`. Removes `PeripheralsToggleAction`, `is_peripherals_enabled`.

- [ ] **Step 1: Update `menus.py` imports**

In `microdrop_application/menus.py`, replace:

```python
from microdrop_application.consts import (
    ADVANCED_MODE_CHANGE, MAGNET_PERIPHERALS_GROUP, PERIPHERALS_ENABLED_KEY,
)
```

with:

```python
from microdrop_application.consts import (
    ADVANCED_MODE_CHANGE, MAGNET_BACKEND_GROUP, MAGNET_UI_GROUP,
    PERIPHERAL_BACKEND_ENABLED_KEY, PERIPHERAL_UI_ENABLED_KEY,
)
```

- [ ] **Step 2: Replace the `is_peripherals_enabled` helper**

In `microdrop_application/menus.py`, replace:

```python
def is_peripherals_enabled():
    return app_globals.get(PERIPHERALS_ENABLED_KEY, False)
```

with:

```python
def is_peripheral_ui_enabled():
    return app_globals.get(PERIPHERAL_UI_ENABLED_KEY, False)


def is_peripheral_backend_enabled():
    return app_globals.get(PERIPHERAL_BACKEND_ENABLED_KEY, False)
```

- [ ] **Step 3: Replace `PeripheralsToggleAction` with `ManagePeripheralsAction`**

In `microdrop_application/menus.py`, replace the entire `PeripheralsToggleAction` class with:

```python
class ManagePeripheralsAction(TaskAction):
    """Tools-menu action opening the Manage Peripherals dialog, which hot
    loads/unloads the magnet UI and backend plugin groups independently.
    TaskAction (not plain Action) so ``self.task`` is populated — the
    orchestrator needs the live task/window/application. Lives in the
    always-loaded task so the entry is present even when both groups are
    unloaded."""

    id = "manage_peripherals_action"
    name = "&Manage Peripherals…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Manage Peripherals: no task available")
            return
        # Local imports avoid pulling the orchestrator (and its Qt helper) and
        # the dialog in at menu-import time, and sidestep import cycles.
        from microdrop_application.plugin_group_manager import PluginGroupManager
        from microdrop_application.peripherals_manager_dialog import (
            PeripheralsManagerModel,
        )

        manager = task.window.application.get_service(PluginGroupManager)
        if manager is None:
            logger.error("Manage Peripherals: PluginGroupManager service not found")
            return

        model = PeripheralsManagerModel(
            magnet_ui_enabled=manager.is_loaded(MAGNET_UI_GROUP),
            magnet_backend_enabled=manager.is_loaded(MAGNET_BACKEND_GROUP),
        )
        ui = model.edit_traits(kind="livemodal")
        if not ui.result:     # Cancel / closed -> no change
            return
        try:
            manager.apply(task, {
                MAGNET_UI_GROUP: model.magnet_ui_enabled,
                MAGNET_BACKEND_GROUP: model.magnet_backend_enabled,
            })
        except Exception:
            logger.exception("Manage Peripherals: applying group changes failed")
```

- [ ] **Step 4: Update `task.py` imports**

In `microdrop_application/task.py`, replace:

```python
from .consts import PKG, MAGNET_PERIPHERALS_GROUP
```

with:

```python
from .consts import PKG, MAGNET_UI_GROUP, MAGNET_BACKEND_GROUP
```

and replace:

```python
from .menus import AdvancedModeAction, PeripheralsToggleAction, is_peripherals_enabled
```

with:

```python
from .menus import (
    AdvancedModeAction, ManagePeripheralsAction,
    is_peripheral_ui_enabled, is_peripheral_backend_enabled,
)
```

- [ ] **Step 5: Wire the Tools menu**

In `microdrop_application/task.py`, in the `menu_bar = SMenuBar(...)` block, replace:

```python
        SMenu(PeripheralsToggleAction(), id="Tools", name="&Tools"),
```

with:

```python
        SMenu(ManagePeripheralsAction(), id="Tools", name="&Tools"),
```

- [ ] **Step 6: Replace the launch-restore method**

In `microdrop_application/task.py`, replace the entire `_restore_peripherals_if_enabled` method with:

```python
    def _restore_peripherals_if_enabled(self):
        """Re-load each magnet-peripheral group on launch if its persisted
        app-global flag is set, so the dialog checkboxes (read from the same
        flags) match what's actually loaded. Backend before UI (services/topics
        exist before the column/UI consume them)."""
        restore = [
            (MAGNET_BACKEND_GROUP, is_peripheral_backend_enabled()),
            (MAGNET_UI_GROUP, is_peripheral_ui_enabled()),
        ]
        if not any(enabled for _, enabled in restore):
            return
        from .plugin_group_manager import PluginGroupManager
        manager = self.window.application.get_service(PluginGroupManager)
        if manager is None:
            logger.warning("peripherals restore: PluginGroupManager service not found")
            return
        for group_name, enabled in restore:
            if enabled and not manager.is_loaded(group_name):
                logger.info(
                    f"Restoring peripheral group '{group_name}' from persisted flag"
                )
                manager.enable(self, group_name)
```

(The call site in `activated()` — `self._restore_peripherals_if_enabled()` — is unchanged.)

- [ ] **Step 7: Compile**

Run: `python -m py_compile microdrop_application/menus.py microdrop_application/task.py`
Expected: no output.

- [ ] **Step 8: Import + introspection smoke (Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
from microdrop_application.menus import ManagePeripheralsAction, is_peripheral_ui_enabled, is_peripheral_backend_enabled
import microdrop_application.task as t
a = ManagePeripheralsAction()
print(\"action name:\", a.name, \"| has task trait:\", \"task\" in a.trait_names())
print(\"MicrodropTask restore:\", hasattr(t.MicrodropTask, \"_restore_peripherals_if_enabled\"))
'"
```
Expected: `action name: &Manage Peripherals… | has task trait: True` and `MicrodropTask restore: True`.

- [ ] **Step 9: Commit**

```bash
git add microdrop_application/menus.py microdrop_application/task.py
git commit -m "Replace single toggle with Manage Peripherals dialog + per-group restore

ManagePeripheralsAction opens the two-checkbox dialog and applies the result
via PluginGroupManager.apply. activated() restores each group independently
from its own persisted flag (backend before UI).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Dynamic preferences tabs

**Files:**
- Modify: `microdrop_application/preferences_dialog.py`

**Interfaces:**
- Produces: `PreferencesDialog` re-pulls `categories`/`panes` from live extensions on each open; idempotent `advanced_mode_tab`.

- [ ] **Step 1: Add the extension-point imports**

In `microdrop_application/preferences_dialog.py`, after the existing envisage import line:

```python
from envisage.ui.tasks.api import PreferencesDialog as _PreferencesDialog, PreferencesTab, PreferencesCategory
```

add:

```python
from envisage.api import PREFERENCES_CATEGORIES, PREFERENCES_PANES
```

- [ ] **Step 2: Make the advanced-tab append idempotent**

In `microdrop_application/preferences_dialog.py`, replace:

```python
    @observe("categories")
    def _category_changed(self, event=None):
        self.categories.append(advanced_mode_tab)
```

with:

```python
    @observe("categories")
    def _category_changed(self, event=None):
        # Idempotent: re-pulling categories on each open (see
        # _refresh_from_application) must not accumulate duplicate tabs.
        if advanced_mode_tab not in self.categories:
            self.categories.append(advanced_mode_tab)
```

- [ ] **Step 3: Add `_refresh_from_application` and call it from `traits_view`**

In `microdrop_application/preferences_dialog.py`, add this method just above `traits_view`:

```python
    def _refresh_from_application(self):
        """Re-pull contributed categories/panes from the LIVE extension points
        so plugin-contributed tabs (e.g. the magnet peripheral tab) show only
        while that plugin is loaded. The base class rebuilds ``_tabs`` reactively
        from ``categories``/``panes``, so reassigning them here refreshes the
        dialog on each open. ``advanced_mode_tab`` is appended explicitly (and
        deduped) so it is present before the reactive rebuild reads categories."""
        if self.application is None:
            return
        self.panes = [
            factory(dialog=self)
            for factory in self.application.get_extensions(PREFERENCES_PANES)
        ]
        categories = list(self.application.get_extensions(PREFERENCES_CATEGORIES))
        if advanced_mode_tab not in categories:
            categories.append(advanced_mode_tab)
        self.categories = categories
```

Then make `traits_view` refresh first — replace its opening line:

```python
    def traits_view(self):
        """Build the dynamic dialog view."""
        buttons = ["Apply", "Revert", "OK", "Cancel"]
```

with:

```python
    def traits_view(self):
        """Build the dynamic dialog view."""
        # Refresh tabs from the currently-loaded plugins each time the dialog
        # opens, so hot-loaded/unloaded plugin tabs appear/disappear live.
        self._refresh_from_application()

        buttons = ["Apply", "Revert", "OK", "Cancel"]
```

- [ ] **Step 4: Compile**

Run: `python -m py_compile microdrop_application/preferences_dialog.py`
Expected: no output.

- [ ] **Step 5: Import smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import microdrop_application.preferences_dialog as pd
print(\"_refresh_from_application:\", hasattr(pd.PreferencesDialog, \"_refresh_from_application\"))
'"
```
Expected: `_refresh_from_application: True`.

- [ ] **Step 6: Commit**

```bash
git add microdrop_application/preferences_dialog.py
git commit -m "Refresh preferences tabs from live extensions on each open

Re-pull categories/panes from get_extensions when the dialog opens so a
hot-loaded plugin's preferences tab shows only while it is loaded; dedupe the
Advanced Mode tab across repeated opens.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Split the startup-list documentation

**Files:**
- Modify: `examples/plugin_consts.py`

**Interfaces:**
- Produces: `MAGNET_UI_PLUGINS`, `MAGNET_BACKEND_PLUGINS` (documentation lists). Removes `MAGNET_PERIPHERAL_PLUGINS`.

- [ ] **Step 1: Replace the doc list**

In `examples/plugin_consts.py`, replace the block:

```python
# The optional magnet-peripheral group (PeripheralControllerPlugin +
# PeripheralProtocolControlsPlugin + PeripheralUiPlugin) is intentionally NOT
# in the default lists below. It is hot loaded/unloaded at runtime from the
# Tools -> Peripherals toggle via PluginGroupManager (group
# "magnet_peripherals"), so users without the magnet hardware aren't burdened
# with its UI/services, and it auto-restores on launch from a persisted flag.
MAGNET_PERIPHERAL_PLUGINS = [
    PeripheralControllerPlugin,        # backend (services + topics)
    PeripheralProtocolControlsPlugin,  # magnet protocol column
    PeripheralUiPlugin,                # dock pane + status icon
]
```

with:

```python
# The optional magnet peripheral is intentionally NOT in the default lists
# below. It is hot loaded/unloaded at runtime from the Tools -> Manage
# Peripherals dialog via PluginGroupManager, as TWO independent groups, so
# users without the magnet hardware aren't burdened with its UI/services and
# each group auto-restores on launch from its persisted flag.
#   - magnet_ui      group: dock pane, status icon, magnet protocol column
#   - magnet_backend group: controller (hardware + connection search)
MAGNET_UI_PLUGINS = [
    PeripheralProtocolControlsPlugin,  # magnet protocol column
    PeripheralUiPlugin,                # dock pane + status icon + tools submenu
]
MAGNET_BACKEND_PLUGINS = [
    PeripheralControllerPlugin,        # controller (services + topics + search)
]
```

- [ ] **Step 2: Compile + import smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
import examples.plugin_consts as pc
print(\"ui:\", [p.__name__ for p in pc.MAGNET_UI_PLUGINS])
print(\"backend:\", [p.__name__ for p in pc.MAGNET_BACKEND_PLUGINS])
print(\"ui plugin still excluded:\", not any(p.__name__==\"PeripheralUiPlugin\" for p in pc.FRONTEND_PLUGINS))
'"
```
Expected: ui `['PeripheralProtocolControlsPlugin', 'PeripheralUiPlugin']`, backend `['PeripheralControllerPlugin']`, `ui plugin still excluded: True`.

- [ ] **Step 3: Commit**

```bash
git add examples/plugin_consts.py
git commit -m "Split magnet peripheral doc list into UI + backend groups

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Integration smoke + manual end-to-end verification

**Files:** none (verification only).

**Interfaces:** Consumes everything above.

- [ ] **Step 1: Full wiring import smoke (Redis up)**

Ensure Redis is running (`pixi run python examples/start_redis_server.py` in a background shell), then:

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
from microdrop_application.plugin_group_manager import PluginGroupManager
from microdrop_application.menus import ManagePeripheralsAction
from microdrop_application.peripherals_manager_dialog import PeripheralsManagerModel
from microdrop_utils.tasks_runtime_helpers import rebuild_menu_bar_live
import microdrop_application.task as t, microdrop_application.preferences_dialog as pd
m = PluginGroupManager()
print(\"groups:\", sorted(m.groups))
print(\"apply:\", hasattr(m, \"apply\"))
print(\"action:\", ManagePeripheralsAction().name)
print(\"prefs refresh:\", hasattr(pd.PreferencesDialog, \"_refresh_from_application\"))
print(\"ALL WIRING OK\")
'"
```
Expected: `groups: ['magnet_backend', 'magnet_ui']`, `apply: True`, the action name, `prefs refresh: True`, `ALL WIRING OK`.

- [ ] **Step 2: Launch the app (mock device, Redis up)**

Run: `cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python examples/run_device_viewer_pluggable.py --device mock"`

- [ ] **Step 3: Manual checks** (tick each; if any fails, stop and report)

- [ ] **Backend only:** Tools → Manage Peripherals → check *Magnet Backend* → OK. Logs show the controller started, the router subscribed its listener, and a 2 s search loop running. No dock pane, no magnet column.
- [ ] **UI only** (from clean): check *Magnet UI* → OK. Magnet column appears in the protocol tree immediately; peripheral dock pane appears **with** the Z-Stage status-bar icon; "Tools → Peripherals → Z-Stage → Search Connection" submenu appears. No search loop.
- [ ] **Both:** enable both; a magnet step actuates and the tree waits for the ack.
- [ ] **Disable UI:** uncheck *Magnet UI* → OK: dock pane + status icon gone, magnet column gone, Tools submenu gone; backend search still running.
- [ ] **Disable backend:** uncheck → OK: search loop stops; logged service ids unregister (no leftover controller offers).
- [ ] **Preferences dynamism:** with UI disabled, open Preferences → no magnet tab. Enable UI, reopen → magnet tab present. Disable UI, reopen → gone. No duplicate "Advanced Mode" tab across repeated opens.
- [ ] **Re-enable idempotency:** toggle each group off→on twice; services register exactly once each cycle, panes/column/menu/icon return, no errors.
- [ ] **Restore on launch:** enable both, restart the app, confirm both groups auto-load from their flags, the dialog checkboxes match, the status icon and submenu are present.

- [ ] **Step 4: Update the project memory**

Update `C:/Users/Info/.claude/projects/C--Users-Info-PycharmProjects-pixi-microdrop/memory/project_plugin_hot_load_unload.md` to reflect the two-group split (magnet_ui / magnet_backend), the Manage Peripherals dialog (replacing the single toggle), the backend search-on-enable, and the live menu-bar/status-icon/preferences refresh. No new commit required (memory lives outside the repo).

---

## Self-Review

**Spec coverage:**
- §Component 1 (two groups) → Tasks 2, 3. ✓
- §Component 2 (menu rebuild) → Task 1. ✓
- §Component 3 (status icon) → Task 4. ✓
- §Component 4 (`add_dock_pane_live` hook) → Task 1. ✓
- §Component 5 (dialog) → Tasks 5, 6. ✓
- §Component 6 (menu wiring + restore) → Task 6. ✓
- §Component 7 (dynamic preferences) → Task 7. ✓
- §Component 8 (startup-list docs) → Task 8. ✓
- §Verification (manual checklist) → Task 9. ✓

**Type consistency:** `enabled_key`/`post_enable_publish_topic` (Task 3) match their use in `enable`/`disable` (Task 3) and `_groups_default` (Task 3). `apply(task, desired)` (Task 3) matches the call in `ManagePeripheralsAction.perform` (Task 6). `MAGNET_UI_GROUP`/`MAGNET_BACKEND_GROUP`/`PERIPHERAL_*_ENABLED_KEY` (Task 2) used consistently in Tasks 3, 6. `on_live_mounted` (Task 4) matches the call in `add_dock_pane_live` (Task 1). `rebuild_menu_bar_live(window, task, application)` (Task 1) matches calls in Task 3. `PeripheralsManagerModel.magnet_ui_enabled`/`magnet_backend_enabled` (Task 5) match reads in Task 6.

**Placeholder scan:** none — every code step shows full code; every command shows expected output.
