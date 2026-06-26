# Uninstall Installed Plugins — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Tools → Uninstall Plugin… that removes a user-installed plugin — auto-disabling any loaded group, purging its modules, deregistering its groups + clearing their enabled flags, and deleting its `installed_plugins/<name>/` dir.

**Architecture:** `PluginGroupManager` records each group's owning manifest + source dir, so it can list user-installed plugins (those under `installed_plugins/`, excluding bundled `default_plugins/`) and deregister them. `installer.uninstall_plugin` orchestrates the teardown + delete; a small `UninstallPluginAction` + dropdown dialog drive it.

**Tech Stack:** Envisage 7 / Pyface Tasks 8 / TraitsUI 8 / PySide6 / Python 3.13, `shutil`, Dramatiq+Redis.

**Spec:** `docs/superpowers/specs/2026-06-25-uninstall-plugin-design.md`

## Global Constraints

- **Working directory for all commands:** `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src`. Commits land in the submodule on branch `feature/peripheral-hot-load`.
- **Testing convention (this project):** NO pytest. Each task gates on (a) `python -m py_compile <files>`, then (b) a `pixi run` import/introspection smoke from the parent dir, then (c) manual GUI at the end (Task 5). Run Python only via pixi: `cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '...'"`. Redis must be running.
- **Any smoke that touches installed/uninstalled plugins** must set `from traits.etsconfig.api import ETSConfig; ETSConfig.application_home = <tempdir>` BEFORE importing `microdrop_application.plugins.paths` (or the manager), AND install **without** a `dest_root` override so the plugin lands in the real (but temp) `installed_plugins/` — `installed_plugins()` keys off `installed_plugins_dir()`, so a `dest_root` elsewhere would make the plugin look non-installed.
- **Conventions:** dataclasses for inert parsed data; HasTraits elsewhere; f-strings only; logger via `from logger.logger_service import get_logger`; no Qt in model/service layers (Qt only in views + `tasks_runtime_helpers.py`); dialogs via `pyface_wrapper` or TraitsUI `edit_traits(kind="livemodal")`. Manifest is the source of truth; manifest-derived strings shown in dialogs are HTML-escaped via `escape_html_multiline`.
- **Commit trailer:** end every commit message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `microdrop_application/plugin_group_manager.py` | install-source tracking on `PluginGroup`; `installed_plugins`/`installed_plugin`/`deregister_plugin`; `register_manifest`/`_add_manifest_groups` carry `source_dir` | Modify |
| `microdrop_application/plugins/installer.py` | `uninstall_plugin`; pass target dir into `register_manifest` | Modify |
| `microdrop_application/plugins_uninstall_dialog.py` | `UninstallPluginModel` dropdown | Create |
| `microdrop_application/menus.py` | `UninstallPluginAction` | Modify |
| `microdrop_application/task.py` | Tools-menu wiring (three items) | Modify |

---

## Task 1: Install-source tracking + query/deregister in `PluginGroupManager`

**Files:**
- Modify: `microdrop_application/plugin_group_manager.py`

**Interfaces:**
- Produces: `PluginGroup` gains `manifest_name: Str`, `manifest_label: Str`, `source_dir: Str`; `_add_manifest_groups(manifest, source_dir="", into=None)`; `register_manifest(manifest, source_dir="")`; `installed_plugins() -> list[(name, label, source_dir, [group_names])]`; `installed_plugin(name) -> tuple|None`; `deregister_plugin(name) -> None`.

- [ ] **Step 1: Add the `Path` import**

In `microdrop_application/plugin_group_manager.py`, after `import importlib` add:

```python
from pathlib import Path
```

- [ ] **Step 2: Add the three source-tracking fields to `PluginGroup`**

In the `PluginGroup` class, after the `post_enable_publish_topic = Str()` line, add:

```python
    #: The owning manifest's name + label, and the directory the manifest was
    #: discovered/installed from. Used to list and uninstall user-installed
    #: plugins (those whose source_dir is under installed_plugins/).
    manifest_name = Str()
    manifest_label = Str()
    source_dir = Str()
```

- [ ] **Step 3: Thread `source_dir` through discovery + registration**

