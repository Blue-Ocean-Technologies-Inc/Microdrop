# Install Plugins From `.microdrop_plugin` Archives — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install plugins at runtime from a `*.microdrop_plugin` archive (Tools → Install Plugin… → file picker), driven by a `microdrop_plugin.json` manifest, and load them via a manifest-driven, generalized `PluginGroupManager` + a Manage Plugins dialog; magnet becomes the bundled-manifest + demo-archive example.

**Architecture:** Plugin groups are discovered from `microdrop_plugin.json` manifests in a repo `default_plugins/` dir and an app-data `installed_plugins/` dir (on `sys.path`). A hardened installer (extension gate, zip-slip, allowlist extraction, informed consent) extracts an archive and registers its groups live. `PluginGroupManager` resolves `module:Class` specs lazily at enable time; the hardcoded magnet `_groups_default` is retired.

**Tech Stack:** Envisage 7 / Pyface Tasks 8 / TraitsUI 8 / PySide6 / Python 3.13, `zipfile`, `importlib`, `importlib`-free dataclasses; Dramatiq+Redis.

**Spec:** `docs/superpowers/specs/2026-06-24-plugin-install-from-zip-design.md`

## Global Constraints

- **Working directory for all commands:** `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src`. Commits land in the submodule on branch `feature/peripheral-hot-load`.
- **Testing convention (this project):** NO pytest. Each task gates on (a) `python -m py_compile <files>`, then (b) a `pixi run` import/introspection smoke from the parent dir, then (c) manual GUI checks at the end (Task 11). Run Python only via pixi: `cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '...'"`. Redis must be running for imports that pull dramatiq (`pixi run python examples/start_redis_server.py`).
- **Any smoke that touches `installed_plugins/`** must first point app-data at a scratch dir so it doesn't pollute the real one and is deterministic: set `from traits.etsconfig.api import ETSConfig; ETSConfig.application_home = <tempdir>` **before** importing `microdrop_application.plugins.paths` (or anything that calls it).
- **Conventions:** dataclasses for inert parsed data; HasTraits + traits_init/_x_default elsewhere; `@observe` (synthetic `_items` → `on_trait_change`); f-strings only; logger via `from logger.logger_service import get_logger`; no Qt in model/service layers (Qt only in views + `microdrop_utils/tasks_runtime_helpers.py`); dialogs via `microdrop_application.dialogs.pyface_wrapper` or TraitsUI `edit_traits(kind="livemodal")`.
- **Commit trailer:** end every commit message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Manifest is the source of truth** for group name / label / `module:Class` specs / `enabled_key` / `post_enable_publish_topic`; do not reintroduce hardcoded magnet group constants.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `microdrop_application/plugins/__init__.py` | package marker | Create |
| `microdrop_application/plugins/manifest.py` | parse/validate `microdrop_plugin.json` → dataclasses | Create |
| `microdrop_application/plugins/paths.py` | default/installed dirs, `sys.path`, manifest-dir discovery | Create |
| `microdrop_application/plugins/installer.py` | zip → validate (zip-slip+allowlist) → consent → extract → register | Create |
| `default_plugins/magnet_peripherals/microdrop_plugin.json` | bundled magnet manifest | Create |
| `microdrop_application/plugin_group_manager.py` | manifest-driven discovery, lazy specs, generic apply | Rewrite |
| `microdrop_application/plugins_manager_dialog.py` | dynamic Manage Plugins checkbox model | Create |
| `microdrop_application/peripherals_manager_dialog.py` | superseded | Delete |
| `microdrop_application/menus.py` | `InstallPluginAction` + `ManagePluginsAction` | Modify |
| `microdrop_application/task.py` | menu wiring + startup discovery + generic restore | Modify |
| `microdrop_application/consts.py` | drop unused magnet group/key consts | Modify |
| `examples/plugin_consts.py` | point magnet doc comment at the manifest | Modify |
| `examples/build_plugin_zip.py` | build the magnet demo archive | Create |

---

## Task 1: Manifest parser

**Files:**
- Create: `microdrop_application/plugins/__init__.py`, `microdrop_application/plugins/manifest.py`

**Interfaces:**
- Produces: `ManifestError(ValueError)`; `@dataclass PluginGroupSpec(name, label, plugins: list[str], enabled_key, post_enable_publish_topic="")`; `@dataclass PluginManifest(schema_version, name, label, version, packages: list[str], groups: list[PluginGroupSpec])`; `load_manifest(source: str|bytes|Path) -> PluginManifest`; `SCHEMA_VERSION = 1`.

- [ ] **Step 1: Create the package marker**

Create `microdrop_application/plugins/__init__.py` with a one-line docstring:

```python
"""Runtime plugin install + manifest-driven group discovery."""
```

- [ ] **Step 2: Create `manifest.py`**

Create `microdrop_application/plugins/manifest.py`:

```python
"""Parse and validate a microdrop_plugin.json manifest.

The manifest (at the root of a .microdrop_plugin archive, or in a
default_plugins/<name>/ directory) declares the Python packages an archive
carries and the plugin GROUP(s) they form, so PluginGroupManager can register
and hot load/unload them. Pure inert data — no Traits, no Qt.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

SCHEMA_VERSION = 1


class ManifestError(ValueError):
    """A microdrop_plugin.json is missing, malformed, or fails validation."""


@dataclass
class PluginGroupSpec:
    name: str
    label: str
    plugins: List[str]                       # dotted "module:Class" specs
    enabled_key: str
    post_enable_publish_topic: str = ""


@dataclass
class PluginManifest:
    schema_version: int
    name: str
    label: str
    version: str
    packages: List[str]
    groups: List[PluginGroupSpec]


def load_manifest(source: Union[str, bytes, Path]) -> PluginManifest:
    """Parse + validate a manifest from a path, JSON string, or raw bytes.

    Raises ManifestError with a clear message on any problem."""
    try:
        if isinstance(source, (str, Path)) and Path(str(source)).exists():
            text = Path(source).read_text(encoding="utf-8")
        elif isinstance(source, bytes):
            text = source.decode("utf-8")
        else:
            text = str(source)
        data = json.loads(text)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        raise ManifestError(f"could not read manifest JSON: {e}") from e

    if not isinstance(data, dict):
        raise ManifestError("manifest must be a JSON object")

    schema = data.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported schema_version {schema!r} (expected {SCHEMA_VERSION})"
        )

    name = data.get("name")
    if not name or not isinstance(name, str):
        raise ManifestError("manifest 'name' is required and must be a string")

    packages = data.get("packages")
    if (not isinstance(packages, list) or not packages
            or not all(isinstance(p, str) and p for p in packages)):
        raise ManifestError("manifest 'packages' must be a non-empty list of strings")

    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        raise ManifestError("manifest 'groups' must be a non-empty list")

    groups = []
    for i, g in enumerate(raw_groups):
        if not isinstance(g, dict):
            raise ManifestError(f"group #{i} must be a JSON object")
        gname = g.get("name")
        if not gname or not isinstance(gname, str):
            raise ManifestError(f"group #{i} 'name' is required")
        plugins = g.get("plugins")
        if (not isinstance(plugins, list) or not plugins
                or not all(isinstance(p, str) and ":" in p for p in plugins)):
            raise ManifestError(
                f"group '{gname}' 'plugins' must be a non-empty list of "
                f"'module:Class' strings"
            )
        enabled_key = g.get("enabled_key")
        if not enabled_key or not isinstance(enabled_key, str):
            raise ManifestError(f"group '{gname}' 'enabled_key' is required")
        groups.append(PluginGroupSpec(
            name=gname,
            label=g.get("label") or gname,
            plugins=list(plugins),
            enabled_key=enabled_key,
            post_enable_publish_topic=g.get("post_enable_publish_topic", "") or "",
        ))

    return PluginManifest(
        schema_version=schema,
        name=name,
        label=data.get("label") or name,
        version=str(data.get("version", "")),
        packages=list(packages),
        groups=groups,
    )
```

