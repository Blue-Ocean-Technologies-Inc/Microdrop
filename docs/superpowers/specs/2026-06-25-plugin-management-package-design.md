# Extract plugin management into a `plugin_management` plugin

**Date:** 2026-06-25
**Status:** Approved (design)
**Builds on / relocates:** the plugin hot load/unload + install + uninstall work
(`feature/peripheral-hot-load`). This is a **pure relocation + decoupling refactor — no
behavior change.**

## Problem & goal

All plugin-management code currently lives inside `microdrop_application/` and is wired into
the app via the hardcoded `MicrodropTask.menu_bar` and `MicrodropPlugin`'s service offer.
That couples a cross-cutting capability to the application package. Move everything
plugin-management into a new top-level `plugin_management/` package and expose it as a
self-contained `PluginManagementPlugin` that **contributes** its Tools menu actions via
`TASK_EXTENSIONS` (the `manual_controls` / `dropbot_tools_menu` pattern) and offers the
`PluginGroupManager` service — so `microdrop_application` no longer references any
plugin-management code. Aligns with the project's decouple-plugins principle.

## Decisions (locked)

- New top-level package `plugin_management/` holds **all** plugin-management code.
- Three Tools actions contributed (no new enable/disable actions): **Install Plugin…**,
  **Uninstall Plugin…**, **Manage Plugins…** (the existing checkbox dialog does
  enable/disable).
- `PluginManagementPlugin` goes in **FRONTEND_PLUGINS** (it's a GUI plugin — contributes the
  task menu + opens dialogs; not GUI-safe in the headless backend).
- Behavior is unchanged; this is a move + rewire only.

## Architecture

```
plugin_management/                       (new top-level package)
  consts.py        PKG, PKG_name, the microdrop_application task id
  manifest.py      <- microdrop_application/plugins/manifest.py
  paths.py         <- microdrop_application/plugins/paths.py   (_PROJECT_ROOT = parents[1])
  installer.py     <- microdrop_application/plugins/installer.py
  group_manager.py <- microdrop_application/plugin_group_manager.py  (PluginGroup + PluginGroupManager)
  manage_dialog.py    <- microdrop_application/plugins_manager_dialog.py  (PluginsManagerModel)
  uninstall_dialog.py <- microdrop_application/plugins_uninstall_dialog.py (UninstallPluginModel)
  menus.py         <- the 3 action classes from microdrop_application/menus.py
  plugin.py        PluginManagementPlugin (service offer + TASK_EXTENSIONS + launch restore)
```

### Component 1 — moved modules (internal rewiring only)

The moved files keep their logic verbatim; only imports change:
- `installer.py` / `group_manager.py`: `from microdrop_application.plugins import paths` →
  `from plugin_management import paths`; `from microdrop_application.plugins.manifest import …`
  → `from plugin_management.manifest import …`; `from microdrop_application.plugin_group_manager
  import …` → `from plugin_management.group_manager import …`.
- `paths.py`: `_PROJECT_ROOT = Path(__file__).resolve().parents[1]` (now one level shallower —
  `plugin_management/paths.py` → `parents[1]` is `src/`). `default_plugins_dir()` /
  `installed_plugins_dir()` unchanged; `default_plugins/` stays at the `src/` top level.
- `menus.py` (the 3 actions): their `perform()` local imports change to
  `from plugin_management.group_manager import PluginGroupManager`,
  `from plugin_management import installer`,
  `from plugin_management.manage_dialog import PluginsManagerModel`,
  `from plugin_management.uninstall_dialog import UninstallPluginModel`. The
  `microdrop_application.dialogs.pyface_wrapper` and logger imports are unchanged.
- `group_manager.py` keeps importing `microdrop_application.helpers`
  (`get_microdrop_redis_globals_manager`), `microdrop_utils.tasks_runtime_helpers`,
  `microdrop_utils.dramatiq_pub_sub_helpers` — those modules don't move.

The service-offer protocol uses the **class** `PluginGroupManager` (imported), and the
actions look it up with the same class — so no protocol-string drift.

### Component 2 — `PluginManagementPlugin` (`plugin_management/plugin.py`, new)

Mirrors `ManualControlsPlugin`:
```python
class PluginManagementPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    my_service_offers = List(contributes_to=SERVICE_OFFERS)
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)
    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")

    def _my_service_offers_default(self):
        return [ServiceOffer(protocol=PluginGroupManager,
                             factory=self._create_plugin_group_manager)]

    def _create_plugin_group_manager(self, *a, **k):
        if self._manager is None:
            from .group_manager import PluginGroupManager
            self._manager = PluginGroupManager()
        return self._manager

    def _contributed_task_extensions_default(self):
        from .menus import InstallPluginAction, UninstallPluginAction, ManagePluginsAction
        return [TaskExtension(task_id=self.task_id_to_contribute_view, actions=[
            SchemaAddition(id="plugin_management.install",   factory=InstallPluginAction,   path="MenuBar/Tools"),
            SchemaAddition(id="plugin_management.uninstall", factory=UninstallPluginAction, path="MenuBar/Tools"),
            SchemaAddition(id="plugin_management.manage",    factory=ManagePluginsAction,   path="MenuBar/Tools"),
        ])]
```
- The `SchemaAddition`s land in the existing empty Tools `SMenu` anchored in
  `MicrodropTask.menu_bar`. Order is controlled with `before`/`after` if declaration order
  doesn't hold (settled in the plan); the target order is Install, Uninstall, Manage.
