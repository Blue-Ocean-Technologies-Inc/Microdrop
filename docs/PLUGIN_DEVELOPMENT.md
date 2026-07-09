# MicroDrop Plugin Development & the Plugin-Management System

A guide for developers: **how MicroDrop installs and loads plugins at runtime**, **how to
build your own installable plugin**, and **which Envisage/Traits/Pyface framework patterns to
reach for** (and the few places we're forced to hand-roll).

Everything described here lives in the top-level **`plugin_management/`** package. It is
contributed to the app as a single self-contained plugin (`PluginManagementPlugin`, in
`FRONTEND_PLUGINS`); `microdrop_application` no longer wires any of it.

---

## Part 1 — How it works

### 1.1 Two concepts: *plugin groups* and *conda packages*

- A **plugin group** is a named, ordered set of Envisage `Plugin` classes that load and
  unload **together** (e.g. the magnet UI = the protocol-column plugin + the dock-pane
  plugin). A group is the unit you enable/disable.
- A **conda package** (built as a `pixi-build-python` package and shipped as a `.conda`
  artifact) carries one or more Python **packages** plus a **`microdrop_plugin.toml` manifest**
  as package data that declares the groups those packages form. Installing a conda package
  lets `pixi` resolve all its dependencies and makes its groups discoverable.

The manifest — *data, not code* — is the source of truth. It names plugin classes as dotted
`"module:Class"` strings that are imported **lazily, only when a group is enabled**, so a
broken or never-enabled plugin can never break startup or discovery.

### 1.2 The pieces

| Module | Responsibility |
|---|---|
| `manifest.py` | `manifest_from_dict()` parses/validates a TOML dict into `PluginManifest`/`PluginGroupSpec` dataclasses. |
| `paths.py` | Locations: `plugin_index_file()` — the app-data cache file (JSON) for the last-fetched channel package list, under `ETSConfig.application_home`. |
| `package_installer.py` | `search_channel()` / `read_cached_index()` (channel discovery + cache), `install_from_channel()` (register channel + `pixi add` + rollback), `uninstall_package()` (`pixi remove`). |
| `entry_point_discovery.py` | `discover_entry_point_manifests()` — reads every `microdrop.plugins` entry point, loads its `microdrop_plugin.toml`, and returns `[(PluginManifest, dist_name)]`. |
| `group_manager.py` | `PluginGroupManager` — discovers groups from entry points, and `enable`/`disable`/`apply` them against the live app. The orchestrator. |
| `manage_dialog.py` / `uninstall_dialog.py` | TraitsUI dialog models (checkbox list / dropdown). |
| `menus.py` | The three `TaskAction`s: Install, Uninstall, Manage. |
| `plugin.py` | `PluginManagementPlugin` — offers the manager service, contributes the Tools actions, restores enabled groups on launch. |
| `live_task_extensions.py` | `LiveTaskExtensionsController` — listens to the `TASK_EXTENSIONS` extension point and **reactively, debounced** mounts/unmounts dock panes + rebuilds the menu (via the helpers below) when plugins are loaded/unloaded at runtime. |
| `microdrop_utils/tasks_runtime_helpers.py` | The hand-rolled Qt helpers to mount/unmount a dock pane and rebuild the menu bar on a **live** window (Pyface has no public API for this — see Part 3 §5). |

### 1.3 Discovery (every launch)

`PluginGroupManager.groups` is lazily built (`_groups_default → _discover_groups`) by calling
`entry_point_discovery.discover_entry_point_manifests()`, which iterates
`importlib.metadata.entry_points(group="microdrop.plugins")`. For each entry point it reads the
package's `microdrop_plugin.toml` resource **without importing the plugin code** — so a broken
or never-enabled plugin is inert until someone tries to enable it.

Each resulting `PluginGroup` carries a `dist_name` (the owning Python distribution). The
manager uses this to classify **installed** plugins (distribution is NOT the app's own
`microdrop_py`) from **bundled** ones (distribution IS `microdrop_py`, disable-only). The
magnet peripheral is bundled this way: its entry point is declared on `microdrop_py` and its
`microdrop_plugin.toml` lives in `peripheral_controller/`.

### 1.4 Install (`Tools → Install Plugin…`)

`InstallPluginAction` opens the **Browse Plugins** dialog (`browse_view.py` /
`BrowsePluginsHandler` / `BrowsePluginsModel`). On open, `model.fetch_data` runs on a
worker thread:

1. **Discover**: `package_installer.search_channel(channel_url=PLUGIN_CHANNEL_URL)` (where
   `PLUGIN_CHANNEL_URL = "https://prefix.dev/microdrop-plugins"`) runs
   `pixi search "*" -c <url> --json`, flattens the per-subdir lists, writes the result to
   `paths.plugin_index_file()` (app-data JSON cache), and returns `list[dict]`. On network
   failure the dialog falls back to `package_installer.read_cached_index()` (returns `[]`
   if absent/malformed) and shows an "Offline" notice.
2. The dialog shows a table of name/version. Selecting a row and clicking **More details**
   fills the details panel. Clicking **Install** shows a consent dialog naming the package,
   version, and dependencies, with a third-party-code warning.
3. **Install**: `package_installer.install_from_channel(name, channel_url=PLUGIN_CHANNEL_URL)`:
   1. Snapshot `pyproject.toml` + `pixi.lock`.
   2. Register the channel (idempotent) — `pixi workspace channel add <url>`.
   3. `pixi add <name>` — the conda solver resolves the plugin + all its `run-dependencies`
      and installs them into the default env.
   4. On any failure: restore the snapshot and re-raise.
   5. Returns `InstallResult(name, requires_relaunch=True)`.
4. A relaunch dialog is offered (a running interpreter can't import newly-installed
   packages).

Security is **hardening only, no cryptographic trust** (deliberate for an internal tool):
the consent gate is the backstop — installing a conda package runs third-party code.

### 1.5 Enable = hot load (`PluginGroupManager.enable(application, group_name)`)

1. `_resolve_factories` imports each `"module:Class"` spec (abort cleanly if any import
   fails — no partial load).
2. Snapshot `service_registry._services` keys; for each factory: `application.add_plugin` +
   `application.start_plugin`; capture the **new** service ids (the before/after diff).
3. Publish `post_enable_publish_topic` if set (e.g. the magnet backend kicks off its
   hardware search).
4. Persist the group's `enabled_key` flag to the application preferences file
   (survives restarts — app_globals would die with the app-managed Redis).

The plugins' **dock panes and menu contributions are mounted/rebuilt reactively** — *not* in
`enable()`. `add_plugin`/`start_plugin` makes each plugin's `TASK_EXTENSIONS` contribution
appear; `LiveTaskExtensionsController` (a listener on that extension point) **debounces** and,
on the next GUI-loop turn, mounts the new panes via `add_dock_pane_live` and rebuilds the menu
**once** (see §1.8 and Part 3 §5). So `enable()` owns only plugin + service lifecycle.

**Disable** reverses the lifecycle: `stop_plugin` + `remove_plugin` in reverse → **unregister
the captured services** → clear the flag. Withdrawing each plugin's `TASK_EXTENSIONS` triggers
the same reactive controller to unmount its panes and rebuild the menu.

### 1.6 Uninstall (`Tools → Uninstall Plugin…`)

`UninstallPluginAction`: only installed (non-bundled) plugins are listed. For the selected
package: **auto-disable** any loaded groups → `manager.deregister_plugin(name)` (drop groups +
clear flags) → `package_installer.uninstall_package(name)`:

1. `pixi remove <name>` removes the package from the default env.

A relaunch dialog is offered; the package is no longer importable after the relaunch.

### 1.7 Launch restore

`PluginManagementPlugin._restore_groups_on_launch` (observing
`application.application_initialized`) runs once the app is up: it ADOPTS the
startup-composed group plugins, then reconciles every group to its persisted
enabled flag (default enabled) — so the Manage Plugins checkboxes match
what's actually loaded after a relaunch.

### 1.8 The three things Envisage/Pyface don't self-heal

Runtime add/remove of a plugin works, but three layers snapshot at startup and need our help:

1. **Service-offer leak.** `CorePlugin` registers runtime `ServiceOffer`s but discards their
   ids, so we capture them ourselves (the before/after `_services` snapshot) and
   `unregister_service` them on disable.
2. **No runtime dock-pane / menu-bar API.** Pyface Tasks builds both once at window creation
   (`TaskWindow.add_task`). `tasks_runtime_helpers.py` drives Qt directly to add/remove a
   pane and rebuild the menu bar on a live window — and we **trigger it reactively** from a
   `TASK_EXTENSIONS` listener + debounce (`live_task_extensions.py`), not imperatively from the
   manager.
3. **Extension-point snapshots.** A plugin that *consumes* an extension point (the protocol
   tree consuming `PROTOCOL_COLUMNS`) only sees contributions present at its `start()` —
   **unless** it opts into live notifications with `connect_extension_point_traits()` and
   reacts to the `<name>_items` event. The protocol tree does exactly this so the magnet
   column appears/disappears when its plugin group loads/unloads (Part 3 §1).

---

## Part 2 — Creating an installable plugin

### 2.1 What a MicroDrop plugin is

An Envisage `Plugin` subclass (`envisage.api.Plugin`). It contributes to **extension points**
(services, task extensions, actor-topic routing, preferences, protocol columns, …) via traits
tagged `contributes_to=…`, and runs setup/teardown in `start()`/`stop()`. See any existing
package — `manual_controls/`, `peripheral_controller/`, `pluggable_protocol_tree/`.

Standard layout:
```
my_plugin/
  __init__.py
  consts.py        # PKG = '.'.join(__name__.split('.')[:-1]); ACTOR_TOPIC_DICT; topics
  plugin.py        # the Plugin subclass
  microdrop_plugin.toml   # group manifest — shipped as package data
  services/ …      # optional service implementations
```

### 2.2 The package manifest — `microdrop_plugin.toml`

Parsed by `manifest.manifest_from_dict`. Ship it as **package data** (in the importable
package directory, not at the repo root). Schema (`schema_version` must be `1`; the
package version is NOT declared here — it lives in `pyproject.toml` and is read from
the installed distribution via `importlib.metadata`):

```toml
schema_version = 1
name = "magnet_peripherals"
label = "Magnet Peripherals"
packages = ["peripheral_controller", "peripheral_protocol_controls", "peripherals_ui"]

[[groups]]
name = "magnet_backend"
label = "Magnet Backend (controller + connection search)"
plugins = ["peripheral_controller.plugin:PeripheralControllerPlugin"]
enabled_key = "microdrop.peripheral_backend_enabled"
post_enable_publish_topic = "ZStage/requests/start_device_monitoring"

[[groups]]
name = "magnet_ui"
label = "Magnet UI (dock pane, status icon, protocol column)"
plugins = [
    "peripheral_protocol_controls.plugin:PeripheralProtocolControlsPlugin",
    "peripherals_ui.plugin:PeripheralUiPlugin",
]
enabled_key = "microdrop.peripheral_ui_enabled"
```

Field reference:

| Field | Req | Meaning |
|---|---|---|
| `schema_version` | yes | Must be `1`. |
| `name` | yes | Unique manifest id (used in dialogs and deregistration). |
| `label` | no | Human name shown in dialogs (defaults to `name`). |
| `version` | no | Free-form string. |
| `packages` | yes | Non-empty list of importable top-level packages this manifest covers. |
| `groups` | yes | Non-empty list of `[[groups]]` tables (below). |
| `groups[].name` | yes | Unique group id (the enable/disable unit). |
| `groups[].label` | no | Shown in Manage Plugins (defaults to `name`). |
| `groups[].plugins` | yes | Ordered `"module:Class"` strings — the Envisage `Plugin` classes, imported lazily on enable, started in this order (stopped in reverse). |
| `groups[].enabled_key` | yes | Key persisting the on/off state in the application preferences file (e.g. `"microdrop.<x>_enabled"`). |
| `groups[].post_enable_publish_topic` | no | A pub/sub topic published (empty message) right after enable — e.g. to start hardware monitoring. |

**Grouping & order tips:** list groups in **enable order** (backend before UI, so services/
topics exist before consumers). Put plugins that must come up together in one group; split
independently-toggleable concerns (UI vs backend) into separate groups.

### 2.3 The `pyproject.toml` — packaging as a conda package

A MicroDrop plugin is a **`pixi-build-python` conda package**. The `pyproject.toml` at your
package root needs four sections:

```toml
[project]
name = "my_widget"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []            # pip/wheel deps (conda deps go in run-dependencies below)

[project.entry-points."microdrop.plugins"]
my_widget = "my_widget"      # value = the importable package containing microdrop_plugin.toml

[build-system]
build-backend = "hatchling.build"
requires = ["hatchling"]

[tool.hatch.build.targets.wheel]
packages = ["my_widget"]

# --- pixi build sections (required for pixi-build-python) ---

[tool.pixi.package]
name = "my_widget"
version = "0.1.0"

[tool.pixi.package.build.backend]
name = "pixi-build-python"
version = "0.*"
channels = ["https://prefix.dev/conda-forge"]

[tool.pixi.package.host-dependencies]
hatchling = "*"

[tool.pixi.package.run-dependencies]
# third-party conda dependencies your plugin needs, e.g.:
# scipy = ">=1.10"
```

Key points:
- `[tool.pixi.package]` (not bare `[package]`) is required by pixi 0.63+.
- Third-party dependencies go in `[tool.pixi.package.run-dependencies]` — the conda solver
  resolves them at install time. Do NOT expect them to be present in the base MicroDrop env.
- The entry-point value (`"my_widget"`) is the importable package name; discovery uses
  `ep.module` to find and load `microdrop_plugin.toml` from that package.

### 2.4 Build the conda package

```bash
pixi build --path <plugin_pkg_dir> --output-dir <out_dir>
```

This produces a `<name>-<version>-<build>.conda` artifact. See
`examples/build_plugin_conda.py` for a one-command builder for the demo plugin:

```python
import subprocess
from pathlib import Path

PKG = Path(__file__).resolve().parent / "demo_plugins" / "scipy_analysis_pkg"
subprocess.run(
    ["pixi", "build", "--path", str(PKG), "--output-dir", "dist_plugins"],
    check=True,
)
```

Run it as: `pixi run python examples/build_plugin_conda.py [output_dir]`

Publish the resulting `.conda` artifact to `PLUGIN_CHANNEL_URL`; users discover and install
it via **Tools → Install Plugin… → Browse Plugins** dialog.

### 2.5 Bundled vs installed

- **Bundled:** the plugin's packages are part of the main `microdrop_py` distribution (code
  lives in `src/`). Add a `[project.entry-points."microdrop.plugins"]` entry to the **main**
  `microdrop-py/pyproject.toml` and ship `microdrop_plugin.toml` inside the importable
  package. Discovered at startup, shown in Manage Plugins — can be **disabled but not
  uninstalled**. This is how magnet ships (`microdrop_plugin.toml` in `peripheral_controller/`,
  entry point on `microdrop_py`).