Replace `_discover_groups`'s `_add_manifest_groups` call. Change:

```python
            self._add_manifest_groups(manifest, into=groups)
```

to:

```python
            self._add_manifest_groups(
                manifest, source_dir=str(manifest_dir), into=groups)
```

Replace the whole `_add_manifest_groups` method with:

```python
    def _add_manifest_groups(self, manifest, source_dir="", into=None):
        """Create a PluginGroup per spec in ``manifest`` and put it in ``into``
        (defaults to self.groups). ``source_dir`` is the dir the manifest came
        from (recorded for uninstall). Last writer wins on a name collision."""
        target = self.groups if into is None else into
        for spec in manifest.groups:
            target[spec.name] = PluginGroup(
                name=spec.name,
                label=spec.label,
                plugin_specs=list(spec.plugins),
                enabled_key=spec.enabled_key,
                post_enable_publish_topic=spec.post_enable_publish_topic,
                manifest_name=manifest.name,
                manifest_label=manifest.label,
                source_dir=source_dir,
            )
```

Replace the `register_manifest` signature line. Change:

```python
    def register_manifest(self, manifest):
```

to:

```python
    def register_manifest(self, manifest, source_dir=""):
```

and change its final line:

```python
        self._add_manifest_groups(manifest)
```

to:

```python
        self._add_manifest_groups(manifest, source_dir=source_dir)
```

- [ ] **Step 4: Add the query + deregister methods**

In `PluginGroupManager`, right after the `register_manifest` method, add:

```python
    def installed_plugins(self):
        """User-installed plugins (whose source_dir sits directly under
        installed_plugins/), one entry per distinct owning manifest, as
        (name, label, source_dir, [group_names]) in discovery order. Bundled
        (default_plugins/) plugins are excluded — they can't be uninstalled."""
        try:
            base = paths.installed_plugins_dir().resolve()
        except OSError:
            return []
        out = {}
        for group in self.groups.values():
            if not group.source_dir:
                continue
            try:
                under = Path(group.source_dir).resolve().parent == base
            except OSError:
                under = False
            if not under:
                continue
            entry = out.get(group.manifest_name)
            if entry is None:
                entry = (group.manifest_name,
                         group.manifest_label or group.manifest_name,
                         group.source_dir, [])
                out[group.manifest_name] = entry
            entry[3].append(group.name)
        return list(out.values())

    def installed_plugin(self, manifest_name):
        """The installed_plugins() entry for ``manifest_name``, or None if it
        isn't a user-installed plugin."""
        for entry in self.installed_plugins():
            if entry[0] == manifest_name:
                return entry
        return None

    def deregister_plugin(self, manifest_name):
        """Drop every group owned by ``manifest_name`` from the registry and
        clear its persisted enabled flag. Used by uninstall."""
        for name in [n for n, g in self.groups.items()
                     if g.manifest_name == manifest_name]:
            group = self.groups.pop(name)
            if group.enabled_key:
                try:
                    if group.enabled_key in app_globals:
                        del app_globals[group.enabled_key]
                except Exception as e:
                    logger.debug(f"could not clear flag {group.enabled_key}: {e}")
```

- [ ] **Step 5: Compile**

Run: `python -m py_compile microdrop_application/plugin_group_manager.py`
Expected: no output.

