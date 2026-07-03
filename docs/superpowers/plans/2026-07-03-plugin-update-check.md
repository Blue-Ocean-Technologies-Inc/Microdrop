# Plugin Update Check on Launch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On app launch, silently diff the plugins channel against the previous launch's cached copy and the installed set; when updates or new plugins exist, show an info dialog with an Update All button that installs updates and then offers the standard relaunch popup.

**Architecture:** A run-once `application:application_initialized` observer in `PluginManagementPlugin` spawns a daemon thread: read old cache (`read_cached_index`) → fetch fresh (`search_channel`, which rewrites the cache) → diff via a pure function (`compute_update_report`) against `installed_plugin_dists()` → if non-empty, `GUI.invoke_later` opens a TraitsUI dialog (MVC trio mirroring `browse_*`). Update All uses the existing `run_with_wait` + `install_from_channel` + `confirm_and_relaunch` machinery.

**Tech Stack:** Traits/TraitsUI, `importlib.metadata`, existing `plugin_management` helpers.

**Spec:** `docs/superpowers/specs/2026-07-03-plugin-update-check-design.md`

## Global Constraints

- f-strings everywhere, including log messages; logging via `from logger.logger_service import get_logger; logger = get_logger(__name__)`.
- Threading rule: model traits are mutated on the GUI thread only; worker callables return data. Qt-free model files (no Qt / pyface imports in `update_model.py`; use stdlib `html.escape`, not `pyface_wrapper.escape_html_multiline`).
- Testing is MANUAL (project preference): implementers WRITE test files but verify via `python -c "import ast; ast.parse(...)"` + the logic smokes specified per task — never run pytest, never launch the app. Python smokes run via `pixi run python -c "..."` from the `microdrop-py` directory (one level above `src`), with `import sys; sys.path.insert(0, 'src')` if needed — check `examples` conventions; plain `python` works if the pixi env is active.
- Repo: `microdrop-py/src`, branch `feat/plugin-update-check` (already created).
- `git add` only the files your task touches; never `git add -A` / `.`.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: `installed_plugin_dists()` helper

**Files:**
- Modify: `plugin_management/package_installer.py`
- Test: `plugin_management/tests/test_package_installer.py` (append)

**Interfaces:**
- Consumes: `ENTRY_POINT_GROUP` from `plugin_management/consts.py` (`"microdrop.plugins"`).
- Produces: `installed_plugin_dists() -> dict[str, str]` — `{distribution name: version}` for installed MicroDrop plugin packages. Task 4 calls it.

- [ ] **Step 1: Add the helper**

In `plugin_management/package_installer.py`: add `import importlib.metadata` to the stdlib imports, add `ENTRY_POINT_GROUP` to the existing `from .consts import ...` line, and append after `read_cached_index()`:

```python
def installed_plugin_dists() -> dict[str, str]:
    """{distribution name: version} for every installed distribution that
    exposes a ``microdrop.plugins`` entry point — i.e. every installed
    MicroDrop plugin package. Dist names match channel package names
    (e.g. heater-microdrop-plugin)."""
    dists = {}
    for dist in importlib.metadata.distributions():
        if not any(ep.group == ENTRY_POINT_GROUP for ep in dist.entry_points):
            continue
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            dists[name] = dist.version
    return dists
```

- [ ] **Step 2: Append the test**

Append to `plugin_management/tests/test_package_installer.py`:

```python
def test_installed_plugin_dists_shape():
    """Every entry maps a non-empty dist name to a non-empty version string;
    only distributions advertising the microdrop.plugins entry point appear."""
    dists = package_installer.installed_plugin_dists()
    assert isinstance(dists, dict)
    for name, version in dists.items():
        assert name and isinstance(name, str)
        assert version and isinstance(version, str)
```

(Match the existing import style at the top of that test file — it already imports `package_installer`.)

- [ ] **Step 3: Verify**

Run from `microdrop-py`: `pixi run python -c "from plugin_management.package_installer import installed_plugin_dists; d = installed_plugin_dists(); print(sorted(d.items()))"` (cwd `src`, or with `sys.path` including `src`).
Expected: prints a list that includes `('heater-microdrop-plugin', '1.0.1')` and `('magnet-microdrop-plugin', '1.0.1')` (versions may differ; the two names must appear since both are installed in the dev env). Also `python -c "import ast; ast.parse(open('plugin_management/package_installer.py').read())"`.