- [ ] **Step 3: Compile**

Run: `python -m py_compile microdrop_application/plugins/__init__.py microdrop_application/plugins/manifest.py`
Expected: no output.

- [ ] **Step 4: Import + parse smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
from microdrop_application.plugins.manifest import load_manifest, ManifestError
m = load_manifest(\"\"\"{\"schema_version\":1,\"name\":\"magnet_peripherals\",\"label\":\"Magnet\",\"version\":\"1.0.0\",\"packages\":[\"peripheral_controller\"],\"groups\":[{\"name\":\"magnet_backend\",\"label\":\"Backend\",\"plugins\":[\"peripheral_controller.plugin:PeripheralControllerPlugin\"],\"enabled_key\":\"microdrop.peripheral_backend_enabled\",\"post_enable_publish_topic\":\"ZStage/requests/start_device_monitoring\"}]}\"\"\")
print(\"name:\", m.name, \"| groups:\", [g.name for g in m.groups], \"| topic:\", m.groups[0].post_enable_publish_topic)
try:
    load_manifest(\"{\\\"schema_version\\\":2}\")
    print(\"FAIL: no error\")
except ManifestError as e:
    print(\"rejected bad schema OK\")
'"
```
Expected: `name: magnet_peripherals | groups: ['magnet_backend'] | topic: ZStage/requests/start_device_monitoring` and `rejected bad schema OK`.

- [ ] **Step 5: Commit**

```bash
git add microdrop_application/plugins/__init__.py microdrop_application/plugins/manifest.py
git commit -m "Add microdrop_plugin.json manifest parser

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Plugin paths + manifest-dir discovery

**Files:**
- Create: `microdrop_application/plugins/paths.py`

**Interfaces:**
- Produces: `MANIFEST_FILENAME = "microdrop_plugin.json"`; `default_plugins_dir() -> Path`; `installed_plugins_dir() -> Path` (creates it); `ensure_on_sys_path() -> None`; `iter_manifest_dirs() -> Iterator[Path]`.

- [ ] **Step 1: Create `paths.py`**

Create `microdrop_application/plugins/paths.py`:

```python
"""Filesystem locations + sys.path wiring for bundled and installed plugins."""

import sys
from pathlib import Path
from typing import Iterator

from traits.etsconfig.api import ETSConfig

# src/ — the dir microdrop_runner_setup puts on sys.path. Bundled default
# plugin manifests live under default_plugins/ beside the source packages.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_FILENAME = "microdrop_plugin.json"


def default_plugins_dir() -> Path:
    """Repo-bundled plugin manifests (code lives in src/, already importable)."""
    return _PROJECT_ROOT / "default_plugins"


def installed_plugins_dir() -> Path:
    """Per-user installed plugins, beside preferences.ini in app-data
    (ETSConfig.application_home). Created if missing."""
    path = Path(ETSConfig.application_home) / "installed_plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_on_sys_path() -> None:
    """Put the installed-plugins dir on sys.path so extracted packages import."""
    path = str(installed_plugins_dir())
    if path not in sys.path:
        sys.path.append(path)


def iter_manifest_dirs() -> Iterator[Path]:
    """Yield each immediate subdir of default_plugins/ then installed_plugins/
    that contains a microdrop_plugin.json. Discovery order: bundled first."""
    for root in (default_plugins_dir(), installed_plugins_dir()):
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / MANIFEST_FILENAME).is_file():
                yield child
```

- [ ] **Step 2: Compile**

Run: `python -m py_compile microdrop_application/plugins/paths.py`
Expected: no output.

- [ ] **Step 3: Import + path smoke (scratch app-home)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig
ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdtest_\")
from microdrop_application.plugins import paths
ip = paths.installed_plugins_dir()
print(\"installed exists:\", ip.is_dir(), \"| name:\", ip.name)
print(\"default ends with src/default_plugins:\", str(paths.default_plugins_dir()).replace(chr(92),\"/\").endswith(\"src/default_plugins\"))
paths.ensure_on_sys_path()
import sys
print(\"on sys.path:\", str(ip) in sys.path)
'"
```
Expected: `installed exists: True | name: installed_plugins`, `default ends with src/default_plugins: True`, `on sys.path: True`.

- [ ] **Step 4: Commit**

```bash
git add microdrop_application/plugins/paths.py
git commit -m "Add plugin paths: default/installed dirs, sys.path, manifest discovery

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Bundled magnet manifest

**Files:**
- Create: `default_plugins/magnet_peripherals/microdrop_plugin.json`

**Interfaces:**
- Produces: the discoverable bundled manifest for the two magnet groups.

- [ ] **Step 1: Create the manifest**

Create `default_plugins/magnet_peripherals/microdrop_plugin.json`:

```json
{
  "schema_version": 1,
  "name": "magnet_peripherals",
  "label": "Magnet Peripherals",
  "version": "1.0.0",
  "packages": ["peripheral_controller", "peripheral_protocol_controls", "peripherals_ui"],
  "groups": [
    {
      "name": "magnet_backend",
      "label": "Magnet Backend (controller + connection search)",
      "plugins": ["peripheral_controller.plugin:PeripheralControllerPlugin"],
      "enabled_key": "microdrop.peripheral_backend_enabled",
      "post_enable_publish_topic": "ZStage/requests/start_device_monitoring"
    },
    {
      "name": "magnet_ui",
      "label": "Magnet UI (dock pane, status icon, protocol column)",
      "plugins": [
        "peripheral_protocol_controls.plugin:PeripheralProtocolControlsPlugin",
        "peripherals_ui.plugin:PeripheralUiPlugin"
      ],
      "enabled_key": "microdrop.peripheral_ui_enabled"
    }
  ]
}
```

- [ ] **Step 2: Validate it parses**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
from microdrop_application.plugins.manifest import load_manifest
from microdrop_application.plugins import paths
m = load_manifest(paths.default_plugins_dir()/\"magnet_peripherals\"/\"microdrop_plugin.json\")
print(\"groups:\", [(g.name, g.enabled_key) for g in m.groups])
print(\"backend topic:\", m.groups[0].post_enable_publish_topic)
'"
```
Expected: `groups: [('magnet_backend', 'microdrop.peripheral_backend_enabled'), ('magnet_ui', 'microdrop.peripheral_ui_enabled')]` and `backend topic: ZStage/requests/start_device_monitoring`.

- [ ] **Step 3: Commit**

```bash
git add default_plugins/magnet_peripherals/microdrop_plugin.json
git commit -m "Add bundled magnet_peripherals plugin manifest

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Manifest-driven `PluginGroupManager`

**Files:**
- Rewrite: `microdrop_application/plugin_group_manager.py`

**Interfaces:**
- Consumes: Task 1 `load_manifest`/`ManifestError`; Task 2 `paths`; Task 3 manifest; existing `tasks_runtime_helpers` add/remove/rebuild, `publish_message`.
- Produces: `PluginGroup` with `label: Str`, `plugin_specs: List(Str)`, plus the existing runtime fields; `PluginGroupManager` with `groups` (discovered), `is_loaded`, `apply(task, desired)`, `enable`, `disable`, `register_manifest(manifest)`, `_resolve_factories`, `_discover_groups`, `_add_manifest_groups`. No hardcoded `_groups_default`.

- [ ] **Step 1: Replace the whole file**

Overwrite `microdrop_application/plugin_group_manager.py` with:

```python
"""Runtime hot load/unload of *named groups* of Envisage plugins.

Groups are discovered from microdrop_plugin.json manifests — bundled ones in
the repo's default_plugins/ and user-installed ones under the app-data
installed_plugins/ dir (see microdrop_application.plugins). Each group names
its plugin classes as dotted "module:Class" specs, resolved lazily at enable
time so a broken/installed plugin never breaks startup or discovery.

Envisage supports adding/removing plugins at runtime, but three layers don't
self-heal: runtime ServiceOffers leak (CorePlugin discards their ids), Pyface
Tasks never adds a dock pane after the window is shown, and a plugin's backend
resources outlive a bare stop(). This orchestrator fills the first two
generically (service-id capture + live dock-pane mount/unmount) and relies on
each plugin's own stop() for the third. The menu bar is rebuilt on each
enable/disable so plugin-contributed submenus appear/disappear live.
"""

import importlib

from traits.api import Bool, Dict, HasTraits, Instance, List, Str

from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_application.plugins import paths
from microdrop_application.plugins.manifest import load_manifest, ManifestError
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.tasks_runtime_helpers import (
    add_dock_pane_live, rebuild_menu_bar_live, remove_dock_pane_live,
)
from logger.logger_service import get_logger

logger = get_logger(__name__)

app_globals = get_microdrop_redis_globals_manager()


class PluginGroup(HasTraits):
    """One named, ordered set of plugins that load/unload together."""

    name = Str()
    #: User-visible label (shown in the Manage Plugins dialog).
    label = Str()
    #: Plugin classes as dotted "module:Class" specs, in load order (unloaded
    #: in reverse). Resolved to classes lazily at enable time.
    plugin_specs = List(Str)
    #: Live plugin instances while loaded (empty otherwise).
    instances = List()
    #: Service-registry ids registered while the group loaded, captured by a
    #: before/after snapshot so disable() can unregister exactly them.
    service_ids = List()
    #: Ids of dock panes mounted live for this group.
    dock_pane_ids = List(Str)
    loaded = Bool(False)
    #: App-globals flag persisting this group's enabled state across runs.
    enabled_key = Str()
    #: Optional topic published (empty message) right after a successful
    #: enable — e.g. the backend group kicks off the magnet search.
    post_enable_publish_topic = Str()


class PluginGroupManager(HasTraits):
    """Discovers, loads, and unloads named plugin groups against a live
    application. Offered as an Envisage service by MicrodropPlugin; the
    Install/Manage Plugins actions and the launch-restore hook use it."""

    groups = Dict(Str, Instance(PluginGroup))

    def _groups_default(self):
        return self._discover_groups()

    # --- discovery ---------------------------------------------------

    def _discover_groups(self):
        """Build the group map from every manifest in default_plugins/ and
        installed_plugins/. Reads JSON only (no plugin imports), so a broken
        installed plugin can't break discovery."""
        groups = {}
        for manifest_dir in paths.iter_manifest_dirs():
            manifest_path = manifest_dir / paths.MANIFEST_FILENAME
            try:
                manifest = load_manifest(manifest_path)
            except ManifestError:
                logger.exception(f"skipping invalid manifest at {manifest_path}")
                continue
            self._add_manifest_groups(manifest, into=groups)
        return groups

    def _add_manifest_groups(self, manifest, into=None):
        """Create a PluginGroup per spec in ``manifest`` and put it in ``into``
        (defaults to self.groups). Last writer wins on a name collision."""
        target = self.groups if into is None else into
        for spec in manifest.groups:
            target[spec.name] = PluginGroup(
                name=spec.name,
                label=spec.label,
                plugin_specs=list(spec.plugins),
                enabled_key=spec.enabled_key,
                post_enable_publish_topic=spec.post_enable_publish_topic,
            )

    def register_manifest(self, manifest):
        """Register a freshly-installed manifest's groups at runtime. Refuses
        (raises) if a colliding group name is currently loaded — the caller
        should ask the user to disable it first."""
        for spec in manifest.groups:
            existing = self.groups.get(spec.name)
            if existing is not None and existing.loaded:
                raise RuntimeError(
                    f"group '{spec.name}' is currently enabled; disable it "
                    f"before reinstalling"
                )
        self._add_manifest_groups(manifest)

    # --- public API --------------------------------------------------

    def is_loaded(self, group_name):
        group = self.groups.get(group_name)
        return bool(group is not None and group.loaded)

    def apply(self, task, desired):
        """Reconcile group load state to ``desired`` ({group_name: bool}).
        Enables newly-on groups in registration order; disables newly-off
        groups in reverse. Only groups whose desired state differs are
        touched."""
        names = list(self.groups.keys())
        for group_name in names:
            if desired.get(group_name) and not self.is_loaded(group_name):
                self.enable(task, group_name)
        for group_name in reversed(names):
            if (group_name in desired
                    and not desired[group_name]
                    and self.is_loaded(group_name)):
                self.disable(task, group_name)

    def enable(self, task, group_name):
        """Resolve the group's plugin specs, add + start them, capture the
        services they register, mount their dock panes, rebuild the menu bar,
        and run the optional post-enable publish. Idempotent — a no-op if the
        group is already loaded."""
        group = self.groups.get(group_name)
        if group is None:
            logger.warning(f"enable: unknown plugin group '{group_name}'")
            return
        if group.loaded:
            logger.info(f"enable: group '{group_name}' already loaded")
            return

        try:
            factories = self._resolve_factories(group)
        except Exception:
            logger.exception(
                f"enable: could not import plugin classes for '{group_name}'; "
                f"group not loaded"
            )
            return

        application = task.window.application
        registry = application.service_registry
        before = set(registry._services.keys())

        for factory in factories:
            try:
                plugin = factory()
                application.add_plugin(plugin)
                application.start_plugin(plugin)
                group.instances.append(plugin)
                logger.info(f"enable: started {plugin.id}")
            except Exception:
                logger.exception(
                    f"enable: failed to load {getattr(factory, '__name__', factory)}"
                )

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

    def disable(self, task, group_name):
        """Reverse of enable: unmount dock panes, stop + remove every plugin
        (reverse order), unregister the captured services, rebuild the menu
        bar. Idempotent — a no-op if the group isn't loaded."""
        group = self.groups.get(group_name)
        if group is None:
            logger.warning(f"disable: unknown plugin group '{group_name}'")
            return
        if not group.loaded:
            logger.info(f"disable: group '{group_name}' not loaded")
            return

        application = task.window.application
        window = task.window

        # UI first: drop the panes before the backend they observe goes away.
        for pane_id in reversed(group.dock_pane_ids):
            try:
                remove_dock_pane_live(window, pane_id)
            except Exception:
                logger.exception(f"disable: failed to remove dock pane '{pane_id}'")
        group.dock_pane_ids = []

        for plugin in reversed(group.instances):
            pid = getattr(plugin, "id", plugin)
            try:
                application.stop_plugin(plugin)
            except Exception:
                logger.exception(f"disable: stop_plugin failed for {pid}")
            try:
                application.remove_plugin(plugin)
            except Exception:
                logger.exception(f"disable: remove_plugin failed for {pid}")
            logger.info(f"disable: removed {pid}")
        group.instances = []

        for service_id in group.service_ids:
            try:
                application.unregister_service(service_id)
                logger.info(f"disable: unregistered service id {service_id}")
            except Exception:
                logger.exception(f"disable: unregister_service failed for {service_id}")
        group.service_ids = []

        try:
            rebuild_menu_bar_live(window, task, application)
        except Exception:
            logger.exception("disable: menu bar rebuild failed")

        group.loaded = False
        if group.enabled_key:
            app_globals[group.enabled_key] = False
        logger.info(f"disable: group '{group_name}' unloaded")

    # --- helpers -----------------------------------------------------

    def _resolve_factories(self, group):
        """Import each "module:Class" spec to a plugin class. Raises on the
        first failure so the caller aborts the enable (no partial load)."""
        factories = []
        for spec in group.plugin_specs:
            module_path, _, class_name = spec.partition(":")
            module = importlib.import_module(module_path)
            factories.append(getattr(module, class_name))
        return factories

    def _mount_dock_panes(self, task, group):
        """Mount every dock pane the group's started plugins contribute for
        this task. Pyface gathers panes once at window creation, so a plugin
        loaded afterwards needs its pane mounted explicitly."""
        window = task.window
        for plugin in group.instances:
            extensions = getattr(plugin, "contributed_task_extensions", None) or []
            for extension in extensions:
                ext_task_id = getattr(extension, "task_id", None)
                if ext_task_id and ext_task_id != task.id:
                    continue
                for factory in getattr(extension, "dock_pane_factories", []) or []:
                    try:
                        pane = add_dock_pane_live(window, task, factory)
                    except Exception:
                        logger.exception(
                            f"enable: failed to mount a dock pane for {plugin.id}"
                        )
                        continue
                    if pane is not None:
                        group.dock_pane_ids.append(pane.id)
```

- [ ] **Step 2: Compile**

Run: `python -m py_compile microdrop_application/plugin_group_manager.py`
Expected: no output.

- [ ] **Step 3: Discovery + lazy-resolve smoke (scratch app-home, Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig
ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdtest_\")
from microdrop_application.plugin_group_manager import PluginGroupManager
m = PluginGroupManager()
print(\"discovered:\", list(m.groups.keys()))
be = m.groups[\"magnet_backend\"]
print(\"backend specs:\", be.plugin_specs, \"| key:\", be.enabled_key, \"| topic set:\", bool(be.post_enable_publish_topic))
print(\"ui label:\", m.groups[\"magnet_ui\"].label)
f = m._resolve_factories(be)
print(\"resolved:\", [c.__name__ for c in f])
print(\"apply present:\", hasattr(m, \"apply\"), \"| register_manifest present:\", hasattr(m, \"register_manifest\"))
'"
```
Expected: `discovered: ['magnet_backend', 'magnet_ui']`; backend specs `['peripheral_controller.plugin:PeripheralControllerPlugin']`, key `microdrop.peripheral_backend_enabled`, `topic set: True`; ui label the magnet-ui string; `resolved: ['PeripheralControllerPlugin']`; both `present: True`.

- [ ] **Step 4: Commit**

```bash
git add microdrop_application/plugin_group_manager.py
git commit -m "Make PluginGroupManager manifest-driven with lazy specs + generic apply

Discovers groups from default_plugins/ and installed_plugins/ manifests
(JSON only, no imports), resolves module:Class specs lazily at enable time,
generalizes apply() to any groups, and adds register_manifest() for runtime
installs. Retires the hardcoded magnet _groups_default.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Installer

**Files:**
- Create: `microdrop_application/plugins/installer.py`

**Interfaces:**
- Consumes: Task 1 `load_manifest`/`ManifestError`; Task 2 `paths`; Task 4 `PluginGroupManager.is_loaded`/`register_manifest`.
- Produces: `InstallError(Exception)`; `InstallCancelled(Exception)`; `install_from_zip(zip_path, manager, *, confirm=None, dest_root=None) -> PluginManifest`.

- [ ] **Step 1: Create `installer.py`**

Create `microdrop_application/plugins/installer.py`:

```python
"""Install a .microdrop_plugin archive (a zip) into the app-data
installed_plugins dir and register its groups with the live PluginGroupManager.

Security hardening (no signing): the archive uses the .microdrop_plugin
extension (enforced by the file dialog), every entry is validated against
zip-slip and an allowlist of the manifest's declared packages BEFORE anything
is extracted, and an injected ``confirm`` callback gates the install on
informed user consent.
"""

import shutil
import zipfile
from pathlib import Path, PurePosixPath

from microdrop_application.plugins import paths
from microdrop_application.plugins.manifest import load_manifest, ManifestError
from logger.logger_service import get_logger

logger = get_logger(__name__)

_S_IFLNK = 0xA000     # unix symlink mode bits, stored in zip external_attr


class InstallError(Exception):
    """The archive is malformed, unsafe, or could not be installed."""


class InstallCancelled(Exception):
    """The user declined the install at the consent prompt."""


def _read_manifest_from_zip(zf):
    try:
        raw = zf.read(paths.MANIFEST_FILENAME)
    except KeyError:
        raise InstallError(f"archive has no {paths.MANIFEST_FILENAME} at its root")
    try:
        return load_manifest(raw)
    except ManifestError as e:
        raise InstallError(str(e)) from e


def _validate_entries(zf, manifest):
    """Return the safe member names to extract. Rejects zip-slip (absolute /
    '..' / symlink) and any entry whose top-level component isn't the manifest
    or a declared package."""
    allowed_tops = set(manifest.packages) | {paths.MANIFEST_FILENAME}
    members = []
    for info in zf.infolist():
        name = info.filename
        if name.endswith("/"):
            continue                                  # dir entry; created implicitly
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts:
            raise InstallError(f"unsafe path in archive: {name!r}")
        if ((info.external_attr >> 16) & 0xF000) == _S_IFLNK:
            raise InstallError(f"symlink entries are not allowed: {name!r}")
        top = pure.parts[0] if pure.parts else ""
        if top not in allowed_tops:
            raise InstallError(
                f"archive entry {name!r} is outside the declared packages "
                f"{sorted(manifest.packages)}"
            )
        members.append(name)
    return members


def install_from_zip(zip_path, manager, *, confirm=None, dest_root=None):
    """Validate, consent-gate, extract, and register a .microdrop_plugin archive.

    ``confirm(manifest) -> bool`` is the informed-consent callback (the action
    passes a dialog). ``dest_root`` overrides the install dir (tests). Returns
    the PluginManifest. Nothing is extracted unless the manifest + all entries
    validate and consent is given. Raises InstallError / InstallCancelled."""
    zip_path = Path(zip_path)
    if not zipfile.is_zipfile(zip_path):
        raise InstallError(f"{zip_path.name} is not a valid archive")

    with zipfile.ZipFile(zip_path) as zf:
        manifest = _read_manifest_from_zip(zf)
        members = _validate_entries(zf, manifest)

        if confirm is not None and not confirm(manifest):
            raise InstallCancelled(f"install of '{manifest.name}' declined")

        # Refuse to clobber a currently-enabled install.
        for spec in manifest.groups:
            if manager.is_loaded(spec.name):
                raise InstallError(
                    f"group '{spec.name}' is enabled; disable it before reinstalling"
                )

        root = Path(dest_root) if dest_root is not None else paths.installed_plugins_dir()
        target = root / manifest.name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        zf.extractall(target, members=members)

    paths.ensure_on_sys_path()
    manager.register_manifest(manifest)
    logger.info(f"installed plugin '{manifest.name}' to {target}")
    return manifest
```

- [ ] **Step 2: Compile**

Run: `python -m py_compile microdrop_application/plugins/installer.py`
Expected: no output.

- [ ] **Step 3: Install + reject smoke (builds a fixture archive in scratch, Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile, zipfile, json
from pathlib import Path
from traits.etsconfig.api import ETSConfig
ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdtest_\")
from microdrop_application.plugin_group_manager import PluginGroupManager
from microdrop_application.plugins import installer

tmp = Path(tempfile.mkdtemp())
man = {\"schema_version\":1,\"name\":\"demo_plugin\",\"label\":\"Demo\",\"version\":\"0.1\",\"packages\":[\"demo_pkg\"],\"groups\":[{\"name\":\"demo_group\",\"label\":\"Demo Group\",\"plugins\":[\"demo_pkg.plugin:DemoPlugin\"],\"enabled_key\":\"microdrop.demo_enabled\"}]}
arc = tmp/\"demo.microdrop_plugin\"
with zipfile.ZipFile(arc, \"w\") as zf:
    zf.writestr(\"microdrop_plugin.json\", json.dumps(man))
    zf.writestr(\"demo_pkg/__init__.py\", \"\")
    zf.writestr(\"demo_pkg/plugin.py\", \"class DemoPlugin: pass\")
dest = tmp/\"dest\"
m = PluginGroupManager()
mani = installer.install_from_zip(arc, m, confirm=lambda x: True, dest_root=dest)
print(\"installed:\", mani.name, \"| extracted:\", (dest/\"demo_plugin\"/\"demo_pkg\"/\"plugin.py\").is_file())
print(\"registered:\", \"demo_group\" in m.groups)

# Reject: undeclared top-level entry
bad = tmp/\"bad.microdrop_plugin\"
with zipfile.ZipFile(bad, \"w\") as zf:
    zf.writestr(\"microdrop_plugin.json\", json.dumps(man))
    zf.writestr(\"evil.py\", \"import os\")
try:
    installer.install_from_zip(bad, m, confirm=lambda x: True, dest_root=dest)
    print(\"FAIL: bad archive not rejected\")
except installer.InstallError as e:
    print(\"rejected undeclared entry OK\")

# Cancel path
try:
    installer.install_from_zip(arc, m, confirm=lambda x: False, dest_root=dest)
    print(\"FAIL: cancel not raised\")
except installer.InstallCancelled:
    print(\"cancel OK\")
'"
```
Expected: `installed: demo_plugin | extracted: True`, `registered: True`, `rejected undeclared entry OK`, `cancel OK`.

- [ ] **Step 4: Commit**

```bash
git add microdrop_application/plugins/installer.py
git commit -m "Add hardened .microdrop_plugin installer (zip-slip + allowlist + consent)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Manage Plugins dialog model

**Files:**
- Create: `microdrop_application/plugins_manager_dialog.py`
- Delete: `microdrop_application/peripherals_manager_dialog.py`

**Interfaces:**
- Produces: `PluginsManagerModel(groups: list[tuple[str, str, bool]])` with one `Bool` trait per group (`grp__<name>`), `desired() -> dict[str, bool]`, and a dynamic livemodal `traits_view`.

- [ ] **Step 1: Create `plugins_manager_dialog.py`**

Create `microdrop_application/plugins_manager_dialog.py`:

```python
"""Manage Plugins dialog model: one checkbox per registered plugin group.

Built dynamically from the live group list (name, label, loaded) — adds a Bool
trait per group and a programmatic TraitsUI view. Qt-free; the action owns the
orchestration (apply on OK)."""

from traits.api import Bool, HasTraits
from traitsui.api import Item, Label, VGroup, View


def _trait_name(group_name):
    return "grp__" + group_name


class PluginsManagerModel(HasTraits):
    """Checkbox state for the Manage Plugins dialog. ``groups`` is a list of
    (group_name, label, loaded) tuples."""

    def __init__(self, groups, **traits):
        super().__init__(**traits)
        self._group_names = [name for name, _label, _loaded in groups]
        self._group_labels = {name: label for name, label, _loaded in groups}
        for name, _label, loaded in groups:
            self.add_trait(_trait_name(name), Bool(loaded))

    def desired(self):
        """{group_name: checkbox bool} for every listed group."""
        return {name: getattr(self, _trait_name(name)) for name in self._group_names}

    def traits_view(self):
        if self._group_names:
            items = [
                Item(_trait_name(name), label=self._group_labels[name])
                for name in self._group_names
            ]
        else:
            items = [Label("No optional plugins are installed.")]
        return View(
            VGroup(*items, label="Enable plugin groups", show_border=True),
            buttons=["OK", "Cancel"],
            kind="livemodal",
            title="Manage Plugins",
            resizable=True,
        )
```

- [ ] **Step 2: Delete the superseded dialog**

Run: `git rm microdrop_application/peripherals_manager_dialog.py`
Expected: `rm 'microdrop_application/peripherals_manager_dialog.py'`.

- [ ] **Step 3: Compile**

Run: `python -m py_compile microdrop_application/plugins_manager_dialog.py`
Expected: no output.

- [ ] **Step 4: Import + dynamic-trait smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
from microdrop_application.plugins_manager_dialog import PluginsManagerModel
m = PluginsManagerModel([(\"magnet_ui\",\"Magnet UI\",False),(\"magnet_backend\",\"Magnet Backend\",True)])
print(\"ui:\", m.grp__magnet_ui, \"| backend:\", m.grp__magnet_backend)
print(\"desired:\", m.desired())
'"
```
Expected: `ui: False | backend: True` and `desired: {'magnet_ui': False, 'magnet_backend': True}`.

- [ ] **Step 5: Commit**

```bash
git add microdrop_application/plugins_manager_dialog.py microdrop_application/peripherals_manager_dialog.py
git commit -m "Add dynamic Manage Plugins dialog model; remove magnet-only dialog

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Install + Manage Plugins menu actions

**Files:**
- Modify: `microdrop_application/menus.py`

**Interfaces:**
- Consumes: Task 4 `PluginGroupManager`; Task 5 `installer`; Task 6 `PluginsManagerModel`; `pyface_wrapper.file_dialog/confirm/information/error/YES`.
- Produces: `ManagePluginsAction(TaskAction)`, `InstallPluginAction(TaskAction)`. Removes `ManagePeripheralsAction`, `is_peripheral_ui_enabled`, `is_peripheral_backend_enabled`, and the magnet consts import.

- [ ] **Step 1: Swap the consts import**

In `microdrop_application/menus.py`, replace:

```python
from microdrop_application.consts import (
    ADVANCED_MODE_CHANGE, MAGNET_BACKEND_GROUP, MAGNET_UI_GROUP,
    PERIPHERAL_BACKEND_ENABLED_KEY, PERIPHERAL_UI_ENABLED_KEY,
)
```

with:

```python
from microdrop_application.consts import ADVANCED_MODE_CHANGE
```

- [ ] **Step 2: Remove the magnet enabled-flag helpers**

In `microdrop_application/menus.py`, delete these two functions entirely:

```python
def is_peripheral_ui_enabled():
    return app_globals.get(PERIPHERAL_UI_ENABLED_KEY, False)


def is_peripheral_backend_enabled():
    return app_globals.get(PERIPHERAL_BACKEND_ENABLED_KEY, False)
```

- [ ] **Step 3: Replace `ManagePeripheralsAction` with the two generic actions**

In `microdrop_application/menus.py`, replace the entire `ManagePeripheralsAction` class with:

```python
class ManagePluginsAction(TaskAction):
    """Tools-menu action opening the Manage Plugins dialog — a checkbox per
    registered optional plugin group (bundled + installed). Applies the
    selection on OK via PluginGroupManager.apply. TaskAction so self.task is
    populated; lives in the always-loaded task."""

    id = "manage_plugins_action"
    name = "&Manage Plugins…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Manage Plugins: no task available")
            return
        from microdrop_application.plugin_group_manager import PluginGroupManager
        from microdrop_application.plugins_manager_dialog import PluginsManagerModel

        manager = task.window.application.get_service(PluginGroupManager)
        if manager is None:
            logger.error("Manage Plugins: PluginGroupManager service not found")
            return

        groups = [
            (name, group.label or name, group.loaded)
            for name, group in manager.groups.items()
        ]
        model = PluginsManagerModel(groups)
        ui = model.edit_traits(kind="livemodal")
        if not ui.result:                       # Cancel / closed -> no change
            return
        try:
            manager.apply(task, model.desired())
        except Exception:
            logger.exception("Manage Plugins: applying group changes failed")


class InstallPluginAction(TaskAction):
    """Tools-menu action: pick a .microdrop_plugin archive and install it.
    Shows an informed-consent dialog (what will be installed + a third-party
    code warning) before extracting, then registers its groups live."""

    id = "install_plugin_action"
    name = "&Install Plugin…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Install Plugin: no task available")
            return
        from microdrop_application.dialogs.pyface_wrapper import (
            file_dialog, confirm, information, error as error_dialog, YES,
        )
        from microdrop_application.plugin_group_manager import PluginGroupManager
        from microdrop_application.plugins import installer

        path = file_dialog(
            parent=None, action="open",
            wildcard="MicroDrop plugin (*.microdrop_plugin)|*.microdrop_plugin",
        )
        if not path:
            return

        manager = task.window.application.get_service(PluginGroupManager)
        if manager is None:
            logger.error("Install Plugin: PluginGroupManager service not found")
            return

        def _consent(manifest):
            classes = "<br>".join(
                f"&nbsp;&nbsp;{p}" for g in manifest.groups for p in g.plugins
            )
            pkgs = ", ".join(manifest.packages)
            body = (
                f"<b>{manifest.label}</b> (v{manifest.version or '?'})<br><br>"
                f"Packages: {pkgs}<br>"
                f"Plugin classes that will become importable:<br>{classes}<br><br>"
                f"<b>Warning:</b> installing runs third-party code that has not "
                f"been verified. Only install plugins you trust.<br><br>"
                f"Install this plugin?"
            )
            return confirm(parent=None, message=body,
                           title="Install Plugin?", cancel=False) == YES

        try:
            manifest = installer.install_from_zip(path, manager, confirm=_consent)
        except installer.InstallCancelled:
            return
        except Exception as e:
            error_dialog(parent=None, title="Install failed", message=str(e))
            return

        information(
            parent=None, title="Plugin installed",
            message=f"Installed <b>{manifest.label}</b>.<br><br>"
                    f"Enable it from Tools → Manage Plugins.",
        )
```

- [ ] **Step 4: Compile**

Run: `python -m py_compile microdrop_application/menus.py`
Expected: no output.

- [ ] **Step 5: Import + introspection smoke (Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import microdrop_application.menus as mn
print(\"manage:\", mn.ManagePluginsAction().name)
print(\"install:\", mn.InstallPluginAction().name)
print(\"no is_peripheral helpers:\", not hasattr(mn, \"is_peripheral_ui_enabled\") and not hasattr(mn, \"is_peripheral_backend_enabled\"))
print(\"no ManagePeripheralsAction:\", not hasattr(mn, \"ManagePeripheralsAction\"))
'"
```
Expected: `manage: &Manage Plugins…`, `install: &Install Plugin…`, `no is_peripheral helpers: True`, `no ManagePeripheralsAction: True`.

- [ ] **Step 6: Commit**

```bash
git add microdrop_application/menus.py
git commit -m "Add Install Plugin + Manage Plugins menu actions (replace magnet toggle)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Menu wiring + startup discovery + generic restore

**Files:**
- Modify: `microdrop_application/task.py`

**Interfaces:**
- Consumes: Task 2 `paths.ensure_on_sys_path`; Task 4 `PluginGroupManager`; Task 7 actions.
- Produces: Tools menu carries `InstallPluginAction()` + `ManagePluginsAction()`; `_restore_enabled_plugin_groups()` (replaces `_restore_peripherals_if_enabled`).

- [ ] **Step 1: Swap the consts + menus imports**

In `microdrop_application/task.py`, replace:

```python
from .consts import PKG, MAGNET_UI_GROUP, MAGNET_BACKEND_GROUP
```

with:

```python
from .consts import PKG
```

and replace:

```python
from .menus import (
    AdvancedModeAction, ManagePeripheralsAction,
    is_peripheral_ui_enabled, is_peripheral_backend_enabled,
)
```

with:

```python
from .menus import AdvancedModeAction, ManagePluginsAction, InstallPluginAction
```

- [ ] **Step 2: Wire both actions into the Tools menu**

In `microdrop_application/task.py`, in the `menu_bar = SMenuBar(...)` block, replace:

```python
        SMenu(ManagePeripheralsAction(), id="Tools", name="&Tools"),
```

with:

```python
        SMenu(InstallPluginAction(), ManagePluginsAction(), id="Tools", name="&Tools"),
```

- [ ] **Step 3: Replace the restore call + method**

In `microdrop_application/task.py`, in `activated()`, replace:

```python
        self._restore_peripherals_if_enabled()
```

with:

```python
        self._restore_enabled_plugin_groups()
```

Then replace the entire `_restore_peripherals_if_enabled` method with:

```python
    def _restore_enabled_plugin_groups(self):
        """On launch, make installed plugins importable, then re-enable every
        discovered plugin group whose persisted flag is set — so the Manage
        Plugins checkboxes match what's actually loaded. Registration order
        (bundled first; within the magnet manifest, backend before UI)."""
        from microdrop_application.plugins import paths
        from microdrop_application.helpers import get_microdrop_redis_globals_manager
        from .plugin_group_manager import PluginGroupManager

        paths.ensure_on_sys_path()
        manager = self.window.application.get_service(PluginGroupManager)
        if manager is None:
            logger.warning("plugin restore: PluginGroupManager service not found")
            return
        app_globals = get_microdrop_redis_globals_manager()
        for group_name, group in list(manager.groups.items()):
            if (group.enabled_key
                    and app_globals.get(group.enabled_key, False)
                    and not manager.is_loaded(group_name)):
                logger.info(
                    f"Restoring plugin group '{group_name}' from persisted flag"
                )
                manager.enable(self, group_name)
```

- [ ] **Step 4: Compile**

Run: `python -m py_compile microdrop_application/task.py`
Expected: no output.

- [ ] **Step 5: Import + introspection smoke (Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import microdrop_application.task as t
print(\"restore method:\", hasattr(t.MicrodropTask, \"_restore_enabled_plugin_groups\"))
print(\"old method gone:\", not hasattr(t.MicrodropTask, \"_restore_peripherals_if_enabled\"))
'"
```
Expected: `restore method: True`, `old method gone: True`.

- [ ] **Step 6: Commit**

```bash
git add microdrop_application/task.py
git commit -m "Wire Install/Manage Plugins menu items + generic launch restore

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Remove the superseded magnet consts

**Files:**
- Modify: `microdrop_application/consts.py`, `examples/plugin_consts.py`

**Interfaces:**
- Produces: `consts.py` without `MAGNET_UI_GROUP`/`MAGNET_BACKEND_GROUP`/`PERIPHERAL_UI_ENABLED_KEY`/`PERIPHERAL_BACKEND_ENABLED_KEY`.

- [ ] **Step 1: Confirm nothing still references them**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src && grep -rn "MAGNET_UI_GROUP\|MAGNET_BACKEND_GROUP\|PERIPHERAL_UI_ENABLED_KEY\|PERIPHERAL_BACKEND_ENABLED_KEY" --include=*.py | grep -v "/docs/" || echo "no references"
```
Expected: `no references` (the manifest JSON carries the literal key strings; no `.py` imports them). If anything prints, STOP — it must be migrated to the manifest first.

- [ ] **Step 2: Remove the consts block**

In `microdrop_application/consts.py`, delete this block entirely:

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

- [ ] **Step 3: Point the plugin_consts comment at the manifest**

In `examples/plugin_consts.py`, replace the comment line:

```python
# The optional magnet peripheral is intentionally NOT in the default lists
# below. It is hot loaded/unloaded at runtime from the Tools -> Manage
# Peripherals dialog via PluginGroupManager, as TWO independent groups, so
# users without the magnet hardware aren't burdened with its UI/services and
# each group auto-restores on launch from its persisted flag.
#   - magnet_ui      group: dock pane, status icon, magnet protocol column
#   - magnet_backend group: controller (hardware + connection search)
```

with:

```python
# The optional magnet peripheral is intentionally NOT in the default lists
# below. Its two groups (magnet_backend, magnet_ui) are declared by the bundled
# manifest default_plugins/magnet_peripherals/microdrop_plugin.json and hot
# loaded/unloaded at runtime via the Tools -> Manage Plugins dialog
# (PluginGroupManager). The lists below mirror that manifest for documentation.
```

- [ ] **Step 4: Compile + import smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -m py_compile microdrop_application/consts.py examples/plugin_consts.py && python -c 'import microdrop_application.consts as c; print(\"consts ok, magnet removed:\", not hasattr(c, \"MAGNET_UI_GROUP\"))'"
```
Expected: `consts ok, magnet removed: True`.

- [ ] **Step 5: Commit**

```bash
git add microdrop_application/consts.py examples/plugin_consts.py
git commit -m "Remove superseded magnet group/key consts (manifest is source of truth)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Build the magnet demo archive

**Files:**
- Create: `examples/build_plugin_zip.py`

**Interfaces:**
- Produces: `examples/build_plugin_zip.py` writing `examples/plugins/magnet_peripherals.microdrop_plugin`.

- [ ] **Step 1: Create `build_plugin_zip.py`**

Create `examples/build_plugin_zip.py`:

```python
"""Build the magnet demo archive:
examples/plugins/magnet_peripherals.microdrop_plugin.

Zips the three magnet packages from src/ plus the bundled
default_plugins/magnet_peripherals/microdrop_plugin.json manifest into the
.microdrop_plugin archive — the canonical example of the install format. Test
directories and bytecode are excluded so the archive matches the installer's
allowlist (only the declared packages + the manifest)."""

import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]                      # src/
MANIFEST = SRC / "default_plugins" / "magnet_peripherals" / "microdrop_plugin.json"
OUT_DIR = SRC / "examples" / "plugins"
OUT = OUT_DIR / "magnet_peripherals.microdrop_plugin"
PACKAGES = ["peripheral_controller", "peripheral_protocol_controls", "peripherals_ui"]


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(MANIFEST, "microdrop_plugin.json")
        for pkg in PACKAGES:
            for path in sorted((SRC / pkg).rglob("*")):
                if path.is_dir():
                    continue
                rel_parts = path.relative_to(SRC).parts
                if "__pycache__" in rel_parts or "tests" in rel_parts:
                    continue
                if path.suffix == ".pyc":
                    continue
                zf.write(path, str(path.relative_to(SRC)))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
```

- [ ] **Step 2: Build + verify the archive**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python examples/build_plugin_zip.py && python -c '
import zipfile
from microdrop_application.plugins.manifest import load_manifest
names = zipfile.ZipFile(\"examples/plugins/magnet_peripherals.microdrop_plugin\").namelist()
print(\"has manifest:\", \"microdrop_plugin.json\" in names)
print(\"has controller pkg:\", any(n.startswith(\"peripheral_controller/\") for n in names))
print(\"no tests:\", not any(\"/tests/\" in n for n in names))
print(\"manifest parses:\", load_manifest(zipfile.ZipFile(\"examples/plugins/magnet_peripherals.microdrop_plugin\").read(\"microdrop_plugin.json\")).name)
'"
```
Expected: `has manifest: True`, `has controller pkg: True`, `no tests: True`, `manifest parses: magnet_peripherals`.

- [ ] **Step 3: Commit (script only; ignore the built archive)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src && printf 'examples/plugins/\n' >> .gitignore
git add examples/build_plugin_zip.py .gitignore
git commit -m "Add magnet demo-archive build script (examples/build_plugin_zip.py)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Integration smoke + manual verification

**Files:** none (verification only).

- [ ] **Step 1: Full wiring import smoke (scratch app-home, Redis up)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig
ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdtest_\")
from microdrop_application.plugin_group_manager import PluginGroupManager
from microdrop_application.plugins import installer, paths
from microdrop_application.plugins_manager_dialog import PluginsManagerModel
import microdrop_application.menus as mn, microdrop_application.task as t
m = PluginGroupManager()
print(\"groups:\", list(m.groups))
print(\"actions:\", mn.InstallPluginAction().name, \"|\", mn.ManagePluginsAction().name)
print(\"restore:\", hasattr(t.MicrodropTask, \"_restore_enabled_plugin_groups\"))
print(\"ALL WIRING OK\")
'"
```
Expected: `groups: ['magnet_backend', 'magnet_ui']`, both action names, `restore: True`, `ALL WIRING OK`.

- [ ] **Step 2: Build the demo archive**

Run: `cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python examples/build_plugin_zip.py"`
Expected: `wrote …/magnet_peripherals.microdrop_plugin (… bytes)`.

- [ ] **Step 3: Launch the app (mock device, Redis up)**

Run: `cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python examples/run_device_viewer_pluggable.py --device mock"`

- [ ] **Step 4: Manual checks** (tick each; stop and report on any failure)

- [ ] **Bundled magnet present:** Tools → Manage Plugins lists *Magnet Backend (…)* and *Magnet UI (…)* with checkboxes; enabling Magnet Backend starts the search (logs), Magnet UI mounts the pane + status icon + protocol column + the "Search Connection" submenu. Unchecking each tears them down. (Same behavior as before, now manifest-driven.)
- [ ] **Install picker:** Tools → Install Plugin… opens a file dialog that shows only `*.microdrop_plugin`. A plain `.zip` is not selectable.
- [ ] **Consent + install:** pick `examples/plugins/magnet_peripherals.microdrop_plugin` → the consent dialog lists name/version/packages/plugin classes + the "third-party code" warning → YES → "Plugin installed" dialog. The install lands under `…/Sci-Bots/Microdrop/installed_plugins/magnet_peripherals/`.
- [ ] **Reopen Manage Plugins:** the magnet groups are still listed (re-registered); enabling works.
- [ ] **Reinstall guard:** with a magnet group enabled, Install Plugin… of the same archive is refused with "disable it first" (error dialog); nothing changes.
- [ ] **Rejected archive:** rename any `.zip` to `.microdrop_plugin` with no `microdrop_plugin.json` (or an undeclared top-level file) → Install fails with a clear error and nothing is extracted.
- [ ] **Persistence/restore:** enable a group, restart the app → it auto-loads from its flag and the Manage Plugins checkbox matches.

- [ ] **Step 5: Update project memory**

Append to `C:/Users/Info/.claude/projects/C--Users-Info-PycharmProjects-pixi-microdrop/memory/project_plugin_hot_load_unload.md`: the install-from-zip mechanism (`.microdrop_plugin` archives, `microdrop_plugin.json` manifest, `installed_plugins/` under `ETSConfig.application_home` on `sys.path`, `default_plugins/` for bundled magnet, the `Install Plugin…`/`Manage Plugins…` actions, manifest-driven discovery + lazy `module:Class` resolution, hardening = extension+zip-slip+allowlist+consent, and that envisage's `Package/EggPluginManager` were considered but rejected as deprecated/env-hostile). No repo commit required (memory lives outside the repo).

---

## Self-Review

**Spec coverage:**
- Manifest (§Component 1) → Task 1. ✓
- Paths + discovery (§Component 2) → Task 2; bundled magnet manifest (§Component 6) → Task 3. ✓
- `PluginGroupManager` generalization (§Component 3) → Task 4. ✓
- Installer + hardening (§Component 4, §7 security) → Task 5. ✓
- Manage Plugins dialog (§Component 5) → Task 6; Install/Manage actions (§Component 5) → Task 7; menu wiring + generic restore (§Component 5) → Task 8. ✓
- Consts cleanup (§Component 7) → Task 9. ✓
- Demo archive + build script (§Component 6) → Task 10. ✓
- Verification (§Verification) → Task 11. ✓
- Considered-alternative note (envisage managers) is in the spec; no code task needed. ✓

**Type consistency:** `load_manifest`/`ManifestError`/`PluginManifest`/`PluginGroupSpec` (Task 1) used by Tasks 4, 5. `paths.MANIFEST_FILENAME`/`installed_plugins_dir`/`default_plugins_dir`/`ensure_on_sys_path`/`iter_manifest_dirs` (Task 2) used by Tasks 4, 5, 8. `PluginGroup.plugin_specs`/`label` + `register_manifest`/`_resolve_factories`/`apply`/`is_loaded` (Task 4) used by Tasks 5, 7, 8. `install_from_zip(zip_path, manager, *, confirm, dest_root)` (Task 5) called by Task 7 and the Task 5 smoke. `PluginsManagerModel(groups)`/`desired()`/`grp__<name>` (Task 6) used by Task 7. `InstallPluginAction`/`ManagePluginsAction` (Task 7) used by Task 8. `_restore_enabled_plugin_groups` (Task 8) matches the `activated()` call. The four removed consts (Task 9) are confirmed unreferenced by Task 9 Step 1 before removal.

**Placeholder scan:** none — every code step has full code; every command states expected output.