- Because the actions are contributed via `task_extensions`, they are **always present** and
  survive `rebuild_menu_bar_live` (which recomputes `task.extra_actions` from the live
  `application.task_extensions`).

### Component 3 — launch restore (moved into the plugin)

The `_restore_enabled_plugin_groups` logic moves out of `MicrodropTask.activated()` into the
plugin, triggered like `dropbot_tools_menu/plugin.py`:
```python
@observe("application:application_initialized")
def _on_application_initialized(self, event):
    window = self.application.active_window
    if window is None:
        self.application.on_trait_change(self._on_window_created, "active_window")
    else:
        self._restore_enabled_groups(window)

def _on_window_created(self, window):
    if window is not None:
        self.application.on_trait_change(self._on_window_created, "active_window", remove=True)
        self._restore_enabled_groups(window)

def _restore_enabled_groups(self, window):
    from . import paths
    paths.ensure_on_sys_path()
    manager = self.application.get_service(PluginGroupManager)
    if manager is None:
        return
    task = window.active_task
    app_globals = get_microdrop_redis_globals_manager()
    for group_name, group in list(manager.groups.items()):
        if (group.enabled_key and app_globals.get(group.enabled_key, False)
                and not manager.is_loaded(group_name)):
            manager.enable(task, group_name)
```
`window.active_task` is the `MicrodropTask`; `manager.enable(task, …)` uses
`task.window.application` internally exactly as before.

### Component 4 — `microdrop_application` edits (the only external blast radius)

- `microdrop_application/menus.py`: remove `InstallPluginAction`, `UninstallPluginAction`,
  `ManagePluginsAction` (and the now-unused local imports they introduced). **Keep**
  `AdvancedModeAction`, `is_advanced_mode`, `app_globals`, and the `ADVANCED_MODE_CHANGE`
  import (Edit-menu toggle is untouched).
- `microdrop_application/task.py`: Tools menu becomes the empty anchor
  `SMenu(id="Tools", name="&Tools")`; remove the `InstallPluginAction`/`ManagePluginsAction`/
  `UninstallPluginAction` import, remove `_restore_enabled_plugin_groups` and its call in
  `activated()`. `AdvancedModeAction` import stays.
- `microdrop_application/plugin.py`: remove the `PluginGroupManager` service offer (the
  `plugin_group_manager_service_offer` entry, `_create_plugin_group_manager_service`, and the
  `_plugin_group_manager` cache trait + its `Any` import if now unused). The preferences
  dialog offer stays.
- `examples/plugin_consts.py`: `from plugin_management.plugin import PluginManagementPlugin`;
  add it to `FRONTEND_PLUGINS`.

### Files

**New (package):** `plugin_management/{__init__,consts,manifest,paths,installer,group_manager,manage_dialog,uninstall_dialog,menus,plugin}.py`

**Moved-from → deleted:**
- `microdrop_application/plugin_group_manager.py`
- `microdrop_application/plugins/{__init__,manifest,paths,installer}.py`
- `microdrop_application/plugins_manager_dialog.py`
- `microdrop_application/plugins_uninstall_dialog.py`

**Edited:** `microdrop_application/{menus,task,plugin}.py`, `examples/plugin_consts.py`

**Unchanged data:** `default_plugins/magnet_peripherals/microdrop_plugin.json`

### Dependency direction

After the move, `plugin_management` → `microdrop_application` (consts/helpers/dialogs) +
`microdrop_utils` is the only direction; `microdrop_application` imports nothing from
`plugin_management`. No import cycle.

## Error handling / cross-cutting

- Behavior is identical to today; all the install/uninstall/enable/disable safety
  (zip-slip, allowlist, consent, atomic swap, module purge, loaded-guards, flag clearing)
  is carried verbatim in the moved files.
- The contributed actions are static (always shown) regardless of group load state, same as
  the prior hardcoded menu.
- Testing (project convention — no pytest): `py_compile` the package + edited files; the
  existing install/uninstall/discovery `pixi` smokes re-pointed at `plugin_management.*`; an
  `import examples.plugin_consts` smoke proving `PluginManagementPlugin` is in
  `FRONTEND_PLUGINS`; and manual GUI (the three Tools actions appear and work; restore on
  launch still loads enabled groups).

## Verification (manual, Redis up, `--device mock`)

1. **Menu present:** Tools shows Install Plugin…, Uninstall Plugin…, Manage Plugins… (now
   contributed by `PluginManagementPlugin`, not hardcoded).
2. **Round-trip unchanged:** install the demo archive, enable a group via Manage Plugins,
   uninstall it — all behave exactly as before.
3. **Restore on launch:** enable a group, restart → it auto-loads (restore now runs from the
   plugin's `application_initialized` hook).
4. **Decoupling:** `grep -rn "plugin_group_manager\|microdrop_application.plugins\|plugins_manager_dialog\|plugins_uninstall_dialog" microdrop_application/` returns nothing (all references moved to `plugin_management`).

## Known limitations (accepted)

- None beyond those already documented for install/uninstall/hot-load (no crypto trust,
  single-process, sys.path shadow) — unchanged by this move.