- [ ] **Step 4: Commit**

```bash
git add plugin_management/package_installer.py plugin_management/tests/test_package_installer.py
git commit -m "feat: installed_plugin_dists() — installed MicroDrop plugin dist versions"
```

---

### Task 2: `update_model.py` — diff + dialog model

**Files:**
- Create: `plugin_management/update_model.py`
- Test: `plugin_management/tests/test_update_model.py`

**Interfaces:**
- Consumes: `plugin_management.browse_model._version_key`, `plugin_management.package_installer` (`install_from_channel`, `InstallError`).
- Produces: `UpdateReport` (traits: `updates: List[(name, installed, latest)]`, `new_plugins: List[(name, latest)]`, property `has_content`), `compute_update_report(old, new, installed) -> UpdateReport`, `UpdateDialogModel` (traits `report`, `updates_html`, `new_plugins_html`, `has_updates`, `has_new`; method `do_update_all() -> (list[str], list[(str, str)])`). Tasks 3 and 4 use these exact names.

- [ ] **Step 1: Write the module**

`plugin_management/update_model.py`:

```python
"""Model for the launch update-check dialog: the diff between the fresh
channel list, the previous launch's cached copy, and the installed set —
plus the worker-safe bulk update.

Qt-free (project MVC rule): nothing here imports Qt/pyface or mutates
traits off the GUI thread; ``do_update_all`` only returns data.
"""
import html

from traits.api import Bool, HasTraits, Instance, List, Str, Tuple

from logger.logger_service import get_logger

from . import package_installer
from .browse_model import _version_key

logger = get_logger(__name__)

#: Hint appended under the new-plugins list (install path lives elsewhere).
NEW_PLUGINS_HINT = (
    "<br><i>Install new plugins via Tools ▸ Manage Plugins ▸ "
    "Browse.</i>"
)


def _latest_by_name(packages) -> dict:
    """Collapse a raw channel package list to {name: latest version str}."""
    latest = {}
    for pkg in packages:
        name = pkg.get("name")
        if not name:
            continue
        version = str(pkg.get("version", ""))
        if name not in latest or _version_key(version) > _version_key(latest[name]):
            latest[name] = version
    return latest


class UpdateReport(HasTraits):
    """What the launch check found. ``updates`` rows are
    (name, installed_version, latest_version); ``new_plugins`` rows are
    (name, latest_version)."""

    updates = List(Tuple(Str, Str, Str))
    new_plugins = List(Tuple(Str, Str))

    @property
    def has_content(self):
        return bool(self.updates or self.new_plugins)


def compute_update_report(old, new, installed) -> UpdateReport:
    """Diff the fresh channel list against the installed set and the
    previous launch's cached copy.

    - update: installed package whose channel latest is newer than the
      installed version.
    - new plugin: channel package neither installed nor present in the OLD
      cached list. With no old cache (first launch) new-plugin detection
      is skipped entirely — the fetch just wrote the baseline — so a fresh
      install doesn't report every package as "new".
    """
    new_latest = _latest_by_name(new)
    old_names = set(_latest_by_name(old))
    updates = [
        (name, installed[name], latest)
        for name, latest in sorted(new_latest.items())
        if name in installed
        and _version_key(latest) > _version_key(installed[name])
    ]
    new_plugins = []
    if old_names:                       # first launch: baseline only
        new_plugins = [
            (name, latest)
            for name, latest in sorted(new_latest.items())
            if name not in installed and name not in old_names
        ]
    return UpdateReport(updates=updates, new_plugins=new_plugins)


class UpdateDialogModel(HasTraits):
    """Rows shown by the update dialog + the worker-safe bulk update."""

    report = Instance(UpdateReport)

    updates_html = Str()
    new_plugins_html = Str()
    has_updates = Bool(False)
    has_new = Bool(False)

    def traits_init(self):
        report = self.report
        self.has_updates = bool(report.updates)
        self.has_new = bool(report.new_plugins)
        self.updates_html = "<br>".join(
            f"<b>{html.escape(name)}</b>: {html.escape(installed)} "
            f"→ {html.escape(latest)}"
            for name, installed, latest in report.updates
        )
        if report.new_plugins:
            self.new_plugins_html = "<br>".join(
                f"<b>{html.escape(name)}</b> (v{html.escape(version)})"
                for name, version in report.new_plugins
            ) + NEW_PLUGINS_HINT

    def do_update_all(self):
        """Worker-thread safe: install the latest version of every listed
        update. Returns (succeeded names, [(name, error) failures])."""
        succeeded, failed = [], []
        for name, _installed, _latest in self.report.updates:
            try:
                package_installer.install_from_channel(name)
                succeeded.append(name)
            except package_installer.InstallError as e:
                logger.warning(f"update of {name} failed: {e}")
                failed.append((name, str(e)))
        return succeeded, failed
```

