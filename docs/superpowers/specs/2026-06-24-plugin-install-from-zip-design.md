# Install plugins from `.microdrop_plugin` archives

**Date:** 2026-06-24
**Status:** Approved (design)
**Builds on:** the two-group hot load/unload work (`feature/peripheral-hot-load`, commits
`19e14ed1`..`a89702f1`) — `PluginGroupManager`, the live dock-pane/menu/status-icon/
preferences refresh, and the Manage-Peripherals dialog. This generalizes that machinery
from hardcoded magnet groups to **manifest-driven groups discovered from disk**, and adds a
zip-based installer.

## Problem & goals

Today the optional magnet plugin group is hardcoded in `PluginGroupManager._groups_default`
and its packages ship in the repo. The user wants to **install plugins from a file at
runtime**: pick an archive in a file dialog, and after install be able to load the plugin
the same way magnet loads. The magnet plugin becomes the worked example, packaged as an
archive.

Goals:
- A **Tools → Install Plugin…** action that opens a file picker (filtered to
  `*.microdrop_plugin`) and installs the selected archive.
- An archive may contain **one or more Python packages** plus a manifest declaring the
  plugin **group(s)** they form.
- After install, the new group(s) appear in a generalized **Manage Plugins** dialog and can
  be enabled/disabled (hot load/unload) exactly like magnet.
- Installs **persist** across restart and **auto-restore** their enabled state.
- Reasonable **security hardening** (no cryptographic signing — internal/trusted-source
  tool): custom extension, path-traversal protection, allowlist extraction, informed
  consent.

Non-goals: cryptographic signature/trust (explicitly deferred), dependency resolution / pip
installs (archives are pure-Python source whose deps are already in the env), remote
distributed backend (unchanged limitation), sandboxing imported code (not feasible
in-process).

## Decisions (locked)

- **Archive = a zip** with extension **`.microdrop_plugin`** and a **`microdrop_plugin.json`**
  manifest at its root.
- **Install location:** a new `installed_plugins/` directory under
  `ETSConfig.application_home` (`…/Sci-Bots/Microdrop/installed_plugins/`, beside
  `preferences.ini` and `.beta_disclaimer_accepted`), added to `sys.path` at startup.
- **Manifest-driven groups:** `PluginGroupManager` discovers groups from manifests in two
  dirs — a bundled repo **`default_plugins/`** and the app-data **`installed_plugins/`** —
  retiring the hardcoded `_groups_default`. Magnet ships as a bundled default manifest
  (code stays in `src/`) and is also built into a demo archive.
- **UI:** a dedicated **Install Plugin…** menu item, and a generalized **Manage Plugins…**
  dialog (replacing Manage Peripherals) that lists *all* registered groups with checkboxes.
- **Security:** hardening only — extension gate, zip-slip protection, allowlist extraction
  (only manifest-declared packages), and an informed-consent dialog. No keys/signing.

## Architecture

```
Tools → Install Plugin…  (InstallPluginAction)
   file_dialog(*.microdrop_plugin) → installer.install_from_zip(path, manager)
     read+validate manifest (no extraction) → validate entries (zip-slip + allowlist)
       → informed-consent dialog (shows name/version/packages/plugin classes + warning)
         → extract allowlisted entries to installed_plugins/<name>/ → ensure_on_sys_path
           → manager.register_manifest(manifest)  (groups appear live)

Tools → Manage Plugins…  (ManagePluginsAction)
   PluginsManagerModel lists ALL manager.groups as checkboxes (seeded from is_loaded)
     → on OK: manager.apply(task, {group_name: bool, …})

Startup (MicrodropTask.activated / app start):
   paths.ensure_on_sys_path()  → manager.discover()  (default_plugins/ + installed_plugins/)
     → restore: enable every group whose enabled_key flag is set (registration order)
```

### Component 1 — Manifest (`microdrop_application/plugins/manifest.py`, new)

