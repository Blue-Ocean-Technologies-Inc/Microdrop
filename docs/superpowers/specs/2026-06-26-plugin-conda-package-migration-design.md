# Full migration: plugins as installed conda packages (entry points + local channel)

**Date:** 2026-06-26
**Status:** Approved (design discussed + approved in conversation)
**Branch:** `feat/plugin_management` (Microdrop submodule)
**Tracks:** Microdrop issue #491. **Builds on:** the validated plugin-as-conda-package spike
(`docs/superpowers/specs/2026-06-26-plugin-as-conda-package-spike-design.md`).

## Problem & goal

The spike proved a MicroDrop plugin can be a real `pixi-build-python` conda package discovered
via Python entry points, with pixi resolving its dependencies natively. This migration makes
that the **only** plugin model and removes the custom machinery it replaces: the
`.microdrop_plugin` zip format, the hardened zip installer, app-data extraction with per-plugin
`sys.path` wiring, the `pixi_env.py` dependency-feature plumbing, and JSON directory discovery.

**Goal:** a plugin author ships a **built `.conda` file**; the user installs it from the UI;
**pixi resolves and installs its dependencies**; after a relaunch the plugin is discovered,
enable-able, and loads with its dock pane — the same end state as today, with far less custom
code.

## Decisions (locked)

- **Plugin = a `pixi-build-python` conda package**, shipped as a built `.conda` artifact.
- **Install = local conda channel + `pixi add`.** The app keeps a local channel dir, drops the
  `.conda` in, indexes it, registers the channel, and `pixi add <pkg>`; the conda solver
  resolves deps. **No `pixi_env.py`.**
- **Discovery = Python entry points only** (`microdrop.plugins`), un-flagged. The
  `default_plugins/` JSON directory discovery is removed.
- **Full replacement, including magnet:** magnet is discovered via an entry point on the main
  `microdrop_py` package; its JSON manifest is deleted.
- **Default environment** (plugins + deps install into it).
- **Front-load the go/no-go (R1):** validate local-channel install before removing anything.

## End state & data flow

```
Install Plugin… → pick <name>.conda
  → copy into app-data plugin_channel/ → index the channel dir
  → register the channel in the workspace (once) → pixi add <name>
       conda solver resolves <name> + its run-dependencies (e.g. scipy) → installs into default env
  → "needs a relaunch" dialog → Yes: relaunch into the default env
After relaunch:
  discovery: importlib.metadata entry_points(group="microdrop.plugins")
    → each → package-data microdrop_plugin.toml → manifest_from_dict → PluginGroup(s)
  Manage Plugins → enable → existing runtime loads the plugins + mounts the dock pane
Uninstall Plugin… → auto-disable group → pixi remove <name> → drop <name>.conda from the channel → relaunch
```

## Components

### 1. Plugin packaging (author side)

A plugin is a `pixi-build-python` conda package, as validated by the spike's
`examples/demo_plugins/scipy_analysis_pkg/`:
- `pyproject.toml` with `[project]` (name, version, `[project.entry-points."microdrop.plugins"]`),
  `[tool.pixi.package]` + `[tool.pixi.package.build.backend] name = "pixi-build-python"`,
  `[tool.pixi.package.host-dependencies] hatchling`, and the plugin's third-party deps in
  `[tool.pixi.package.run-dependencies]` (resolved against conda channels).
- The importable package ships a `microdrop_plugin.toml` (TOML group manifest) as package data.
- The entry-point value is the importable package (`name = "the_package"`); discovery resolves it
  via `ep.module`.

The author runs `pixi build` to produce `<name>-<version>-<build>.conda`. An example builder
`examples/build_plugin_conda.py` (replacing `build_plugin_zip.py`) documents/automates this for
the demo plugin.

### 2. Local channel + install — `plugin_management/package_installer.py` (new)

Replaces the zip `installer.py` and `pixi_env.py`. A Qt-free service that shells out to pixi
with single, deterministic commands (no CLI-output scraping) and snapshots `pyproject.toml` +
`pixi.lock` for rollback.

- **Channel location:** `plugin_management/paths.py` is repurposed to provide
  `plugin_channel_dir()` = `ETSConfig.application_home/plugin_channel/` (created if missing). The
  app-data `installed_plugins/` extraction dir and `iter_manifest_dirs` are removed.