- [ ] **Step 2: Write the tests**

`plugin_management/tests/test_update_model.py`:

```python
"""compute_update_report is a pure function — these run Qt-free."""
from plugin_management.update_model import compute_update_report


def _pkg(name, version):
    return {"name": name, "version": version}


OLD = [_pkg("heater-microdrop-plugin", "1.0.0"),
       _pkg("magnet-microdrop-plugin", "1.0.0")]
NEW = [_pkg("heater-microdrop-plugin", "1.0.0"),
       _pkg("heater-microdrop-plugin", "1.0.2"),
       _pkg("magnet-microdrop-plugin", "1.0.0"),
       _pkg("shiny-new-plugin", "0.1.0")]


def test_update_detected_for_installed_older_version():
    report = compute_update_report(
        OLD, NEW, {"heater-microdrop-plugin": "1.0.0"})
    assert report.updates == [
        ("heater-microdrop-plugin", "1.0.0", "1.0.2")]


def test_no_update_when_installed_is_current_or_newer():
    report = compute_update_report(
        OLD, NEW, {"heater-microdrop-plugin": "1.0.2",
                   "magnet-microdrop-plugin": "2.0.0"})
    assert report.updates == []


def test_new_plugin_is_absent_from_old_cache_and_not_installed():
    report = compute_update_report(OLD, NEW, {})
    assert report.new_plugins == [("shiny-new-plugin", "0.1.0")]


def test_first_launch_baseline_reports_no_new_plugins():
    report = compute_update_report([], NEW, {"heater-microdrop-plugin": "1.0.0"})
    assert report.new_plugins == []
    assert report.updates == [
        ("heater-microdrop-plugin", "1.0.0", "1.0.2")]


def test_installed_but_gone_from_channel_is_ignored():
    report = compute_update_report(OLD, NEW, {"retired-plugin": "3.0.0"})
    assert all(name != "retired-plugin" for name, *_ in report.updates)


def test_has_content():
    assert not compute_update_report(OLD, OLD, {}).has_content
    assert compute_update_report(OLD, NEW, {}).has_content
```

- [ ] **Step 3: Verify with a logic smoke (no pytest)**

Run from `src` via the pixi env:

```bash
pixi run python -c "
import sys; sys.path.insert(0, 'src')
from plugin_management.update_model import compute_update_report
old = [{'name': 'a', 'version': '1.0.0'}]
new = [{'name': 'a', 'version': '1.0.1'}, {'name': 'b', 'version': '0.1.0'}]
r = compute_update_report(old, new, {'a': '1.0.0'})
assert r.updates == [('a', '1.0.0', '1.0.1')], r.updates
assert r.new_plugins == [('b', '0.1.0')], r.new_plugins
r2 = compute_update_report([], new, {'a': '1.0.0'})
assert r2.new_plugins == []
from plugin_management.update_model import UpdateDialogModel
m = UpdateDialogModel(report=r)
assert m.has_updates and m.has_new and '→' in m.updates_html
print('UPDATE MODEL SMOKE OK')
"
```

