# Uninstall installed plugins

**Date:** 2026-06-25
**Status:** Approved (design)
**Builds on:** the install-from-zip feature (`feature/peripheral-hot-load`, commits
`3d96ff9d`..`b5989336`) — `PluginGroupManager` (manifest-driven groups), the
`microdrop_application/plugins/` package (`manifest`, `paths`, `installer`), and the
`Install Plugin…` / `Manage Plugins…` Tools actions.

## Problem & goals

Plugins can be installed from a `.microdrop_plugin` archive into
`installed_plugins/<name>/`, but there is no way to remove one. Add a
**Tools → Uninstall Plugin…** action that removes a user-installed plugin: its files, its
registered groups, its imported modules, and its persisted enabled flags — auto-disabling
any of its groups that are currently loaded first.

Goals:
- A dedicated **Uninstall Plugin…** menu item that lists only **user-installed** plugins and
  removes the chosen one.
- **Auto-disable** any loaded group of that plugin (full hot-unload) before deleting files.
- Clean removal: drop the groups from the manager, delete the install dir, purge the
  packages from `sys.modules`, and clear the groups' enabled-flag app-globals.

Non-goals: uninstalling **bundled** plugins under `default_plugins/` (magnet) — they ship
with the repo and are disable-only; per-group uninstall (the unit is the whole installed
plugin / its dir); dependency tracking between plugins.

## Decisions (locked)

- UI: a **separate "Uninstall Plugin…" menu item** (not embedded in the Manage Plugins
  dialog), symmetric with Install Plugin….
- Loaded behavior: **auto-disable then uninstall** (one click; the action hot-unloads any
  enabled group of the plugin, then removes it).
- Unit: a whole **installed plugin** = one `installed_plugins/<manifest.name>/` dir and all
  the groups its manifest declares. Bundled plugins are excluded from the uninstall list.

## Architecture

```
Tools → Uninstall Plugin…  (UninstallPluginAction)
   manager.installed_plugins()  →  (empty? info dialog : open UninstallPluginModel)
     pick a plugin + OK → confirm("Uninstall <label>? deletes its files") == YES
       → installer.uninstall_plugin(task, manager, manifest_name)
            read packages from source_dir manifest
            → for each loaded group: manager.disable(task, group)      (hot-unload)
            → _purge_package_modules(packages)                          (release handles)
            → manager.deregister_plugin(name)   (pop groups + clear enabled flags)
            → shutil.rmtree(source_dir)
       → information("Uninstalled <label>")
```

### Component 1 — Install-source tracking in `PluginGroupManager`

`PluginGroup` gains three fields so the manager knows where each group came from and which
plugin owns it:
- `manifest_name = Str()` — the owning manifest's `name`.
- `manifest_label = Str()` — the owning manifest's `label` (shown in the uninstall list).
- `source_dir = Str()` — the directory the manifest was discovered/installed from.

`_add_manifest_groups(manifest, source_dir, into=None)` records these on every group it
builds. `_discover_groups` passes the manifest's directory; `register_manifest(manifest,
source_dir)` (called by the installer) passes the install target dir. The installer's
existing `register_manifest(manifest)` call is updated to pass `str(target)`.

New manager methods:
- `installed_plugins() -> list[tuple[str, str, str, list[str]]]` — one entry per distinct
  **user-installed** plugin (a group whose `source_dir` is under `paths.installed_plugins_dir()`),
  as `(manifest_name, manifest_label, source_dir, [group_names])`. Bundled
  (`default_plugins/`) plugins are excluded. Group names are collected in discovery order.
- `installed_plugin(name) -> tuple | None` — the entry for `name`, or None if it isn't a
  user-installed plugin.
- `deregister_plugin(name) -> None` — for every group with `manifest_name == name`: clear
  `app_globals[group.enabled_key]` (if set) and pop the group from `self.groups`.

### Component 2 — `installer.uninstall_plugin(task, manager, manifest_name)`

```python
def uninstall_plugin(task, manager, manifest_name):
    """Auto-disable any loaded group of the installed plugin, purge its modules,
    deregister its groups, and delete its installed_plugins/<name>/ dir. Raises
    InstallError if manifest_name isn't a user-installed plugin (bundled/unknown)."""
