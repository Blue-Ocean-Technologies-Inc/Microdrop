# MicroDrop Plugin Development & the Plugin-Management System

A guide for developers: **how MicroDrop installs and loads plugins at runtime**, **how to
build your own installable plugin**, and **which Envisage/Traits/Pyface framework patterns to
reach for** (and the few places we're forced to hand-roll).

Everything described here lives in the top-level **`plugin_management/`** package. It is
contributed to the app as a single self-contained plugin (`PluginManagementPlugin`, in
`FRONTEND_PLUGINS`); `microdrop_application` no longer wires any of it.

---

## Part 1 — How it works

### 1.1 Two concepts: *plugin groups* and *plugin archives*

- A **plugin group** is a named, ordered set of Envisage `Plugin` classes that load and
  unload **together** (e.g. the magnet UI = the protocol-column plugin + the dock-pane
  plugin). A group is the unit you enable/disable.
- A **plugin archive** (`*.microdrop_plugin`, a renamed zip) carries one or more Python
  **packages** plus a **`microdrop_plugin.json` manifest** that declares the groups those
  packages form. Installing an archive makes its packages importable and registers its
  groups.

The manifest — *data, not code* — is the source of truth. It names plugin classes as dotted
`"module:Class"` strings that are imported **lazily, only when a group is enabled**, so a
broken or never-enabled plugin can never break startup or discovery.

### 1.2 The pieces

| Module | Responsibility |
|---|---|
| `manifest.py` | `load_manifest()` parses/validates `microdrop_plugin.json` into `PluginManifest`/`PluginGroupSpec` dataclasses. |
| `paths.py` | Locations: bundled `default_plugins/` (in the repo) and per-user `installed_plugins/` (under `ETSConfig.application_home`, on `sys.path`); `iter_manifest_dirs()` discovery. |
| `installer.py` | `install_from_zip()` (validate → consent → extract) and `uninstall_plugin()` (auto-disable → purge → deregister → delete). |
| `group_manager.py` | `PluginGroupManager` — discovers groups from manifests, and `enable`/`disable`/`apply` them against the live app. The orchestrator. |
| `manage_dialog.py` / `uninstall_dialog.py` | TraitsUI dialog models (checkbox list / dropdown). |
| `menus.py` | The three `TaskAction`s: Install, Uninstall, Manage. |
| `plugin.py` | `PluginManagementPlugin` — offers the manager service, contributes the Tools actions, restores enabled groups on launch. |
| `live_task_extensions.py` | `LiveTaskExtensionsController` — listens to the `TASK_EXTENSIONS` extension point and **reactively, debounced** mounts/unmounts dock panes + rebuilds the menu (via the helpers below) when plugins are loaded/unloaded at runtime. |
| `microdrop_utils/tasks_runtime_helpers.py` | The hand-rolled Qt helpers to mount/unmount a dock pane and rebuild the menu bar on a **live** window (Pyface has no public API for this — see Part 3 §5). |

### 1.3 Discovery (every launch)

`PluginGroupManager.groups` is lazily built (`_groups_default → _discover_groups`) by reading
**every** `microdrop_plugin.json` under `default_plugins/` then `installed_plugins/`
(`paths.iter_manifest_dirs()`). Discovery reads **JSON only** — it never imports plugin code,
so an invalid manifest is logged and skipped, and a broken installed plugin is inert until
someone tries to enable it. Each group records its `source_dir` so the manager can later tell
**installed** plugins (under `installed_plugins/`, uninstallable) from **bundled** ones (under
`default_plugins/`, disable-only).

### 1.4 Install (`Tools → Install Plugin…`)

`InstallPluginAction` → file picker (`*.microdrop_plugin`) → `installer.install_from_zip`:

1. `zipfile.is_zipfile` sanity check.
2. Read + `load_manifest` the root `microdrop_plugin.json` **in memory** (no extraction yet).
3. **Validate every entry** (`_validate_entries`): reject absolute paths, any `..` segment,
   symlink entries (zip-slip); allow only entries whose top-level component is the manifest
   or one of the **declared `packages`** (allowlist). Returns the safe member list.
4. **Informed consent**: a dialog lists the name/version/packages/plugin classes + a
   "this runs third-party code" warning (manifest fields HTML-escaped). Decline ⇒ abort.
5. Refuse if any of the manifest's groups is currently **loaded** (reinstall guard).
6. **Atomic, restorable extract**: extract the allowlisted members into a staging dir, rename
   any prior install aside as a backup, swap staging in, delete the backup on success / restore
   it on failure (Windows-safe — `replace()` can fail on a locked file).
7. `ensure_on_sys_path()` + `manager.register_manifest(manifest, source_dir)` so the new
   groups appear immediately.

Security is **hardening only, no cryptographic trust** (deliberate for an internal tool):
extension gate + zip-slip + allowlist + consent. A malicious *declared* package can still run
code on install — the consent gate is the backstop.

### 1.5 Enable = hot load (`PluginGroupManager.enable(task, group_name)`)

1. `_resolve_factories` imports each `"module:Class"` spec (abort cleanly if any import
   fails — no partial load).
2. Snapshot `service_registry._services` keys; for each factory: `application.add_plugin` +
   `application.start_plugin`; capture the **new** service ids (the before/after diff).
3. Publish `post_enable_publish_topic` if set (e.g. the magnet backend kicks off its
   hardware search).
4. Set the group's `enabled_key` app-global flag (persists the "on" state).

The plugins' **dock panes and menu contributions are mounted/rebuilt reactively** — *not* in
`enable()`. `add_plugin`/`start_plugin` makes each plugin's `TASK_EXTENSIONS` contribution
appear; `LiveTaskExtensionsController` (a listener on that extension point) **debounces** and,
on the next GUI-loop turn, mounts the new panes via `add_dock_pane_live` and rebuilds the menu
**once** (see §1.8 and Part 3 §5). So `enable()` owns only plugin + service lifecycle.

**Disable** reverses the lifecycle: `stop_plugin` + `remove_plugin` in reverse → **unregister
the captured services** → clear the flag. Withdrawing each plugin's `TASK_EXTENSIONS` triggers
the same reactive controller to unmount its panes and rebuild the menu.

### 1.6 Uninstall (`Tools → Uninstall Plugin…`)

`installer.uninstall_plugin(task, manager, name)`: not-installed guard → **auto-disable** any
loaded group → `_purge_package_modules` (drop the packages from `sys.modules` so a reinstall
gets fresh code, and to release `.pyd` handles before deletion) → `deregister_plugin` (drop
the groups + clear their flags via an `in`-guarded `del` on the app-globals proxy, which has
no `pop`) → `shutil.rmtree` the install dir. Bundled plugins are never offered for uninstall.

### 1.7 Launch restore

`PluginManagementPlugin._on_application_initialized` (observing the
`application:application_initialized` event, with an `active_window` fallback) runs once the
GUI window exists: `ensure_on_sys_path()`, then `manager.enable(task, group)` for every group
whose persisted flag is set — so the Manage Plugins checkboxes match what's actually loaded
after a relaunch.

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
  services/ …      # optional service implementations
```

### 2.2 The manifest — `microdrop_plugin.json`

Validated by `manifest.load_manifest`. Schema (`schema_version` must be `1`):

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

Field reference:

| Field | Req | Meaning |
|---|---|---|
| `schema_version` | yes | Must be `1`. |
| `name` | yes | Unique id; also the install dir name (`installed_plugins/<name>/`). |
| `label` | no | Human name shown in dialogs (defaults to `name`). |
| `version` | no | Free-form string. |
| `packages` | yes | Non-empty list of the **top-level package directories** the archive carries. The installer's allowlist extracts only these (+ the manifest). |
| `groups` | yes | Non-empty list of groups (below). |
| `groups[].name` | yes | Unique group id (the enable/disable unit). |
| `groups[].label` | no | Shown in Manage Plugins (defaults to `name`). |
| `groups[].plugins` | yes | Ordered `"module:Class"` strings — the Envisage `Plugin` classes, imported lazily on enable, started in this order (stopped in reverse). |
| `groups[].enabled_key` | yes | App-global flag key persisting the on/off state (e.g. `"microdrop.<x>_enabled"`). |
| `groups[].post_enable_publish_topic` | no | A pub/sub topic published (empty message) right after enable — e.g. to start hardware monitoring. |

**Grouping & order tips:** list groups in **enable order** (backend before UI, so services/
topics exist before consumers). Put plugins that must come up together in one group; split
independently-toggleable concerns (UI vs backend) into separate groups.

### 2.3 Build the archive

A `*.microdrop_plugin` is just a zip with `microdrop_plugin.json` at its root and the declared
packages as top-level dirs. See `examples/build_plugin_zip.py` for the canonical builder
(it excludes `__pycache__`, `tests`, and `.pyc` so the archive matches the allowlist):

```python
import zipfile
from pathlib import Path
SRC = Path(__file__).resolve().parents[1]   # src/
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(MANIFEST, "microdrop_plugin.json")
    for pkg in PACKAGES:
        for p in sorted((SRC / pkg).rglob("*")):
            if p.is_dir() or "__pycache__" in p.parts or "tests" in p.parts or p.suffix == ".pyc":
                continue
            zf.write(p, str(p.relative_to(SRC)))
```
Ship the resulting file; a user installs it via **Tools → Install Plugin…**.

### 2.4 Bundled vs installed

- **Bundled:** drop a `default_plugins/<name>/microdrop_plugin.json` in the repo (the code
  stays in `src/`, already importable). It's discovered at startup and shows in Manage Plugins
  with no install — and can be **disabled but not uninstalled**. This is how magnet ships.
- **Installed:** built into an archive and installed at runtime into `installed_plugins/<name>/`
  (on `sys.path`); fully uninstallable.

### 2.5 What your plugin should implement

- **`start(self)` / `stop(self)`** — acquire/release runtime resources. Because your plugin can
  be **hot-unloaded**, `stop()` must fully tear down: stop background schedulers/threads, drop
  Dramatiq actor references, remove any app-globals you own, disconnect Qt signals. (See
  `peripheral_controller`'s `stop()` → `shutdown_monitoring()` + `cleanup()`.)
- **Dock pane?** Contribute it via `TaskExtension(dock_pane_factories=[...])` (§2.6). For
  hot-load to mount it cleanly, give the pane a `destroy()` that undoes anything it wired into
  longer-lived objects (status bar, the global theme signal) — and an optional
  `on_live_mounted(self)` hook, which `add_dock_pane_live` calls after mounting (used by the
  peripheral pane to install its status-bar icon, since the usual
  `task:window:status_bar_manager` observer never fires on a hot-mount).
- **Contributing to an extension point that's consumed live?** (e.g. a protocol column.) Just
  declare `List(contributes_to=THE_ID)` — the consumer reacts if it opted into live events
  (§ Part 3 §1). You don't need to do anything special on the contributing side.
- **`enabled_key`** is owned by the manifest, not your plugin code. Your plugin doesn't read
  it; the manager sets/clears it.

### 2.6 Minimal worked example

`my_widget/plugin.py`:
```python
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from traits.api import List, Str
from microdrop_application.consts import PKG as APP_PKG

class MyWidgetPlugin(Plugin):
    id = "my_widget.plugin"
    name = "My Widget Plugin"
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)
    task_id = Str(f"{APP_PKG}.task")

    def _contributed_task_extensions_default(self):
        from .dock_pane import MyWidgetDockPane
        return [TaskExtension(task_id=self.task_id, dock_pane_factories=[MyWidgetDockPane])]

    def start(self):  ...   # acquire resources
    def stop(self):   ...   # release EVERYTHING (hot-unload safe)
```
`my_widget/microdrop_plugin.json`:
```json
{ "schema_version": 1, "name": "my_widget", "label": "My Widget", "version": "0.1.0",
  "packages": ["my_widget"],
  "groups": [ { "name": "my_widget", "label": "My Widget",
                "plugins": ["my_widget.plugin:MyWidgetPlugin"],
                "enabled_key": "microdrop.my_widget_enabled" } ] }
```
Zip `my_widget/` + the manifest into `my_widget.microdrop_plugin`, install, enable — the dock
pane mounts live.

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

The architecture deliberately favors a **data manifest + lazy `module:Class` imports** over a
scan-and-import discovery (the deprecated `PackagePluginManager` pattern) — it gives
installability without importing untrusted code at discovery, and it sidesteps the pip/wheel +
entry-points path that fights a pixi-managed env. See
`docs/superpowers/specs/2026-06-24-plugin-install-from-zip-design.md` for that rationale.