- **Installed:** built into a `.conda` artifact and installed at runtime via `pixi add`;
  `dist_name` is NOT `microdrop_py`, so it is fully uninstallable via Uninstall Plugin….

### 2.6 What your plugin should implement

- **`start(self)` / `stop(self)`** — acquire/release runtime resources. Because your plugin can
  be **hot-unloaded**, `stop()` must fully tear down: stop background schedulers/threads, drop
  Dramatiq actor references, remove any app-globals you own, disconnect Qt signals. (See
  `peripheral_controller`'s `stop()` → `shutdown_monitoring()` + `cleanup()`.)
- **Dock pane?** Contribute it via `TaskExtension(dock_pane_factories=[...])` (§2.7). For
  hot-load to mount it cleanly, give the pane a `destroy()` that undoes anything it wired into
  longer-lived objects (status bar, the global theme signal) — and an optional
  `on_live_mounted(self)` hook, which `add_dock_pane_live` calls after mounting (used by the
  peripheral pane to install its status-bar icon, since the usual
  `task:window:status_bar_manager` observer never fires on a hot-mount).
- **Contributing to an extension point that's consumed live?** (e.g. a protocol column.) Just
  declare `List(contributes_to=THE_ID)` — the consumer reacts if it opted into live events
  (Part 3 §1). You don't need to do anything special on the contributing side.
- **`enabled_key`** is owned by the manifest, not your plugin code. Your plugin doesn't read
  it; the manager sets/clears it.

### 2.7 Minimal worked example — `scipy_analysis_pkg`

The canonical demo is `examples/demo_plugins/scipy_analysis_pkg/`. It adds a dock pane that
uses `scipy` (not in MicroDrop's base env) to plot random distributions.

**File layout:**
```
scipy_analysis_pkg/
  pyproject.toml
  scipy_analysis/
    __init__.py
    consts.py
    microdrop_plugin.toml    ← package data, discovered via entry point
    plugin.py
    dock_pane.py
```

**`scipy_analysis/microdrop_plugin.toml`:**
```toml
schema_version = 1
name = "scipy_analysis"
label = "Scipy Random Analysis (conda-package spike)"
packages = ["scipy_analysis"]

[[groups]]
name = "scipy_analysis"
label = "Scipy Random Analysis (dock pane)"
plugins = ["scipy_analysis.plugin:ScipyAnalysisPlugin"]
enabled_key = "microdrop.scipy_analysis_enabled"
```

**`scipy_analysis/plugin.py`:**
```python
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from traits.api import List, Str

from microdrop_application.consts import PKG as APP_PKG


class ScipyAnalysisPlugin(Plugin):
    id = "scipy_analysis.plugin"
    name = "Scipy Analysis Plugin"

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)
    task_id = Str(f"{APP_PKG}.task")

    def _contributed_task_extensions_default(self):
        from .dock_pane import ScipyAnalysisDockPane    # lazy — scipy imported here
        return [TaskExtension(task_id=self.task_id,
                              dock_pane_factories=[ScipyAnalysisDockPane])]
```

Build → install → relaunch → enable in Manage Plugins → the dock pane mounts live. The
`scipy` dependency is declared in `[tool.pixi.package.run-dependencies]` and is resolved by
the conda solver at install time; it is NOT imported at plugin resolution (only inside
`_contributed_task_extensions_default`, so enabling fails cleanly until `scipy` is available).

---

## Part 3 — Framework patterns (and where we must hand-roll)

Researched against the installed `envisage`/`pyface`/`traits` under `.pixi/envs/default/…`.
Bottom line: most of our machinery already uses the canonical idioms; **one** area (live menu/
dock-pane mutation) genuinely has no framework alternative.

### §1 React to extension-point changes at runtime — the key trick

This is how a consumer plugin (the protocol tree) sees a contribution (the magnet column)
appear/disappear at runtime. `connect_extension_point_traits()`
(`envisage/extension_point.py:45`) registers listeners on the extension *registry*; when a
contribution changes, it fires a **synthetic** `<name>_items` event
(`extension_point.py:149,159`). Canonical pattern (Envisage uses it itself in
`core_plugin.py:84,117`; the repo in `message_router/plugin.py`):

```python
class MyPlugin(Plugin):
    my_ep = ExtensionPoint(List(IColumn), id="my.ep.id")   # declares the EP + a live list trait

    def start(self):
        super().start()
        self.connect_extension_point_traits()              # OPT IN — Envisage never calls this for you
        self._apply(added=list(self.my_ep), removed=[])    # handle the initial set

    @on_trait_change("my_ep_items")                        # NOT @observe — the name is synthetic
    def _on_changed(self, event):                          # event is an ExtensionPointChangedEvent
        self._apply(event.added, event.removed)

    @observe("my_ep")                                      # index-less wholesale replacement (rare)
    def _on_replaced(self, event):
        self._apply(added=event.new, removed=event.old)
```
**Why `on_trait_change`, not `@observe`:** `@observe` validates names against real traits and
rejects `my_ep_items` (no such trait exists); `on_trait_change` does string matching and binds
the synthetic name. **Verdict:** this *is* the framework idiom — keep it.

### §2 Declare / contribute an extension point

- **Offer:** `x = ExtensionPoint(List(SomeType), id="my.id", desc="…")` — both declares the EP
  and gives you a list trait that auto-aggregates all contributions live
  (`core_plugin.py:95` offers `SERVICE_OFFERS` this way).
- **Contribute:** `y = List(SomeType, contributes_to="my.id")` in another plugin (often with a
  `_y_default`). That's all the contributing side does.

### §3 Services — offer, look up, and decouple with an interface

We **decouple consumers from the implementation** with a traits interface: `PluginGroupManager`
is `@provides(IPluginGroupManager)` (`i_plugin_group_manager.py`), the service is offered as
`ServiceOffer(protocol=IPluginGroupManager, factory=…)`, and every consumer looks up
`application.get_service(IPluginGroupManager)` — so the Tools actions, restore hook, and
installer depend only on the interface. The registry **lazily resolves and caches** factory
results (`service_registry.py:251`), so a factory offer is already an effective singleton.
Notes:
- Envisage matches a service by the protocol's **dotted name**, so the offer and every lookup
  must use the *same* protocol object/string (here, `IPluginGroupManager`).
- There is **no** `get_service_by_id` for cross-plugin lookup (`get_service_from_id` takes an
  int assigned at registration). Use the protocol class.
- Nothing auto-binds a service into an `Instance` trait — call `get_service` yourself.
- `Interface.providedBy(obj)` is a *zope* idiom, not traits — don't use it; envisage matching
  is by protocol name, not adaptation.

### §4 Contribute menu actions to a Task

`TaskExtension(task_id="microdrop_application.task", actions=[SchemaAddition(factory=…,
path="MenuBar/Tools")])`, factory returning an `SGroup`/`SMenu` of `TaskAction`s — exactly
what `plugin_management/plugin.py`, `dropbot_tools_menu`, and `manual_controls` do. A
`TaskAction`'s `self.task` is **auto-populated by the framework** (`task_action.py:35`), so
prefer `self.task` over `event.task` and over manually threading `plugin=self`. Because actions
come in via `task_extensions`, they're **always present** and survive `rebuild_menu_bar_live`.

### §5 Live menu-bar / dock-pane mutation — **no framework API exists**

Confirmed against `pyface/tasks/task_window.py`: dock panes + menu bar are built **once** in
`add_task()` (`:197-208`); the only public mutators are whole-task (`add_task`/`remove_task`);
`set_layout`/`reset_layout` only rearrange **existing** panes; the dock-pane toggle group only
flips **visibility**. So `microdrop_utils/tasks_runtime_helpers.py` (which reaches into
`window._active_state`, `state.dock_panes`, `action_manager_builder_factory`, `_get_state`) is
**necessary and unavoidable**. We *trigger* these helpers **reactively** from a debounced
`TASK_EXTENSIONS` listener (`live_task_extensions.py`, §1.5/§1.8) instead of imperatively — the
helpers stay; only the trigger became declarative. Caveat: the helpers depend on **private
Pyface internals** — re-verify on any Pyface upgrade.

### §6 App-lifecycle hooks

`TasksApplication` exposes (`envisage/ui/tasks/tasks_application.py`):
`application_initialized` (Event, fired after the first windows + GUI loop exist), `active_window`
(Instance), and `window_created/opened/closing/closed` (Events). We restore enabled groups with
a single **`@observe("application:active_window")`** (null-guarded) — it fires once the GUI
window is available and, because the restore is idempotent (only enables flagged groups not
already loaded), re-firing on a later window switch is a harmless no-op. This replaced an
earlier `application_initialized` + manual `on_trait_change("active_window")` rewire.

### §7 Traits tricks worth knowing

- **`@observe` extended/`:` syntax** — `@observe("a:b.items")` reacts to list mutations deep in
  an object graph (`task_window.py:439`). Remember the §1 exception: it only binds **real**
  traits, not the synthetic `_items` EP event.
- **`Property` + `@cached_property(observe=…)`** — lazy, auto-invalidated derived state
  (`task_action.py:79`: `dock_pane = Property(Instance(ITaskPane), observe="task")`). Good for
  action enablement derived from the task/window.
- **`_x_default`** — defer expensive/singleton construction to first access (our
  `_my_service_offers_default`, `message_router`'s `_router_actor_default`). Idiomatic for
  service factories and avoiding import-time cost.
- **`dispatch="ui"`** on `@observe`/`on_trait_change` — marshal a handler onto the GUI thread.
  Essential when a plugin receives Dramatiq/Redis messages on a worker thread but must touch Qt
  widgets.
- **`@provides(IFoo)`** — declare interface conformance for cleaner service offer/lookup (§3).

### Summary

| Area | Cleaner framework option? | What we do |
|---|---|---|
| Live extension-point reactions | No — `connect_extension_point_traits()` + `@on_trait_change("..._items")` *is* canonical | Keep |
| Declare/contribute extension points | No | Keep |
| Service offer + lookup | `@provides(IFoo)` interface for decoupling | **Applied** — offer/lookup by `IPluginGroupManager` |
| Menu/action contributions | No — `TaskExtension`+`SchemaAddition`+`SGroup` | Keep; prefer `TaskAction.self.task` |
| **Live menu/dock-pane mutation** | **None — Pyface builds once at window creation** | **Hand-rolled (necessary)** |
| Lifecycle hooks | `@observe("application:active_window")` over the manual rewire | **Applied** |
| Traits tricks | n/a | Adopt `dispatch="ui"`, `Property`+`@cached_property`, `@provides` where useful |

The architecture deliberately favors a **TOML manifest + lazy `module:Class` imports** over a
scan-and-import discovery (the deprecated `PackagePluginManager` pattern) — it gives
installability without importing untrusted code at discovery, and dependency resolution is
delegated to the conda solver via `pixi add`, not custom `sys.path` wiring. See
`docs/superpowers/specs/2026-06-26-plugin-conda-package-migration-design.md` for that
rationale.