- [ ] **Step 6: Source-tracking smoke (scratch app-home, Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile, json
from traits.etsconfig.api import ETSConfig
ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdtest_\")
from microdrop_application.plugin_group_manager import PluginGroupManager, app_globals
from microdrop_application.plugins import paths
from microdrop_application.plugins.manifest import load_manifest
m = PluginGroupManager()
print(\"bundled magnet excluded from installed:\", m.installed_plugins() == [])
man = load_manifest(json.dumps({\"schema_version\":1,\"name\":\"demo_plugin\",\"label\":\"Demo\",\"version\":\"0.1\",\"packages\":[\"demo_pkg\"],\"groups\":[{\"name\":\"demo_group\",\"label\":\"Demo G\",\"plugins\":[\"demo_pkg.plugin:DemoPlugin\"],\"enabled_key\":\"microdrop.demo_enabled\"}]}))
src = str(paths.installed_plugins_dir()/\"demo_plugin\")
m.register_manifest(man, source_dir=src)
ip = m.installed_plugins()
print(\"installed entry:\", ip)
app_globals[\"microdrop.demo_enabled\"] = True
m.deregister_plugin(\"demo_plugin\")
print(\"group gone:\", \"demo_group\" not in m.groups, \"| flag cleared:\", \"microdrop.demo_enabled\" not in app_globals)
print(\"installed_plugin(missing):\", m.installed_plugin(\"nope\"))
'"
```
Expected: `bundled magnet excluded from installed: True`; `installed entry: [('demo_plugin', 'Demo', '<...>/installed_plugins/demo_plugin', ['demo_group'])]`; `group gone: True | flag cleared: True`; `installed_plugin(missing): None`.

- [ ] **Step 7: Commit**

```bash
git add microdrop_application/plugin_group_manager.py
git commit -m "Track install source on plugin groups; add installed_plugins/deregister

Records each group's owning manifest name/label + source dir, and adds
installed_plugins()/installed_plugin()/deregister_plugin() so user-installed
plugins (under installed_plugins/, excluding bundled default_plugins) can be
listed and removed. register_manifest now carries the install dir.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `installer.uninstall_plugin` + pass target into `register_manifest`

**Files:**
- Modify: `microdrop_application/plugins/installer.py`

**Interfaces:**
- Consumes: Task 1 `installed_plugin`/`deregister_plugin`/`register_manifest(manifest, source_dir)`; existing `_purge_package_modules`, `load_manifest`, `paths`.
- Produces: `uninstall_plugin(task, manager, manifest_name) -> None`.

- [ ] **Step 1: Pass the install dir into `register_manifest`**

In `microdrop_application/plugins/installer.py`, in `install_from_zip`, change:

```python
    manager.register_manifest(manifest)
```

to:

```python
    manager.register_manifest(manifest, str(target))
```

- [ ] **Step 2: Add `uninstall_plugin`**

Append to `microdrop_application/plugins/installer.py`:

```python
def uninstall_plugin(task, manager, manifest_name):
    """Remove a user-installed plugin: auto-disable any of its loaded groups,
    purge its modules, deregister its groups (clearing their enabled flags),
    and delete its installed_plugins/<name>/ directory.

    Raises InstallError if ``manifest_name`` isn't a user-installed plugin
    (bundled or unknown)."""
    info = manager.installed_plugin(manifest_name)
    if info is None:
        raise InstallError(f"'{manifest_name}' is not an installed plugin")
    _name, _label, source_dir, group_names = info

    # Read the declared packages (for the sys.modules purge) before removal.
    try:
        manifest = load_manifest(Path(source_dir) / paths.MANIFEST_FILENAME)
        packages = manifest.packages
    except Exception:
        packages = []

    # Auto-disable any loaded group (full hot-unload) before deleting files.
    for group_name in group_names:
        if manager.is_loaded(group_name):
            manager.disable(task, group_name)

    # Purge first so module/.pyd handles are released before rmtree (Windows).
    _purge_package_modules(packages)
    manager.deregister_plugin(manifest_name)

    source = Path(source_dir)
    if source.exists():
        shutil.rmtree(source)
    logger.info(f"uninstalled plugin '{manifest_name}' from {source_dir}")
```

- [ ] **Step 3: Compile**

Run: `python -m py_compile microdrop_application/plugins/installer.py`
Expected: no output.

- [ ] **Step 4: Install → uninstall round-trip smoke (scratch app-home, Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile, zipfile, json
from pathlib import Path
from traits.etsconfig.api import ETSConfig
ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdtest_\")
from microdrop_application.plugin_group_manager import PluginGroupManager, app_globals
from microdrop_application.plugins import installer, paths

tmp = Path(tempfile.mkdtemp())
man = {\"schema_version\":1,\"name\":\"demo_plugin\",\"label\":\"Demo\",\"version\":\"0.1\",\"packages\":[\"demo_pkg\"],\"groups\":[{\"name\":\"demo_group\",\"label\":\"Demo G\",\"plugins\":[\"demo_pkg.plugin:DemoPlugin\"],\"enabled_key\":\"microdrop.demo_enabled\"}]}
arc = tmp/\"demo.microdrop_plugin\"
with zipfile.ZipFile(arc, \"w\") as zf:
    zf.writestr(\"microdrop_plugin.json\", json.dumps(man))
    zf.writestr(\"demo_pkg/__init__.py\", \"\")
    zf.writestr(\"demo_pkg/plugin.py\", \"class DemoPlugin: pass\")
m = PluginGroupManager()
# install into the REAL (temp) installed_plugins dir — no dest_root override:
installer.install_from_zip(arc, m, confirm=lambda x: True)
target = paths.installed_plugins_dir()/\"demo_plugin\"
app_globals[\"microdrop.demo_enabled\"] = True
print(\"installed:\", target.is_dir(), \"| listed:\", [e[0] for e in m.installed_plugins()])
# uninstall (no loaded groups, so task=None is fine):
installer.uninstall_plugin(None, m, \"demo_plugin\")
print(\"dir gone:\", not target.exists(), \"| group gone:\", \"demo_group\" not in m.groups, \"| flag cleared:\", \"microdrop.demo_enabled\" not in app_globals)
try:
    installer.uninstall_plugin(None, m, \"demo_plugin\")
    print(\"FAIL: re-uninstall not rejected\")
except installer.InstallError:
    print(\"re-uninstall rejected OK\")
'"
```
Expected: `installed: True | listed: ['demo_plugin']`; `dir gone: True | group gone: True | flag cleared: True`; `re-uninstall rejected OK`.

- [ ] **Step 5: Commit**

```bash
git add microdrop_application/plugins/installer.py
git commit -m "Add installer.uninstall_plugin; pass install dir into register_manifest

uninstall_plugin auto-disables loaded groups, purges modules, deregisters
the groups, and rmtrees the installed_plugins/<name>/ dir. install_from_zip
now records the install dir so the plugin is listable/uninstallable.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Uninstall dialog model

**Files:**
- Create: `microdrop_application/plugins_uninstall_dialog.py`

**Interfaces:**
- Produces: `UninstallPluginModel(installed: list[(name,label,dir,group_names)])` with `selected: Str` (the chosen `manifest_name`) and a livemodal `traits_view` (EnumEditor dropdown).

- [ ] **Step 1: Create the file**

Create `microdrop_application/plugins_uninstall_dialog.py`:

```python
"""Uninstall Plugin dialog model: pick one user-installed plugin to remove.

Built from the manager's installed_plugins() list. Qt-free TraitsUI; the action
owns the orchestration (confirm + installer.uninstall_plugin)."""

from traits.api import HasTraits, Str
from traitsui.api import EnumEditor, Item, View


class UninstallPluginModel(HasTraits):
    """Single-select of a user-installed plugin to uninstall. ``selected`` is
    the chosen manifest_name."""

    selected = Str()

    def __init__(self, installed, **traits):
        super().__init__(**traits)
        # installed: list of (name, label, source_dir, group_names)
        self._installed = list(installed)
        if self._installed:
            self.selected = self._installed[0][0]

    def traits_view(self):
        # EnumEditor `values` maps each stored value (manifest_name) -> label.
        values = {name: f"{label} ({name})"
                  for name, label, _dir, _groups in self._installed}
        return View(
            Item("selected", editor=EnumEditor(values=values), show_label=False),
            buttons=["OK", "Cancel"],
            kind="livemodal",
            title="Uninstall Plugin",
            resizable=True,
        )
```

- [ ] **Step 2: Compile**

Run: `python -m py_compile microdrop_application/plugins_uninstall_dialog.py`
Expected: no output.

- [ ] **Step 3: Import + selection smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
from microdrop_application.plugins_uninstall_dialog import UninstallPluginModel
m = UninstallPluginModel([(\"demo_plugin\",\"Demo\",\"/d\",[\"demo_group\"]), (\"p2\",\"Two\",\"/e\",[\"g2\"])])
print(\"default selected:\", m.selected)
m.selected = \"p2\"
print(\"reassigned:\", m.selected)
empty = UninstallPluginModel([])
print(\"empty selected:\", repr(empty.selected))
'"
```
Expected: `default selected: demo_plugin`, `reassigned: p2`, `empty selected: ''`.

- [ ] **Step 4: Commit**

```bash
git add microdrop_application/plugins_uninstall_dialog.py
git commit -m "Add Uninstall Plugin dialog model (single-select dropdown)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `UninstallPluginAction` + Tools-menu wiring

**Files:**
- Modify: `microdrop_application/menus.py`
- Modify: `microdrop_application/task.py`

**Interfaces:**
- Consumes: Task 1 `installed_plugins`; Task 2 `installer.uninstall_plugin`; Task 3 `UninstallPluginModel`; `pyface_wrapper` `confirm`/`information`/`error`/`YES`/`escape_html_multiline`.
- Produces: `UninstallPluginAction(TaskAction)`; Tools menu carrying Install, Uninstall, Manage.

- [ ] **Step 1: Add `UninstallPluginAction` to `menus.py`**

In `microdrop_application/menus.py`, immediately after the `InstallPluginAction` class, add:

```python
class UninstallPluginAction(TaskAction):
    """Tools-menu action: remove a user-installed plugin (its files, groups,
    modules, and enabled flags), auto-disabling any loaded group first. Bundled
    plugins are not listed."""

    id = "uninstall_plugin_action"
    name = "&Uninstall Plugin…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Uninstall Plugin: no task available")
            return
        from microdrop_application.dialogs.pyface_wrapper import (
            confirm, information, error as error_dialog, YES, escape_html_multiline,
        )
        from microdrop_application.plugin_group_manager import PluginGroupManager
        from microdrop_application.plugins import installer
        from microdrop_application.plugins_uninstall_dialog import UninstallPluginModel

        manager = task.window.application.get_service(PluginGroupManager)
        if manager is None:
            logger.error("Uninstall Plugin: PluginGroupManager service not found")
            return

        installed = manager.installed_plugins()
        if not installed:
            information(parent=None, title="Uninstall Plugin",
                       message="No user-installed plugins to uninstall.")
            return

        model = UninstallPluginModel(installed)
        ui = model.edit_traits(kind="livemodal")
        if not ui.result:
            return
        name = model.selected
        label = {n: l for n, l, _d, _g in installed}.get(name, name)
        safe_label = escape_html_multiline(label)
        if confirm(parent=None,
                   message=f"Uninstall <b>{safe_label}</b>?<br><br>"
                           f"This deletes its installed files.",
                   title="Uninstall Plugin?", cancel=False) != YES:
            return
        try:
            installer.uninstall_plugin(task, manager, name)
        except Exception as e:
            error_dialog(parent=None, title="Uninstall failed", message=str(e))
            return
        information(parent=None, title="Plugin uninstalled",
                   message=f"Uninstalled <b>{safe_label}</b>.")
```

- [ ] **Step 2: Wire the Tools menu in `task.py`**

In `microdrop_application/task.py`, change the menus import:

```python
from .menus import AdvancedModeAction, ManagePluginsAction, InstallPluginAction
```

to:

```python
from .menus import (
    AdvancedModeAction, ManagePluginsAction, InstallPluginAction,
    UninstallPluginAction,
)
```

and change the Tools `SMenu`:

```python
        SMenu(InstallPluginAction(), ManagePluginsAction(), id="Tools", name="&Tools"),
```

to:

```python
        SMenu(InstallPluginAction(), UninstallPluginAction(), ManagePluginsAction(),
              id="Tools", name="&Tools"),
```

- [ ] **Step 3: Compile**

Run: `python -m py_compile microdrop_application/menus.py microdrop_application/task.py`
Expected: no output.

- [ ] **Step 4: Import + introspection smoke (Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import microdrop_application.menus as mn, microdrop_application.task as t
a = mn.UninstallPluginAction()
print(\"action:\", a.name, \"| has task trait:\", \"task\" in a.trait_names())
print(\"task imports UninstallPluginAction:\", hasattr(t, \"UninstallPluginAction\"))
'"
```
Expected: `action: &Uninstall Plugin… | has task trait: True`, `task imports UninstallPluginAction: True`.

- [ ] **Step 5: Commit**

```bash
git add microdrop_application/menus.py microdrop_application/task.py
git commit -m "Add Uninstall Plugin menu action + Tools wiring

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Integration smoke + manual verification

**Files:** none (verification only).

- [ ] **Step 1: Full wiring import smoke (scratch app-home, Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig
ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdtest_\")
from microdrop_application.plugin_group_manager import PluginGroupManager
from microdrop_application.plugins import installer
from microdrop_application.plugins_uninstall_dialog import UninstallPluginModel
import microdrop_application.menus as mn, microdrop_application.task as t
m = PluginGroupManager()
print(\"installed (none yet):\", m.installed_plugins())
print(\"action:\", mn.UninstallPluginAction().name)
print(\"uninstall_plugin present:\", hasattr(installer, \"uninstall_plugin\"))
print(\"ALL WIRING OK\")
'"
```
Expected: `installed (none yet): []`, the action name, `uninstall_plugin present: True`, `ALL WIRING OK`.

- [ ] **Step 2: Launch the app (mock device, Redis up)**

Run: `cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python examples/build_plugin_zip.py && python examples/run_device_viewer_pluggable.py --device mock"`

- [ ] **Step 3: Manual checks** (tick each; stop and report on any failure)

- [ ] **Empty state:** with nothing installed, Tools → Uninstall Plugin… shows "No user-installed plugins to uninstall."
- [ ] **Install then list:** Tools → Install Plugin… → pick `examples/plugins/magnet_peripherals.microdrop_plugin` → consent → installed. Tools → Uninstall Plugin… now lists it (by label). The **bundled** magnet does NOT appear here (only the installed copy, by its manifest name).
- [ ] **Auto-disable + remove:** enable one of the installed plugin's groups via Manage Plugins, then Uninstall Plugin… → pick it → confirm. Its group hot-unloads (pane/menu/status-icon gone), the `installed_plugins/<name>/` dir is deleted, and it disappears from both Manage Plugins and Uninstall lists.
- [ ] **Flags cleared on restart:** uninstall an enabled plugin, restart → it does not auto-load (enabled flags were cleared).
- [ ] **Bundled is safe:** the bundled magnet (from `default_plugins/`) is never in the Uninstall list and stays usable via Manage Plugins.

- [ ] **Step 4: Update project memory**

Append to `C:/Users/Info/.claude/projects/C--Users-Info-PycharmProjects-pixi-microdrop/memory/project_plugin_hot_load_unload.md`: the uninstall capability — `Tools → Uninstall Plugin…` (`UninstallPluginAction` + `UninstallPluginModel`), `installer.uninstall_plugin(task, manager, name)` (auto-disable → purge modules → `deregister_plugin` clears flags → `rmtree`), and that `PluginGroupManager` now tracks `manifest_name`/`manifest_label`/`source_dir` per group so `installed_plugins()` lists only user-installed (under `installed_plugins/`) plugins while bundled `default_plugins/` ones are disable-only. No repo commit required (memory lives outside the repo).

---

## Self-Review

**Spec coverage:**
- §Component 1 (source tracking + installed_plugins/installed_plugin/deregister_plugin) → Task 1. ✓
- §Component 2 (`uninstall_plugin`) → Task 2. ✓
- §Component 3 (uninstall dialog) → Task 3. ✓
- §Component 4 (`UninstallPluginAction` + menu wiring) → Task 4. ✓
- §Verification (manual) → Task 5. ✓

**Type consistency:** `installed_plugins()` returns `(name, label, source_dir, [group_names])` (Task 1) — consumed identically by `installer.uninstall_plugin` (Task 2, unpacks 4-tuple), `UninstallPluginModel` (Task 3, reads `name`/`label`), and `UninstallPluginAction` (Task 4, builds the label map). `installed_plugin`/`deregister_plugin` (Task 1) called by `uninstall_plugin` (Task 2). `register_manifest(manifest, source_dir="")` (Task 1) matches the `register_manifest(manifest, str(target))` call (Task 2). `uninstall_plugin(task, manager, manifest_name)` (Task 2) matches the call in `UninstallPluginAction` (Task 4). `UninstallPluginModel(installed)`/`selected` (Task 3) matches Task 4's use.

**Placeholder scan:** none — every code step has full code; every command states expected output.