Expected: `UPDATE MODEL SMOKE OK`. (Adjust cwd/sys.path to however the repo's verified pixi invocation works; the pass criterion is the OK line.)

- [ ] **Step 4: Commit**

```bash
git add plugin_management/update_model.py plugin_management/tests/test_update_model.py
git commit -m "feat: update-check diff model (compute_update_report + UpdateDialogModel)"
```

---

### Task 3: dialog view + controller

**Files:**
- Create: `plugin_management/update_view.py`
- Create: `plugin_management/update_controller.py`

**Interfaces:**
- Consumes: `UpdateDialogModel` / `UpdateReport` (Task 2), `run_with_wait` (`microdrop_utils.threaded_progress`), `confirm_and_relaunch` (`plugin_management.relaunch`), `error` + `escape_html_multiline` (`microdrop_application.dialogs.pyface_wrapper`).
- Produces: `show_update_dialog(report, application)` — GUI-thread entry point Task 4 schedules via `GUI.invoke_later`.

- [ ] **Step 1: Write the view**

`plugin_management/update_view.py`:

```python
"""TraitsUI layout for the launch update-check dialog: an updates section
and a new-plugins section (each hides when empty) + Update All / Later
buttons. Pure presentation — the controller handles the buttons; the model
supplies the HTML row text."""
from traitsui.api import Action, Group, HTMLEditor, Item, VGroup, View

update_all_action = Action(name="Update All", action="update_all",
                           visible_when="object.has_updates")
later_action = Action(name="Later", action="do_close")

update_view = View(
    VGroup(
        Group(
            Item("updates_html", show_label=False, style="custom",
                 editor=HTMLEditor()),
            label="Updates available",
            show_border=True,
            visible_when="has_updates",
        ),
        Group(
            Item("new_plugins_html", show_label=False, style="custom",
                 editor=HTMLEditor()),
            label="New plugins available",
            show_border=True,
            visible_when="has_new",
        ),
    ),
    buttons=[update_all_action, later_action],
    title="Plugin Updates",
    kind="livemodal",
    width=460,
    height=340,
)
```

- [ ] **Step 2: Write the controller**

`plugin_management/update_controller.py`:

```python
"""Handler for the launch update-check dialog: Update All runs the bulk
update on a worker thread and then offers the standard relaunch popup;
Later just closes.

Worker callables (do_update_all) must not touch model traits — they return
data and the GUI-thread callbacks act on it (project threading rule)."""
from traits.api import Any
from traitsui.api import Handler

from microdrop_application.dialogs.pyface_wrapper import (
    error as error_dialog, escape_html_multiline)
from microdrop_utils.threaded_progress import run_with_wait

from logger.logger_service import get_logger

from .relaunch import confirm_and_relaunch

logger = get_logger(__name__)


def show_update_dialog(report, application):
    """Open the update dialog for a non-empty report. GUI thread only —
    schedule via ``GUI.invoke_later`` from workers."""
    from .update_model import UpdateDialogModel
    from .update_view import update_view

    window = getattr(application, "active_window", None)
    task = getattr(window, "active_task", None)
    model = UpdateDialogModel(report=report)
    model.edit_traits(view=update_view,
                      handler=UpdateDialogHandler(task=task))


class UpdateDialogHandler(Handler):
    """Runs the bulk update, reports failures, then offers a relaunch."""

    #: The active task, for confirm_and_relaunch (None-safe: the helper
    #: degrades gracefully without a running application).
    task = Any(None)

    def update_all(self, info):
        model = info.object
        run_with_wait(
            model.do_update_all,
            title="Updating plugins", message="Updating plugins…",
            on_success=lambda result: self._after_update(info, result),
            on_error=lambda e: error_dialog(
                parent=None, title="Update failed", message=str(e)),
        )

    def _after_update(self, info, result):
        succeeded, failed = result
        if failed:
            failures = "<br>".join(
                f"<b>{escape_html_multiline(name)}</b>: "
                f"{escape_html_multiline(err)}"
                for name, err in failed
            )
            error_dialog(parent=None, title="Some updates failed",
                         message=failures)
        info.ui.dispose()
        if succeeded:
            names = ", ".join(
                f"<b>{escape_html_multiline(name)}</b>" for name in succeeded
            )
            confirm_and_relaunch(self.task, f"Updated {names}.")

    def do_close(self, info):
        info.ui.dispose()
```

- [ ] **Step 3: Verify**

`python -c "import ast; ast.parse(open('plugin_management/update_view.py').read()); ast.parse(open('plugin_management/update_controller.py').read())"` — exit 0. Then an import smoke from the pixi env (Qt imports must resolve; do NOT open the dialog): `pixi run python -c "import plugin_management.update_controller, plugin_management.update_view; print('IMPORTS OK')"` (with `sys.path` adjusted as in Task 2 if needed).
Expected: `IMPORTS OK`.

- [ ] **Step 4: Commit**

```bash
git add plugin_management/update_view.py plugin_management/update_controller.py
git commit -m "feat: update-check dialog view + controller (Update All -> relaunch)"
```

---

### Task 4: launch hook in `PluginManagementPlugin`

**Files:**
- Modify: `plugin_management/plugin.py`

**Interfaces:**
- Consumes: `read_cached_index` / `search_channel` / `installed_plugin_dists` / `InstallError` (`package_installer`), `compute_update_report` (Task 2), `show_update_dialog` (Task 3).
- Produces: nothing new — behavior only.

- [ ] **Step 1: Add the observer + worker**

In `plugin_management/plugin.py`: add `import threading` to the stdlib imports. In the class, directly after `_restore_groups_on_launch` (and add `#: True once the launch update check has started` trait next to `_groups_restored`):

```python
    #: True once the launch update check has started (runs exactly once).
    _update_check_started = Bool(False)

    @observe("application:application_initialized")
    def _check_plugin_updates_on_launch(self, event):
        """Fetch the plugins channel in the background and, when an
        installed package has an update or new plugins appeared since the
        last launch, show the update dialog. Never blocks launch; offline
        (or any fetch failure) is silent. Colon-observe for the same
        reason as _restore_groups_on_launch above."""
        if self._update_check_started:
            return
        self._update_check_started = True
        threading.Thread(target=self._run_update_check, daemon=True,
                         name="plugin-update-check").start()

    def _run_update_check(self):
        from pyface.api import GUI

        from . import package_installer
        from .update_controller import show_update_dialog
        from .update_model import compute_update_report

        try:
            # Read the previous launch's copy BEFORE the fetch rewrites it.
            old = package_installer.read_cached_index()
            new = package_installer.search_channel()
            installed = package_installer.installed_plugin_dists()
        except package_installer.InstallError as e:
            logger.info(f"plugin update check skipped: {e}")
            return
        report = compute_update_report(old, new, installed)
        if not report.has_content:
            logger.info("plugin update check: everything up to date")
            return
        logger.info(
            f"plugin update check: {len(report.updates)} update(s), "
            f"{len(report.new_plugins)} new plugin(s)"
        )
        GUI.invoke_later(show_update_dialog, report, self.application)
```

(`Bool`, `observe`, and `logger` already exist in this module; verify the imports rather than re-adding.)

- [ ] **Step 2: Verify**

`python -c "import ast; ast.parse(open('plugin_management/plugin.py').read())"` — exit 0. Then wiring smoke (no GUI): `pixi run python -c "from plugin_management.plugin import PluginManagementPlugin; p = PluginManagementPlugin(); assert hasattr(p, '_run_update_check'); print('PLUGIN WIRING OK')"`.
Expected: `PLUGIN WIRING OK`.

- [ ] **Step 3: Commit**

```bash
git add plugin_management/plugin.py
git commit -m "feat: launch-time plugin update check (background fetch + dialog)"
```

---

### Task 5: Manual verification (human)

No automated runs — hand this checklist to the user:

- [ ] Launch with everything current — no dialog; log shows "plugin update check: everything up to date".
- [ ] `pixi add "heater-microdrop-plugin==1.0.0"` (downgrade), relaunch — dialog lists `heater-microdrop-plugin: 1.0.0 → <latest>`; Update All → wait dialog → relaunch popup; after relaunch the version is current and no dialog appears.
- [ ] Delete `plugin_index.json` from app data, relaunch — no "new plugins" section (baseline rebuild), updates still detected.
- [ ] Disconnect network, relaunch — silent launch, log shows "plugin update check skipped".
- [ ] Publish a brand-new package to the channel (or hand-edit the cached `plugin_index.json` to remove one) and relaunch — "New plugins available" section lists it with the Browse hint.