`microdrop_plugin.json` schema (at archive root):
```json
{
  "schema_version": 1,
  "name": "magnet_peripherals",
  "label": "Magnet Peripherals",
  "version": "1.0.0",
  "packages": ["peripheral_controller", "peripheral_protocol_controls", "peripherals_ui"],
  "groups": [
    { "name": "magnet_backend", "label": "Magnet Backend (controller + connection search)",
      "plugins": ["peripheral_controller.plugin:PeripheralControllerPlugin"],
      "enabled_key": "microdrop.peripheral_backend_enabled",
      "post_enable_publish_topic": "ZStage/requests/start_device_monitoring" },
    { "name": "magnet_ui", "label": "Magnet UI (dock pane, status icon, protocol column)",
      "plugins": ["peripheral_protocol_controls.plugin:PeripheralProtocolControlsPlugin",
                  "peripherals_ui.plugin:PeripheralUiPlugin"],
      "enabled_key": "microdrop.peripheral_ui_enabled" }
  ]
}
```
- `groups` are listed in **enable order** (magnet backend before UI).
- `plugins` are dotted `module:Class` specs (resolved lazily at enable time — a broken
  plugin module never crashes startup; `post_enable_publish_topic` is a literal topic
  string so the manifest stays data, not code).
- `PluginManifest` and `PluginGroupSpec` are plain `@dataclass`es (inert parsed data — no
  Traits reactivity needed): `PluginManifest(schema_version, name, label, version,
  packages: list[str], groups: list[PluginGroupSpec])`; `PluginGroupSpec(name, label,
  plugins: list[str], enabled_key, post_enable_publish_topic="")`.
- `load_manifest(path_or_bytes) -> PluginManifest`: parse JSON, validate
  `schema_version == 1`, required fields present, `packages`/`groups` non-empty, each
  group has ≥1 plugin spec and a non-empty `enabled_key`. Raises `ManifestError` with a
  clear message on any violation (the installer turns it into an error dialog).

### Component 2 — Paths + discovery (`microdrop_application/plugins/paths.py`, new)

- `installed_plugins_dir() -> Path`: `Path(ETSConfig.application_home)/"installed_plugins"`,
  created if missing.
- `default_plugins_dir() -> Path`: `PROJECT_ROOT/"default_plugins"` (PROJECT_ROOT = `src/`,
  the dir already added to `sys.path` by `microdrop_runner_setup`).
- `ensure_on_sys_path()`: insert `installed_plugins_dir()` onto `sys.path` if absent.
- `iter_manifest_dirs() -> Iterator[Path]`: yields each immediate subdir of
  `default_plugins/` and `installed_plugins/` that contains a `microdrop_plugin.json`.

### Component 3 — `PluginGroupManager` generalization (`plugin_group_manager.py`)

- `PluginGroup`: add `label = Str()`; replace `plugin_factories = List()` with
  `plugin_specs = List(Str)` (dotted `module:Class`). A `_resolve_factories(group)` imports
  every spec via `importlib` (`module`, then `getattr(Class)`); on any failure it raises,
  and `enable()` catches, logs, and aborts that enable (group stays unloaded, flag unset —
  no partial load).
- Retire `_groups_default`. Add:
  - `discover()`: clear/rebuild `groups` from `paths.iter_manifest_dirs()` via
    `load_manifest` + `_add_manifest_groups`.
  - `register_manifest(manifest)`: `_add_manifest_groups(manifest)` for a freshly-installed
    archive (runtime). On a group-name collision: if the existing group **is loaded**,
    refuse (raise) so the caller tells the user to disable it first; else replace the
    registration.
  - `_add_manifest_groups(manifest)`: build a `PluginGroup` per `group` spec
    (`name, label, plugin_specs, enabled_key, post_enable_publish_topic`) and put it in
    `self.groups`.
- `enable()` resolves `plugin_specs → factories` first (Component 3 lazy import), then the
  existing flow (add/start, service capture, dock-pane mount, menu rebuild, post-enable
  publish, set flag) is unchanged.
- `apply(task, desired)` generalizes to **any** groups: enable newly-on groups in
  `groups` registration order; disable newly-off groups in reverse. (Magnet keeps
  backend-before-UI via manifest group order.)

### Component 4 — Installer (`microdrop_application/plugins/installer.py`, new)

`install_from_zip(zip_path, manager, *, confirm=None) -> PluginManifest`:
1. Open `zip_path` with `zipfile`. Read `microdrop_plugin.json` from the root;
   `load_manifest` it (no extraction yet).
2. **Validate every entry** against the manifest, *before extracting*:
   - reject absolute paths, any `..` segment, and symlink entries (zip-slip);
   - **allowlist:** each entry's top-level path component must be `microdrop_plugin.json`
     or one of `manifest.packages`; refuse the whole archive if any entry falls outside
     (so no stray top-level scripts / `sitecustomize.py` / dotfiles get installed).
   Any violation → raise `InstallError` naming the offending entry.
