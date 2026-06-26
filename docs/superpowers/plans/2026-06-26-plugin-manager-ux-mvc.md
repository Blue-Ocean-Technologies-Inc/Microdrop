# Manage Plugins UX overhaul (TraitsUI MVC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three plugin Tools actions with one **Manage Plugins** window — per-plugin rows (version + Enable/optional-group checkboxes), a richer pre-install preview, and a "please wait" loading state — built as a clean TraitsUI Model/View/Controller.

**Architecture:** A Qt-free `HasTraits` **model** (row state + `desired_state`/`apply`/`do_install`/`do_uninstall`/`preview`), a TraitsUI **`Controller`** (dialog + threading + relaunch glue), and a TraitsUI **`View`**. The manifest marks groups `optional`; "Enable" enables core groups + auto-checks optionals (each separately toggleable). Install/uninstall run on a worker thread behind a modal progress dialog and end in a relaunch; Apply is a live hot-load.

**Tech Stack:** Traits/TraitsUI, Pyface (`Controller`, `ProgressDialog`, `GUI.invoke_later`), the existing `plugin_management` package + `IPluginGroupManager` service, `package_installer`, `relaunch`.

## Global Constraints

- **MVC:** model is Qt-free `HasTraits` (state + business logic, no dialogs/threading); the TraitsUI `Controller` owns dialogs/threading/relaunch; the `View` is layout only. Model is mutated only on the GUI thread (worker→GUI hand-off via `pyface.api.GUI.invoke_later`).
- **Enable model:** `Enable` on ⇒ core groups on + each optional group per its checkbox; `Enable` off ⇒ all the plugin's groups off. Checking `Enable` auto-checks every optional (`@observe("enabled")`).
- **Apply = live hot-load (no relaunch). Install / Uninstall = relaunch** (`relaunch.relaunch_app`).
- **Manifest fields:** `PluginGroupSpec.optional: bool = False`, `PluginGroupSpec.toggle_label: str = ""` (short checkbox label; falls back to `label`). Defaults preserve every existing manifest.
- **Preview** is read from the `.conda`: name/version/`depends` from `info/index.json`; groups/plugin-classes from the bundled `microdrop_plugin.toml` (degrade to name/version/deps if the manifest can't be read).
- **Dialogs only** via `microdrop_application.dialogs.pyface_wrapper`. f-strings only. **No pytest** — verify via `py_compile` + `pixi run` import/headless smokes + manual GUI.
- Work from `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src` (submodule, branch `feat/plugin_management`). Commit messages end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File structure

**New:** `plugin_management/manager_model.py`, `plugin_management/manager_view.py`,
`plugin_management/manager_controller.py`, `microdrop_utils/threaded_progress.py`.
**Edit:** `plugin_management/manifest.py`, `plugin_management/group_manager.py`,
`plugin_management/package_installer.py`, `plugin_management/menus.py`,
`plugin_management/plugin.py`, `peripheral_controller/microdrop_plugin.toml`.
**Remove:** `plugin_management/manage_dialog.py`, `plugin_management/uninstall_dialog.py`.

---

### Task 1: Manifest + group schema — `optional`, `toggle_label`, version

**Files:**
- Modify: `plugin_management/manifest.py`, `plugin_management/group_manager.py`, `peripheral_controller/microdrop_plugin.toml`

**Interfaces:**
- Produces: `PluginGroupSpec.optional: bool`, `PluginGroupSpec.toggle_label: str`; `PluginGroup` traits `optional` (Bool), `toggle_label` (Str), `manifest_version` (Str), set by `_add_manifest_groups`.

- [ ] **Step 1: Add the fields to `PluginGroupSpec` + `manifest_from_dict`**

In `plugin_management/manifest.py`, add to `PluginGroupSpec`:
```python
@dataclass
class PluginGroupSpec:
    name: str
    label: str
    plugins: List[str]                       # dotted "module:Class" specs
    enabled_key: str
    post_enable_publish_topic: str = ""
    optional: bool = False
    toggle_label: str = ""
```
In `manifest_from_dict`, build each group with the two new fields (read with defaults so existing manifests are unaffected):
```python
        groups.append(PluginGroupSpec(
            name=gname,
            label=g.get("label") or gname,
            plugins=list(plugins),
            enabled_key=enabled_key,
            post_enable_publish_topic=g.get("post_enable_publish_topic", "") or "",
            optional=bool(g.get("optional", False)),
            toggle_label=str(g.get("toggle_label", "") or ""),
        ))
```

- [ ] **Step 2: Add matching `PluginGroup` traits + thread them through**

In `plugin_management/group_manager.py`, add to the `PluginGroup` HasTraits (next to `manifest_name`/`manifest_label`):
```python
    #: True if this group is independently toggleable (its own checkbox in the
    #: Manage Plugins window); core groups (optional=False) load with "Enable".
    optional = Bool(False)
    #: Short label for the optional checkbox column (falls back to label).
    toggle_label = Str()
    #: Owning manifest's version (shown next to the plugin name).
    manifest_version = Str()
```
and in `_add_manifest_groups`, set them on each `PluginGroup(...)`:
```python
                optional=spec.optional,
                toggle_label=spec.toggle_label or spec.label,
                manifest_version=manifest.version,
```
(`Bool`/`Str` are already imported from `traits.api` in this module.)

- [ ] **Step 3: Mark magnet's backend optional**

In `peripheral_controller/microdrop_plugin.toml`, add to the `magnet_backend` group table:
```toml
optional = true
toggle_label = "Backend"
```
(Leave `magnet_ui` as-is — it's a core group.)

- [ ] **Step 4: Verify (parse + discovery)**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig; ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdhome_\")
from plugin_management.group_manager import PluginGroupManager
m = PluginGroupManager()
g = {n: (grp.optional, grp.toggle_label, grp.manifest_version) for n, grp in m.groups.items()}
print(\"magnet_backend:\", g.get(\"magnet_backend\"))
print(\"magnet_ui:\", g.get(\"magnet_ui\"))
'"
```
Expected: `magnet_backend: (True, 'Backend', '1.0.0')`; `magnet_ui: (False, 'Magnet UI (dock pane, status icon, protocol column)', '1.0.0')`.

- [ ] **Step 5: Commit**

```bash
git add plugin_management/manifest.py plugin_management/group_manager.py peripheral_controller/microdrop_plugin.toml
git commit -m "Manifest: optional/toggle_label group fields + manifest_version on PluginGroup

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `read_conda_preview` — read name/version/deps + manifest from a `.conda`

**Files:**
- Modify: `plugin_management/package_installer.py`

**Interfaces:**
- Produces: `@dataclass PluginPreview(name: str, version: str, depends: list, manifest)`; `read_conda_preview(conda_path) -> PluginPreview`.

- [ ] **Step 1: Add the preview reader**

In `plugin_management/package_installer.py`, after `package_name_from_conda`, add:
```python
@dataclass
class PluginPreview:
    name: str
    version: str
    depends: list          # conda dependency match-specs (what pixi will install)
    manifest: object = None  # PluginManifest | None (groups + plugin classes)


def _zst_tar(z, member):
    """Open a .conda zip member (a *.tar.zst) as a tarfile."""
    return tarfile.open(fileobj=io.BytesIO(zstd.decompress(z.read(member))))


def _conda_manifest(z):
    """Best-effort: parse the bundled microdrop_plugin.toml from the pkg payload.
    Returns a PluginManifest or None (preview degrades gracefully)."""
    import tomllib
    from plugin_management.manifest import manifest_from_dict, ManifestError
    try:
        pkg_member = next(n for n in z.namelist()
                          if n.startswith("pkg-") and n.endswith(".tar.zst"))
        with _zst_tar(z, pkg_member) as tar:
            toml_name = next((m for m in tar.getnames()
                              if m.rsplit("/", 1)[-1] == "microdrop_plugin.toml"), None)
            if toml_name is None:
                return None
            data = tomllib.loads(tar.extractfile(toml_name).read().decode("utf-8"))
            return manifest_from_dict(data)
    except (StopIteration, OSError, ValueError, ManifestError) as e:
        logger.debug(f"could not read bundled manifest: {e}")
        return None


def read_conda_preview(conda_path) -> PluginPreview:
    """Read a .conda's package name/version, conda dependencies, and (best-effort)
    its plugin manifest — for the pre-install consent dialog. Raises InstallError
    if the archive's index can't be read."""
    p = Path(conda_path)
    try:
        with zipfile.ZipFile(p) as z:
            info_member = next(n for n in z.namelist()
                               if n.startswith("info-") and n.endswith(".tar.zst"))
            with _zst_tar(z, info_member) as tar:
                idx = json.loads(tar.extractfile("info/index.json").read().decode("utf-8"))
            return PluginPreview(
                name=idx["name"],
                version=str(idx.get("version", "")),
                depends=list(idx.get("depends", [])),
                manifest=_conda_manifest(z),
            )
    except (StopIteration, KeyError, OSError, ValueError) as e:
        raise InstallError(f"could not read plugin info from {p.name}: {e}") from e
```

- [ ] **Step 2: Build the demo `.conda` (smoke fixture)**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python examples/build_plugin_conda.py 2>&1 | tail -2 && ls dist_plugins -R 2>/dev/null | grep -i '\.conda'"
```
Expected: a `scipy_analysis-0.1.0-*.conda` is listed (under `dist_plugins/`, possibly a `noarch/` subdir).

- [ ] **Step 3: Preview smoke against the demo `.conda`**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
import glob
from plugin_management.package_installer import read_conda_preview
conda = glob.glob(\"dist_plugins/**/scipy_analysis-*.conda\", recursive=True)[0]
pv = read_conda_preview(conda)
print(\"name/version:\", pv.name, pv.version)
print(\"depends has scipy:\", any(d.split()[0]==\"scipy\" for d in pv.depends))
print(\"manifest groups:\", None if pv.manifest is None else [g.name for g in pv.manifest.groups])
'"
```
Expected: `name/version: scipy_analysis 0.1.0`; `depends has scipy: True`; `manifest groups: ['scipy_analysis']`.

- [ ] **Step 4: Commit**

```bash
git add plugin_management/package_installer.py
git commit -m "package_installer: read_conda_preview (name/version/deps + bundled manifest)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `threaded_progress.run_with_wait` — worker thread + "please wait" modal

**Files:**
- Create: `microdrop_utils/threaded_progress.py`

**Interfaces:**
- Produces: `run_with_wait(work, *, title, message, on_success, on_error) -> None` — runs `work()` on a worker thread behind a modal indeterminate progress dialog; calls `on_success(result)` / `on_error(exc)` on the GUI thread.

- [ ] **Step 1: Create the helper**

`microdrop_utils/threaded_progress.py`:
```python
"""Run a slow blocking callable on a worker thread behind a modal, indeterminate
"please wait" dialog, marshalling the result back to the GUI thread.

Qt is allowed here (this is a UI helper, not a model). The worker callable must
NOT touch Qt or Traits models — only the on_success/on_error callbacks (which run
on the GUI thread) may."""
import threading

from pyface.api import GUI, ProgressDialog

from logger.logger_service import get_logger

logger = get_logger(__name__)


def run_with_wait(work, *, title="Please wait", message="Working…",
                  on_success=None, on_error=None):
    """Show an indeterminate ProgressDialog, run ``work()`` on a worker thread,
    then (on the GUI thread) close the dialog and call ``on_success(result)`` or
    ``on_error(exc)``. Non-cancellable."""
    dialog = ProgressDialog(title=title, message=message, can_cancel=False)
    dialog.open()
    dialog.change_message(message)

    def _finish(success, payload):
        try:
            dialog.close()
        except Exception:
            pass
        if success:
            if on_success is not None:
                on_success(payload)
        else:
            logger.exception("threaded work failed", exc_info=payload)
            if on_error is not None:
                on_error(payload)

    def _worker():
        try:
            result = work()
        except Exception as e:                       # marshal failure to GUI thread
            GUI.invoke_later(_finish, False, e)
        else:
            GUI.invoke_later(_finish, True, result)

    threading.Thread(target=_worker, daemon=True).start()
```

- [ ] **Step 2: Compile + import smoke**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -m py_compile microdrop_utils/threaded_progress.py && python -c 'from microdrop_utils.threaded_progress import run_with_wait; print(\"run_with_wait import OK\")'"
```
Expected: no compile output; `run_with_wait import OK`. (Full threaded behaviour is exercised in the manual GUI pass — a headless event loop can't drive `ProgressDialog` + `GUI.invoke_later` deterministically.)

- [ ] **Step 3: Commit**

```bash
git add microdrop_utils/threaded_progress.py
git commit -m "Add threaded_progress.run_with_wait: worker thread behind a please-wait modal

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Model — `manager_model.py`

**Files:**
- Create: `plugin_management/manager_model.py`

**Interfaces:**
- Consumes: the `IPluginGroupManager` service (`groups`, `apply`, `installed_plugins`); Task 2 `read_conda_preview`; `package_installer.install_conda_file`/`uninstall_package`.
- Produces: `OptionalGroupToggle`, `PluginRow`, `PluginManagerModel` with `rows`, `refresh()`, `desired_state()`, `apply(task)`, `installed_rows()`, `preview(path)`, `do_install(path)`, `do_uninstall(name)`.

- [ ] **Step 1: Create the model**

`plugin_management/manager_model.py`:
```python
"""Qt-free model for the Manage Plugins window: per-plugin row state + the
enable/disable/install/uninstall business logic. No Qt, no dialogs, no threading
(the controller owns those). Mutated only on the GUI thread."""
from traits.api import Any, Bool, HasTraits, Instance, List, Str, observe

from plugin_management import package_installer
from logger.logger_service import get_logger

logger = get_logger(__name__)


class OptionalGroupToggle(HasTraits):
    """One optional group's checkbox (e.g. magnet 'Backend')."""
    group_name = Str()
    toggle_label = Str()
    on = Bool(False)


class PluginRow(HasTraits):
    """One installed plugin (manifest) — its enable state + optional toggles."""
    manifest_name = Str()
    label = Str()
    version = Str()
    bundled = Bool(False)                       # app's own dist -> not uninstallable
    core_groups = List(Str)                     # enabled whenever 'enabled' is on
    optionals = List(Instance(OptionalGroupToggle))
    enabled = Bool(False)

    @observe("enabled")
    def _auto_check_optionals(self, event):
        if event.new:                            # 'Enable' auto-checks every optional
            for opt in self.optionals:
                opt.on = True

    def desired(self):
        """{group_name: bool} for this plugin's groups."""
        out = {g: self.enabled for g in self.core_groups}
        for opt in self.optionals:
            out[opt.group_name] = self.enabled and opt.on
        return out


class PluginManagerModel(HasTraits):
    """Rows for every installed plugin + the operations the controller invokes."""
    manager = Any()                             # IPluginGroupManager
    rows = List(Instance(PluginRow))

    def _rows_default(self):
        return self._build_rows()

    def refresh(self):
        self.rows = self._build_rows()

    def _build_rows(self):
        by_manifest = {}
        order = []
        for group in self.manager.groups.values():
            key = group.manifest_name
            if key not in by_manifest:
                by_manifest[key] = []
                order.append(key)
            by_manifest[key].append(group)
        installed = {e[0] for e in self.manager.installed_plugins()}
        rows = []
        for key in order:
            groups = by_manifest[key]
            core = [g.name for g in groups if not g.optional]
            optionals = [OptionalGroupToggle(group_name=g.name,
                                             toggle_label=g.toggle_label or g.name,
                                             on=g.loaded)
                         for g in groups if g.optional]
            any_core_loaded = any(g.loaded for g in groups if not g.optional)
            first = groups[0]
            rows.append(PluginRow(
                manifest_name=key,
                label=first.manifest_label or key,
                version=first.manifest_version,
                bundled=key not in installed,
                core_groups=core,
                optionals=optionals,
                enabled=any_core_loaded or any(o.on for o in optionals),
            ))
        return rows

    def desired_state(self):
        """{group_name: bool} across every plugin (for manager.apply)."""
        desired = {}
        for row in self.rows:
            desired.update(row.desired())
        return desired

    def apply(self, task):
        """Commit enable/disable as a live hot-load (no relaunch)."""
        self.manager.apply(task, self.desired_state())

    def installed_rows(self):
        """Rows the user can uninstall (non-bundled)."""
        return [r for r in self.rows if not r.bundled]

    # --- operations the controller runs on a worker thread -------------
    def preview(self, conda_path):
        return package_installer.read_conda_preview(conda_path)

    def do_install(self, conda_path):
        return package_installer.install_conda_file(conda_path)

    def do_uninstall(self, name):
        package_installer.uninstall_package(name)
```

Note: `do_install` calls `install_conda_file` WITHOUT a `confirm` callback — consent is gathered by the controller's preview dialog BEFORE the threaded call, so the worker never blocks on a dialog.

- [ ] **Step 2: Headless model smoke (the enable-model logic)**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig; ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdhome_\")
from plugin_management.group_manager import PluginGroupManager
from plugin_management.manager_model import PluginManagerModel
m = PluginManagerModel(manager=PluginGroupManager())
row = next(r for r in m.rows if r.manifest_name == \"magnet_peripherals\")
print(\"magnet bundled:\", row.bundled, \"version:\", row.version, \"optionals:\", [o.toggle_label for o in row.optionals])
row.enabled = True                     # Enable -> ui core + backend optional auto-checked
print(\"enable-all desired:\", row.desired())
row.optionals[0].on = False            # uncheck Backend -> UI only
print(\"ui-only desired:\", row.desired())
row.enabled = False                    # disable -> all off
print(\"disabled desired:\", row.desired())
'"
```
Expected: `magnet bundled: True ... optionals: ['Backend']`; `enable-all desired: {'magnet_ui': True, 'magnet_backend': True}`; `ui-only desired: {'magnet_ui': True, 'magnet_backend': False}`; `disabled desired: {'magnet_ui': False, 'magnet_backend': False}`.

- [ ] **Step 3: Commit**

```bash
git add plugin_management/manager_model.py
git commit -m "Add Manage Plugins model: row state + enable/install/uninstall business logic

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: View — `manager_view.py`

**Files:**
- Create: `plugin_management/manager_view.py`

**Interfaces:**
- Consumes: `PluginRow`/`OptionalGroupToggle`/`PluginManagerModel` (Task 4). The action names `install_plugin`, `uninstall_plugin`, `apply_changes`, `close` are handled by the controller (Task 6).
- Produces: `manager_view() -> traitsui.View`; `PluginRow.traits_view` / `OptionalGroupToggle.traits_view`.

- [ ] **Step 1: Per-item views + the window view**

`plugin_management/manager_view.py`:
```python
"""TraitsUI layout for the Manage Plugins window. Pure presentation — the
Controller (manager_controller) supplies the action handlers; the model
(manager_model) supplies the state."""
from traitsui.api import (Action, HGroup, Item, Label, ListEditor, Spring,
                          UReadonly, VGroup, View)

# Action buttons -> Controller methods of the same name.
install_action = Action(name="Install Plugin…", action="install_plugin")
uninstall_action = Action(name="Uninstall…", action="uninstall_plugin",
                          enabled_when="len(handler.model.installed_rows()) > 0")
apply_action = Action(name="Apply", action="apply_changes")
close_action = Action(name="Close", action="close")


def optional_toggle_view():
    return View(HGroup(Item("on", show_label=False), UReadonly("toggle_label")))


def plugin_row_view():
    return View(HGroup(
        UReadonly("label", width=-240),
        UReadonly("version", width=-70),
        Spring(),
        Item("enabled", label="Enable"),
        # ListEditor(style="custom") renders each optional with its default view
        # (OptionalGroupToggle.traits_view, attached at the bottom of this module).
        Item("optionals", show_label=False, style="custom",
             editor=ListEditor(style="custom")),
    ))


def manager_view():
    return View(
        VGroup(
            Label("Installed plugins:"),
            # each PluginRow renders with its default view (PluginRow.traits_view).
            Item("rows", show_label=False, style="custom",
                 editor=ListEditor(style="custom")),
            show_border=True,
        ),
        buttons=[install_action, uninstall_action, apply_action, close_action],
        title="Manage Plugins",
        kind="livemodal",
        resizable=True,
        width=560,
        height=360,
    )


# Attach the per-item default views to the model classes from the VIEW module, so
# all layout lives here (the model stays view-free) while ListEditor(style="custom")
# above picks them up as each item's default view.
from plugin_management.manager_model import OptionalGroupToggle, PluginRow  # noqa: E402

PluginRow.traits_view = plugin_row_view()
OptionalGroupToggle.traits_view = optional_toggle_view()
```

- [ ] **Step 2: Compile + view-construction smoke (offscreen)**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -m py_compile plugin_management/manager_view.py && python -c '
from plugin_management.manager_view import manager_view, plugin_row_view, optional_toggle_view
print(\"views build:\", bool(manager_view()), bool(plugin_row_view()), bool(optional_toggle_view()))
'"
```
Expected: no compile output; `views build: True True True`.

- [ ] **Step 3: Commit**

```bash
git add plugin_management/manager_view.py
git commit -m "Add Manage Plugins view: per-plugin rows + Enable/optional checkboxes + actions

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Controller — `manager_controller.py`

**Files:**
- Create: `plugin_management/manager_controller.py`

**Interfaces:**
- Consumes: `PluginManagerModel` (Task 4), `manager_view` (Task 5), `threaded_progress.run_with_wait` (Task 3), `package_installer` (`InstallCancelled`), `relaunch.relaunch_app`, the pyface_wrapper dialogs.
- Produces: `PluginManagerController(Controller)` with `model`, `task`, and the action handlers `install_plugin`/`uninstall_plugin`/`apply_changes`/`close`; `open_manager(task)` convenience.

- [ ] **Step 1: Create the controller**

`plugin_management/manager_controller.py`:
```python
"""TraitsUI Controller for the Manage Plugins window: wires the view's actions to
the model and owns the UI glue (dialogs, worker-thread + please-wait modal,
relaunch). The model holds the state/business logic; this holds the flow."""
from traitsui.api import Controller

from microdrop_utils.threaded_progress import run_with_wait
from plugin_management import package_installer
from plugin_management.manager_view import manager_view
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _esc(s):
    from microdrop_application.dialogs.pyface_wrapper import escape_html_multiline
    return escape_html_multiline(str(s))


class PluginManagerController(Controller):
    """Pairs PluginManagerModel with the Manage Plugins view."""

    def __init__(self, model, task, **traits):
        super().__init__(model=model, **traits)
        self.task = task

    def trait_view(self, name=None, view_element=None):
        return manager_view()

    # --- Apply: live hot-load, no relaunch ---------------------------
    def apply_changes(self, info):
        from microdrop_application.dialogs.pyface_wrapper import error as error_dialog
        try:
            self.model.apply(self.task)
            self.model.refresh()
        except Exception as e:
            logger.exception("apply enable/disable failed")
            error_dialog(parent=None, title="Apply failed", message=str(e))

    def close(self, info, is_ok=None):
        info.ui.dispose()
        return True

    # --- Install: pick .conda -> preview -> threaded install -> relaunch
    def install_plugin(self, info):
        from microdrop_application.dialogs.pyface_wrapper import (
            file_dialog, confirm, error as error_dialog, YES)
        path = file_dialog(parent=None, action="open",
                           wildcard="MicroDrop plugin package (*.conda)|*.conda")
        if not path:
            return
        try:
            preview = self.model.preview(path)
        except Exception as e:
            error_dialog(parent=None, title="Install failed", message=str(e))
            return
        if confirm(parent=None, title="Install Plugin?",
                   message=self._consent_html(preview), cancel=False) != YES:
            return
        self._run(lambda: self.model.do_install(path),
                  title="Installing plugin",
                  message=f"Installing {preview.name}…",
                  done=lambda r: self._after_change(
                      f"Installed <b>{_esc(preview.name)}</b>."))

    # --- Uninstall: pick installed -> confirm -> threaded remove -> relaunch
    def uninstall_plugin(self, info):
        from microdrop_application.dialogs.pyface_wrapper import (
            confirm, information, error as error_dialog, YES)
        rows = self.model.installed_rows()
        if not rows:
            information(parent=None, title="Uninstall Plugin",
                       message="No installed plugin packages to uninstall.")
            return
        name = self._pick_installed(rows)
        if name is None:
            return
        label = {r.manifest_name: r.label for r in rows}.get(name, name)
        if confirm(parent=None, title="Uninstall Plugin?",
                   message=f"Uninstall <b>{_esc(label)}</b>? This removes its "
                           f"package from the environment.", cancel=False) != YES:
            return
        self._run(lambda: self.model.do_uninstall(name),
                  title="Uninstalling plugin", message=f"Removing {label}…",
                  done=lambda r: self._after_change(
                      f"Uninstalled <b>{_esc(label)}</b>."))

    # --- helpers -----------------------------------------------------
    def _run(self, work, *, title, message, done):
        from microdrop_application.dialogs.pyface_wrapper import error as error_dialog
        run_with_wait(
            work, title=title, message=message,
            on_success=done,
            on_error=lambda e: error_dialog(parent=None, title=title, message=str(e)),
        )

    def _after_change(self, msg_html):
        from microdrop_application.dialogs.pyface_wrapper import confirm, information, YES
        if confirm(parent=None, title="Relaunch required",
                   message=f"{msg_html}<br><br>Relaunch MicroDrop now to apply?",
                   cancel=False) == YES:
            from plugin_management.relaunch import relaunch_app
            relaunch_app(self.task.window.application)
        else:
            information(parent=None, title="Relaunch later",
                        message="The change takes effect the next time you launch "
                                "MicroDrop.")

    def _consent_html(self, preview):
        deps = ", ".join(_esc(d) for d in preview.depends) or "none"
        groups = "(manifest unreadable)"
        if preview.manifest is not None:
            rows = []
            for g in preview.manifest.groups:
                plugins = "<br>".join(f"&nbsp;&nbsp;{_esc(p)}" for p in g.plugins)
                rows.append(f"<b>{_esc(g.label)}</b><br>{plugins}")
            groups = "<br>".join(rows)
        return (
            f"<b>{_esc(preview.name)}</b> (v{_esc(preview.version)})<br><br>"
            f"Dependencies pixi will install: {deps}<br><br>"
            f"Plugin groups provided:<br>{groups}<br><br>"
            f"<b>Warning:</b> installing runs third-party code that has not been "
            f"verified. Only install plugins you trust.<br><br>Install this plugin?"
        )

    def _pick_installed(self, rows):
        """Small single-select picker; returns the chosen manifest_name or None."""
        from traits.api import Enum, HasTraits
        from traitsui.api import EnumEditor, Item, View
        choices = {f"{r.label}  (v{r.version})": r.manifest_name for r in rows}

        class _Pick(HasTraits):
            choice = Enum(list(choices))
        picker = _Pick()
        ui = picker.edit_traits(view=View(
            Item("choice", editor=EnumEditor(values=list(choices)),
                 label="Plugin"),
            buttons=["OK", "Cancel"], kind="livemodal",
            title="Uninstall which plugin?"))
        return choices[picker.choice] if ui.result else None
```

(Uninstall is relaunch-based — `package_installer.uninstall_package` is `pixi remove` + channel cleanup; the package leaves the env on the relaunch, so the controller need not pre-disable the loaded group.)

- [ ] **Step 2: Compile + import smoke**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -m py_compile plugin_management/manager_controller.py && python -c '
from plugin_management.manager_controller import PluginManagerController
print(\"controller import OK; handlers:\", all(hasattr(PluginManagerController, h) for h in (\"install_plugin\",\"uninstall_plugin\",\"apply_changes\",\"close\")))
'"
```
Expected: no compile output; `controller import OK; handlers: True`.

- [ ] **Step 3: Commit**

```bash
git add plugin_management/manager_controller.py
git commit -m "Add Manage Plugins controller: install/uninstall/apply glue (threaded + relaunch)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Wire one menu action; remove the old dialogs/actions

**Files:**
- Modify: `plugin_management/menus.py`, `plugin_management/plugin.py`
- Remove: `plugin_management/manage_dialog.py`, `plugin_management/uninstall_dialog.py`

**Interfaces:**
- Consumes: `PluginManagerController` (Task 6), `PluginManagerModel` (Task 4).
- Produces: a single `ManagePluginsAction` opening the MVC window; `InstallPluginAction`/`UninstallPluginAction` removed.

- [ ] **Step 1: Collapse `menus.py` to one action**

Replace the entire body of `plugin_management/menus.py` with:
```python
"""Tools-menu action for plugin management — a single Manage Plugins window.

Contributed to the microdrop task's MenuBar/Tools by PluginManagementPlugin via
TASK_EXTENSIONS. Heavy imports are deferred into ``perform``."""
from pyface.tasks.action.api import TaskAction

from logger.logger_service import get_logger

logger = get_logger(__name__)


class ManagePluginsAction(TaskAction):
    """Open the Manage Plugins window (install / uninstall / enable-disable)."""

    id = "manage_plugins_action"
    name = "&Manage Plugins…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Manage Plugins: no task available")
            return
        from plugin_management.i_plugin_group_manager import IPluginGroupManager
        from plugin_management.manager_model import PluginManagerModel
        from plugin_management.manager_controller import PluginManagerController
        from plugin_management.manager_view import manager_view

        manager = task.window.application.get_service(IPluginGroupManager)
        if manager is None:
            logger.error("Manage Plugins: PluginGroupManager service not found")
            return
        model = PluginManagerModel(manager=manager)
        controller = PluginManagerController(model=model, task=task)
        # Controller edits its `model` (the view's Items resolve against the model)
        # with the controller as the handler for the action buttons.
        controller.edit_traits(view=manager_view(), kind="livemodal")
```

- [ ] **Step 2: Contribute only the one action in `plugin.py`**

In `plugin_management/plugin.py`, find the `SGroup(...)` that builds the Tools actions (it currently lists `InstallPluginAction()`, `UninstallPluginAction()`, `ManagePluginsAction()`). Replace its imports + body so it contributes ONLY `ManagePluginsAction()`:
```python
        from plugin_management.menus import ManagePluginsAction
        return SGroup(ManagePluginsAction(), id="plugin_management_actions")
```
(Delete the now-unused `InstallPluginAction`/`UninstallPluginAction` imports there.)

- [ ] **Step 3: Remove the superseded dialog modules**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src
git rm plugin_management/manage_dialog.py plugin_management/uninstall_dialog.py
```

- [ ] **Step 4: Verify nothing dangles + the action loads**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src && grep -rn "manage_dialog\|uninstall_dialog\|InstallPluginAction\|UninstallPluginAction" --include=*.py . || echo "(no stale references)"
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -m py_compile plugin_management/menus.py plugin_management/plugin.py && python -c 'import plugin_management.menus as mn, plugin_management.plugin; print(\"manage action:\", mn.ManagePluginsAction().name)'"
```
Expected: `(no stale references)`; no compile output; `manage action: &Manage Plugins…`.

- [ ] **Step 5: Commit**

```bash
git add plugin_management/menus.py plugin_management/plugin.py
git commit -m "Unify plugin Tools menu into one Manage Plugins window; remove old dialogs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: End-to-end verification (headless + manual GUI)

**Files:** none.

- [ ] **Step 1: Headless wiring smoke**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig; ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdhome_\")
from plugin_management.group_manager import PluginGroupManager
from plugin_management.manager_model import PluginManagerModel
from plugin_management.manager_controller import PluginManagerController
import plugin_management.menus, plugin_management.manager_view
m = PluginManagerModel(manager=PluginGroupManager())
print(\"rows:\", [(r.label, r.version, [o.toggle_label for o in r.optionals]) for r in m.rows])
print(\"ALL WIRING OK\")
'"
```
Expected: magnet row present with version `1.0.0` and `['Backend']`; `ALL WIRING OK`.

- [ ] **Step 2: Manual GUI** (Redis up; demo `.conda` built via `pixi run python examples/build_plugin_conda.py`; tick each)

- [ ] **Tools → Manage Plugins…** opens one window listing **Magnet  v1.0.0** with **Enable** + **Backend** checkboxes.
- [ ] Check **Enable** → **Backend** auto-checks. Uncheck **Backend** → **Apply** → only the magnet UI loads (dock pane/column, no backend search). Re-check + Apply → backend monitoring starts. Uncheck Enable + Apply → magnet fully unloads.
- [ ] **Install Plugin…** → pick the demo `.conda` → the **preview dialog** shows name, version, **scipy** in dependencies, and the group/plugin classes → accept → a **"Installing… please wait"** modal shows during `pixi add` → on success, **Relaunch?** → Yes relaunches; after relaunch the plugin appears and enables.
- [ ] **Uninstall…** → pick the installed plugin → confirm → wait modal → relaunch → it's gone; magnet still works.

- [ ] **Step 3: Record the outcome** in the task report (what worked; any view tweaks wanted — the layout is expected to be iterated). No code commit.

---

## Self-review notes for the executor

- **MVC boundaries:** the model (`manager_model.py`) imports no Qt/dialogs/threading; the controller owns all of that; the view is layout only (item views are passed explicitly so the model stays view-free).
- **Consent before threading:** the install consent dialog runs on the GUI thread BEFORE `run_with_wait`, so the worker thread never blocks on a dialog.
- **The view is the most likely thing to iterate** in the manual GUI pass (nested `ListEditor`s; the user expects to tweak layout) — keep its logic in `manager_view.py` only.