- **`package_name_from_conda(path) -> str`:** read `info/index.json` from the `.conda` (a zstd
  zip) to get the package `name` (do not parse the filename — the build string is unreliable).
- **`install_conda_file(conda_path, *, confirm) -> InstallResult`:**
  1. Validate it's a `.conda` file and readable; read its name.
  2. Informed-consent dialog (name/version + "installs and runs third-party code").
  3. Copy the `.conda` into `plugin_channel_dir()`; **index** the channel dir (generate
     `repodata.json` — exact command settled in R1; `pixi`/`rattler-index`).
  4. Register the channel: ensure `file://<plugin_channel_dir>` is in the workspace channels
     (`pixi workspace channel add …` if absent; idempotent).
  5. `pixi add <name>` — the solver resolves the plugin + its run-dependencies and installs them.
  6. On any failure: restore the pyproject/lock snapshot, remove the copied `.conda`, re-raise.
  7. Return `InstallResult(name, requires_relaunch=True)`.
- **`uninstall_package(name)`:** `pixi remove <name>` (best-effort), then delete the package's
  `.conda`(s) from the channel + re-index. Logged.

Exact pixi invocations (channel add / index / add / remove) are **verified in R1** against
pixi 0.63 / win-64 before the rest of the migration proceeds.

### 3. Discovery — entry-points-only (`entry_point_discovery.py` + `group_manager.py`)

- `entry_point_discovery.enabled()` and the `MICRODROP_ENTRYPOINT_PLUGINS` env gate are removed —
  entry-point discovery is always on.
- `discover_entry_point_manifests()` additionally records each entry point's **distribution**
  name (`ep.dist.name`, normalized) so callers can tell bundled from installed plugins. Its
  return becomes `[(PluginManifest, dist_name)]`.
- `group_manager._discover_groups` builds the group map **only** from
  `discover_entry_point_manifests()`. The `default_plugins/` loop, `paths.iter_manifest_dirs`, and
  `load_manifest`'s file path are gone.
- `PluginGroup.source_dir` is replaced by `dist_name`. `installed_plugins()` returns groups whose
  `dist_name` is **not** the app's own distribution (`microdrop_py` / `microdrop-py`, normalized);
  those are uninstallable. Bundled groups (dist == the app) are disable-only.

### 4. Magnet migration

Magnet code stays in `src/` (it is part of the `microdrop_py` editable install). It becomes a
normally-discovered plugin:
- Add `[project.entry-points."microdrop.plugins"] magnet_peripherals = "peripheral_controller"`
  to the **main** `microdrop-py/pyproject.toml` (committed in the outer repo as part of this
  migration — note this is the one outer-repo change).
- Ship `peripheral_controller/microdrop_plugin.toml` (package data) declaring both groups
  (`magnet_backend`, `magnet_ui`) with their `module:Class` plugins (across the three magnet
  packages), `enabled_key`s, and the backend's `post_enable_publish_topic` — the same content as
  the current `default_plugins/magnet_peripherals/microdrop_plugin.json`, in TOML.
- Delete `default_plugins/magnet_peripherals/microdrop_plugin.json` (and the now-empty
  `default_plugins/` tree).
- Magnet's `dist_name` is `microdrop_py`, so it is correctly bundled/disable-only.

### 5. UI — `menus.py` + dialogs

- **Install Plugin…** (`InstallPluginAction`): file picker for `*.conda` →
  `package_installer.install_conda_file` → relaunch Yes/No dialog (reusing the existing relaunch
  UX copy) → Yes calls `relaunch.relaunch_into_plugins_env` (re-exec; default env).
- **Uninstall Plugin…**: dropdown of installed plugins (from `installed_plugins()`) →
  `package_installer.uninstall_package` → relaunch dialog.
- **Manage Plugins…**: unchanged (enable/disable checkboxes over discovered groups).
- The `.microdrop_plugin` file filter, consent for the zip, and the old install/uninstall code are
  removed.

### 6. Relaunch & isolation

- Install/uninstall change the default env, so a **relaunch** is offered (a running interpreter
  can't import newly-installed packages). `relaunch.py` re-execs the current entry point (the
  absolute-script-path fix stays); since it's the default env, no `-e` is needed.