3. **Informed consent:** call `confirm(manifest)` (injected; the action passes a dialog
   callback) showing `name`, `version`, `packages`, and the plugin classes from
   `groups[].plugins` that will become importable, plus a clear "installing runs
   third-party code that has not been verified" warning. If it does not return YES, abort
   (return None / raise `InstallCancelled`).
4. `target = installed_plugins_dir()/manifest.name`. If it exists: if any of the manifest's
   groups `is_loaded`, refuse (raise) — else remove and replace. Extract only the
   allowlisted entries into `target`.
5. `paths.ensure_on_sys_path()`; `manager.register_manifest(manifest)`.
6. Return the manifest (for the success message).

### Component 5 — UI (`menus.py`, new `plugins_manager_dialog.py`, `task.py`)

- **`InstallPluginAction(TaskAction)`** (menus.py): `file_dialog(action="open",
  wildcard="MicroDrop plugin (*.microdrop_plugin)")`; on a chosen path, fetch the
  `PluginGroupManager` service and call `installer.install_from_zip(path, manager,
  confirm=_consent_dialog)`. The consent callback builds the dialog body from the manifest
  via `pyface_wrapper.confirm` (returns YES/NO). On success → `information(...)` ("Installed
  *<label>* — enable it in Manage Plugins"); on `ManifestError`/`InstallError` →
  `error(...)`; on cancel → nothing.
- **`ManagePluginsAction(TaskAction)`** (replaces `ManagePeripheralsAction`): opens
  `PluginsManagerModel`, seeded from `manager.groups`; on OK calls `manager.apply(...)`.
- **`PluginsManagerModel`** (`microdrop_application/plugins_manager_dialog.py`, replaces
  `peripherals_manager_dialog.py`): built from a list of `(group_name, label, loaded)`.
  For each group it `add_trait("grp__"+name, Bool(loaded))`; `traits_view()` builds one
  checkbox `Item` per group (label = `group.label`) + OK/Cancel, `kind="livemodal"`. A
  `desired()` method returns `{name: getattr(self, "grp__"+name)}`. (No Install button
  inside — Install is its own menu item, which avoids live-rebuilding the dynamic
  checkbox list.)
- **`task.py`:** Tools menu gets both `InstallPluginAction()` and `ManagePluginsAction()`.
  `_restore_peripherals_if_enabled` generalizes to `_restore_enabled_plugin_groups`: after
  `paths.ensure_on_sys_path()` + `manager.discover()`, enable every group (in registration
  order) whose `app_globals[group.enabled_key]` flag is set and that isn't already loaded.
- **Startup wiring:** `ensure_on_sys_path()` + `manager.discover()` run before restore, in
  `activated()` (or app start). The Manage Plugins dialog and restore both read the live
  `manager.groups`, so a just-installed plugin shows up immediately and on next launch.

### Component 6 — Magnet as the worked example

- New **`default_plugins/magnet_peripherals/microdrop_plugin.json`** — the manifest above.
  Code stays in `src/` (already importable), so magnet groups are discovered at startup and
  appear in Manage Plugins with no install needed. This replaces the hardcoded
  `_groups_default`.
- New **`examples/build_plugin_zip.py`** — zips the three magnet packages (from `src/`) plus
  a `microdrop_plugin.json` into `examples/plugins/magnet_peripherals.microdrop_plugin`,
  the canonical example of the archive format. Installing it re-registers the magnet groups
  (idempotent replace when not loaded). *Caveat:* the extracted copy is shadowed on
  `sys.path` by the in-`src/` copy — benign for the demo.

### Component 7 — Cross-cutting

- **Persistence:** installs live in `installed_plugins/<name>/`; rediscovered each launch by
  `discover()`. Enabled state persists via each group's `enabled_key` app-global, restored
  on launch.
- **Error handling:** manifest/entry/permission failures raise typed errors
  (`ManifestError`, `InstallError`, `InstallCancelled`) the action turns into dialogs;
  nothing is extracted unless the manifest + all entries validate and consent is given.
  Group enable failures (bad import, partial start) keep the existing log-and-continue /
  abort-this-enable behavior.
- **Security (hardening only):** extension gate + zip-slip + allowlist extraction + informed
  consent. Residual risk — a malicious author shipping bad code inside a *declared* package
  — is mitigated only by the consent gate; documented as an accepted limitation. No
  signing.
- **Consts cleanup:** the magnet group-name / enabled-key constants in
  `microdrop_application/consts.py` and the `is_peripheral_*_enabled` helpers in `menus.py`
  become redundant (the manifest is the source of truth; restore is generic). Remove the
  ones left unreferenced after the generalization; the manifest JSON carries the
  `enabled_key` strings as literals.
- **Testing (project convention — no pytest):** `py_compile` + `pixi` import/introspection
  smokes for `manifest.load_manifest`, `installer.install_from_zip` into a temp dir (build a
  fixture archive, install it, assert the target tree + `manager.groups`), and
  `discover()`; manual GUI for the full install → Manage Plugins → enable flow.

## Files

**New**
- `microdrop_application/plugins/__init__.py`
- `microdrop_application/plugins/manifest.py` — `PluginManifest`, `PluginGroupSpec`, `load_manifest`, `ManifestError`
- `microdrop_application/plugins/paths.py` — install/default dirs, `ensure_on_sys_path`, `iter_manifest_dirs`
- `microdrop_application/plugins/installer.py` — `install_from_zip`, `InstallError`, `InstallCancelled`
- `microdrop_application/plugins_manager_dialog.py` — `PluginsManagerModel` (replaces `peripherals_manager_dialog.py`)
- `default_plugins/magnet_peripherals/microdrop_plugin.json`
- `examples/build_plugin_zip.py` (+ output `examples/plugins/magnet_peripherals.microdrop_plugin`)

**Edit**
- `microdrop_application/plugin_group_manager.py` — `label`/`plugin_specs`, lazy resolve, `discover`/`register_manifest`/`_add_manifest_groups`, generic `apply`, retire `_groups_default`
- `microdrop_application/menus.py` — `InstallPluginAction` + `ManagePluginsAction` (replace `ManagePeripheralsAction`); drop the magnet-specific helpers
- `microdrop_application/task.py` — Tools-menu wiring (two items), generic `_restore_enabled_plugin_groups`, startup `ensure_on_sys_path()`+`discover()`
- `microdrop_application/consts.py` — remove now-unused magnet group/key consts
- `examples/plugin_consts.py` — the magnet doc lists are superseded by the manifest; trim/point at it

**Remove**
- `microdrop_application/peripherals_manager_dialog.py` (replaced by `plugins_manager_dialog.py`)

## Verification (manual, Redis up, `--device mock`)

1. **Bundled magnet via manifest:** launch — Tools → Manage Plugins lists *Magnet Backend* and
   *Magnet UI* (from `default_plugins/`); enabling each behaves exactly as before (backend
   starts the search; UI mounts pane + status icon + column + submenu).
2. **Build the archive:** `pixi run python examples/build_plugin_zip.py` →
   `examples/plugins/magnet_peripherals.microdrop_plugin` exists.
3. **Install flow:** Tools → Install Plugin… → the picker shows only `*.microdrop_plugin` →
   pick the archive → the consent dialog lists name/version/packages/plugin classes + the
   warning → YES → success dialog. Reopen Manage Plugins → the magnet groups are present
   (re-registered).
4. **Rejected archives:** a `.zip` (wrong extension) isn't selectable; a crafted archive
   with a `../evil` entry or an undeclared top-level file is refused with a clear error and
   nothing is extracted.
5. **Persistence/restore:** enable a group, restart → it auto-loads from its flag; the
   installed dir remains under `…/Sci-Bots/Microdrop/installed_plugins/`.
6. **Reinstall guard:** installing while a group from that manifest is enabled is refused
   with "disable it first"; installing while disabled replaces the install cleanly.

## Known limitations (accepted)

- No cryptographic trust — a malicious *declared* package can run code on install; consent
  gate is the only backstop.
- Single-process only (remote backend deferred, unchanged).
- A magnet archive installed over the bundled magnet is shadowed on `sys.path` by the
  in-`src/` copy (benign; the demo exercises the install UX, not code replacement).
- Menu bar / preferences / dock panes refresh live via the existing mechanisms; the same
  accepted caveats apply (full menu-bar swap; panes rebuilt per open).