```
Steps:
1. `info = manager.installed_plugin(manifest_name)`; if None → raise `InstallError`
   (`"'<name>' is not an installed plugin"`).
2. Read `packages` by `load_manifest(Path(source_dir)/paths.MANIFEST_FILENAME)`; on failure
   default to `[]` (still remove the dir).
3. For each `group_name` in the plugin's groups: `if manager.is_loaded(group_name):
   manager.disable(task, group_name)` (full hot-unload — panes/services/menu).
4. `_purge_package_modules(packages)` (releases module/`.pyd` handles before deletion —
   Windows-safe), then `manager.deregister_plugin(manifest_name)`.
5. `shutil.rmtree(source_dir)` (raise on failure — surfaced as an error dialog; the manager
   state is already consistent because the groups were deregistered first).

(`_purge_package_modules` already exists in `installer.py`.)

### Component 3 — Uninstall dialog (`microdrop_application/plugins_uninstall_dialog.py`, new)

`UninstallPluginModel(installed)` — `installed` is the `installed_plugins()` list. A
single-select dropdown over the plugins, mapping a display string to the `manifest_name`:
```python
class UninstallPluginModel(HasTraits):
    selected = Str()            # chosen manifest_name
    def __init__(self, installed, **traits):
        super().__init__(**traits)
        self._installed = list(installed)   # [(name, label, dir, group_names), ...]
        if self._installed:
            self.selected = self._installed[0][0]
    def traits_view(self):
        # EnumEditor maps each manifest_name value -> its display label
        values = {name: f"{label} ({name})"
                  for name, label, _dir, _g in self._installed}
        return View(
            Item("selected", editor=EnumEditor(values=values), show_label=False),
            buttons=["OK", "Cancel"], kind="livemodal",
            title="Uninstall Plugin", resizable=True)
```
(Exact `EnumEditor` wiring is settled in the plan; the contract is: it offers the installed
plugins by label and `selected` is the chosen `manifest_name`.) Qt-free TraitsUI.

### Component 4 — `UninstallPluginAction` + menu wiring

`UninstallPluginAction(TaskAction)` in `menus.py`:
- fetch the `PluginGroupManager` service (log + return if missing);
- `installed = manager.installed_plugins()`; if empty → `information(parent=None,
  title="Uninstall Plugin", message="No user-installed plugins to uninstall.")` and return;
- open `UninstallPluginModel(installed)` via `edit_traits(kind="livemodal")`; if not
  `ui.result`, return;
- look up the chosen label; `confirm(parent=None, message="Uninstall <b>{label}</b>?<br><br>
  This deletes its installed files.", title="Uninstall Plugin?", cancel=False) == YES` →
  else return;
- `try: installer.uninstall_plugin(task, manager, name)` → `information("Uninstalled
  <label>.")`; `except Exception as e: error(parent=None, title="Uninstall failed",
  message=str(e))`.

`task.py`: Tools menu becomes
`SMenu(InstallPluginAction(), UninstallPluginAction(), ManagePluginsAction(), id="Tools", name="&Tools")`.

### Error handling / cross-cutting

- Bundled magnet (under `default_plugins/`) is never in `installed_plugins()`, so it cannot
  be uninstalled — only disabled.
- Auto-disable + `_purge_package_modules` run **before** `rmtree` so files aren't locked; if
  `rmtree` still fails (a rare Windows lock), the groups are already deregistered (manager
  state consistent) and the error is surfaced via the error dialog.
- `deregister_plugin` clears the enabled flags so a later reinstall doesn't auto-enable the
  plugin on next launch.
- Testing (project convention — no pytest): `py_compile` + `pixi` import/introspection
  smokes — install a fixture archive into a temp `dest_root`, then `uninstall_plugin` and
  assert the dir is gone, the groups are absent from `manager.groups`, and the enabled flags
  are cleared — plus manual GUI for the full pick → confirm → remove flow.

## Files

**New**
- `microdrop_application/plugins_uninstall_dialog.py` — `UninstallPluginModel`

**Edit**
- `microdrop_application/plugin_group_manager.py` — `PluginGroup` source fields;
  `_add_manifest_groups`/`_discover_groups`/`register_manifest` carry `source_dir`;
  `installed_plugins`/`installed_plugin`/`deregister_plugin`
- `microdrop_application/plugins/installer.py` — `uninstall_plugin`; update the
  `register_manifest` call to pass the target dir
- `microdrop_application/menus.py` — `UninstallPluginAction`
- `microdrop_application/task.py` — Tools-menu wiring (three items)

## Verification (manual, Redis up, `--device mock`)

1. **Install** the demo archive (`examples/plugins/magnet_peripherals.microdrop_plugin`) via
   Tools → Install Plugin….
2. **Uninstall list** — Tools → Uninstall Plugin… lists that installed plugin but **not** the
   bundled magnet (if the bundled one is the only magnet, the installed copy appears as its
   own entry by manifest name).
3. **Auto-disable + remove** — enable one of its groups, then Uninstall Plugin… → pick it →
   confirm → its group is hot-unloaded (pane/menu gone), the `installed_plugins/<name>/` dir
   is deleted, and it disappears from both Manage Plugins and Uninstall lists.
4. **Flags cleared** — restart: the uninstalled plugin does not auto-load (its enabled flags
   were cleared).
5. **Bundled is safe** — the bundled magnet never appears in the Uninstall list and remains
   usable via Manage Plugins.
6. **Empty state** — with nothing installed, Uninstall Plugin… shows "No user-installed
   plugins to uninstall."

## Known limitations (accepted)

- The `installed_plugins/` dir stays on `sys.path` after an uninstall (harmless when the
  removed package dir is gone).
- If the OS holds a lock on an extracted file (rare on Windows for a fully-disabled plugin),
  `rmtree` may fail and leave files behind; the manager has already deregistered the groups,
  so a retry or manual delete completes it.