- **Isolation:** the default environment. Installing a plugin adds it + its deps to the base env
  (accepted, as in the spike; `pixi remove` reverts). A dedicated plugins env is out of scope.

### 7. Removal list (what this migration deletes)

`plugin_management/installer.py`, `plugin_management/pixi_env.py`, the `.microdrop_plugin`
extension gate + zip-slip/allowlist/atomic-extract code, app-data `installed_plugins/` +
`ensure_on_sys_path` + `iter_manifest_dirs`, JSON file loading in `manifest.py` (`load_manifest`;
keep `manifest_from_dict` + the dataclasses), `examples/build_plugin_zip.py`,
`default_plugins/magnet_peripherals/microdrop_plugin.json`, and the
`MICRODROP_ENTRYPOINT_PLUGINS` flag. The existing `examples/demo_plugins/scipy_analysis/` (zip
archive demo) is also removed; the `scipy_analysis_pkg/` conda package becomes the canonical demo.

## R1 — the front-loaded go/no-go

Before deleting anything, validate **local-channel install** end to end against pixi 0.63 /
win-64, using the spike's already-built `scipy_analysis` conda package:
1. `pixi build` the spike package → a `.conda` file.
2. Copy it into a throwaway local channel dir; index it.
3. Register the channel + `pixi add scipy_analysis` in a throwaway/guarded context; confirm the
   solver installs `scipy_analysis` + scipy.
4. `pixi remove scipy_analysis`; confirm clean removal.

Record the exact working commands (channel add, index, add, remove). **If local-channel install
can't be made to work**, STOP and revisit the install mechanic (e.g. direct `.conda` path dep, or
wheel + pypi path) before any teardown. Everything downstream depends on R1.

## Error handling

- Install failures (bad `.conda`, solver conflict, pixi error) restore the pyproject/lock
  snapshot, remove the copied `.conda`, and surface an error dialog — nothing half-applied.
- A solver **conflict** (the plugin's deps can't co-exist with the env) is reported with the pixi
  error; the install is rolled back.
- Discovery is best-effort: a malformed/parse-failing entry-point package is logged and skipped,
  never breaking startup.
- A plugin whose deps aren't yet present (user deferred the relaunch) simply fails to enable
  cleanly via the existing `_resolve_factories` import-abort backstop.

## Files

**New:** `plugin_management/package_installer.py`, `examples/build_plugin_conda.py`,
`peripheral_controller/microdrop_plugin.toml`.
**Edit:** `plugin_management/paths.py` (channel dir; drop app-data/discovery), `manifest.py`
(drop JSON file-loading), `entry_point_discovery.py` (always-on; record `dist`),
`group_manager.py` (entry-points-only discovery; `dist_name`; `installed_plugins`), `menus.py`
(`.conda` install/uninstall), `uninstall_dialog.py`/`manage_dialog.py` (installed-package list),
`plugin.py` (service/restore wiring as needed), the main outer `microdrop-py/pyproject.toml`
(magnet entry point).
**Remove:** `installer.py`, `pixi_env.py`, `examples/build_plugin_zip.py`,
`default_plugins/magnet_peripherals/microdrop_plugin.json`,
`examples/demo_plugins/scipy_analysis/`.

## Verification (no pytest)

`py_compile` + import smokes for the new/edited modules; the **R1** local-channel walk
(guarded/throwaway where it would mutate the real workspace); a headless discovery smoke (magnet +
an installed demo found via entry points; `installed_plugins()` classifies them correctly); and a
manual GUI end-to-end: build the demo `.conda` → Install Plugin → relaunch → enable → scipy dock
pane renders; magnet still enables; Uninstall → `pixi remove` → gone. Mutating pixi steps run only
in guarded/throwaway contexts or are reverted, never silently against the committed workspace.

## Known limitations / out of scope

- Installing a plugin mutates the workspace `pyproject.toml` + `pixi.lock` and the default env
  (inherent to a pixi-managed env; `pixi remove` reverts).
- Single local channel, single (default) environment, single-process/workstation assumption.
- Plugin *authoring* still requires `pixi build`; a one-command author helper is provided but a
  full plugin-author SDK/distribution story (prefix.dev/GitHub channels) is out of scope.
- No cryptographic trust; the consent dialog is the backstop (installing a conda package runs
  third-party code — same risk class as any conda install).
