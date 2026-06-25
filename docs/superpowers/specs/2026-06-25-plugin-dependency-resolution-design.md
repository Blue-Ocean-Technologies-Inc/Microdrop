# Dependency-aware plugin install (pixi feature + relaunch)

**Date:** 2026-06-25
**Status:** Approved (design discussed + approved in conversation)
**Tracks:** Microdrop issue #491 (dependency-resolution section).
**Builds on:** the `plugin_management/` install system.

## Problem & goal

An installed `.microdrop_plugin` plugin may need third-party packages that aren't in our
**pixi-managed** environment. Let an archive declare its dependencies; on install, add them to
the env via pixi, and — because a running interpreter can't safely use newly-installed packages
— **relaunch only when the plugin actually pulled in a dep that isn't already present**, with a
Yes/No dialog.

## Decisions (locked)

- **Direction A:** each dependency-bearing plugin gets its own pixi **feature**
  `plugin-<manifest.name>`; a single environment **`microdrop-plugins`** = default + every such
  feature. The app relaunches into `microdrop-plugins` when needed.
- **Relaunch only when needed:** if every declared dep is already importable in the *current*
  process, no env change and no relaunch — enable as normal.
- **Relaunch UX:** an info dialog with **Yes** (relaunch now) / **No** ("available next launch").
- **Manifest mutation accepted:** a dep-bearing install edits the workspace
  `pyproject.toml` + `pixi.lock` (inherent to pixi); on a failed solve we revert them.

## Why a relaunch is unavoidable

A live Python interpreter can't be trusted to import packages installed mid-run (PATH, compiled
conda libs, import caches), and the plugin's deps are installed into a *different* env
(`microdrop-plugins`) than the one the app launched in. So gaining a dep ⇒ relaunch into
`microdrop-plugins`. The only case needing no relaunch is when the dep is **already importable
now** (the base env or another loaded plugin already provides it).

## Archive addition

A plugin archive **may** include a `pyproject.toml` at its root. We read **only** its dependency
tables, mirroring the main env's shape:
- `[tool.pixi.dependencies]` → conda specs (resolved against our channels).
- `[project.dependencies]` and/or `[tool.pixi.pypi-dependencies]` → PyPI specs.

Everything else in the file is ignored. No `pyproject.toml` / empty dep tables ⇒ today's
behavior (no env change, no relaunch).

**Installer allowlist change:** `pyproject.toml` is added to the extraction allowlist
(`manifest.packages ∪ {microdrop_plugin.json, pyproject.toml}`) and extracted into
`installed_plugins/<name>/` so uninstall and re-checks can read it.

## Components

### 1. `plugin_management/plugin_deps.py` (new) — parse + satisfaction check (Qt-free)

- `read_plugin_dependencies(pyproject_path_or_text) -> PluginDependencies` (a dataclass:
  `conda: list[str]`, `pypi: list[str]`). Parses with `tomllib` (stdlib, 3.11+). Missing
  tables → empty lists.
- `unsatisfied(deps) -> list[str]` — the declared deps **not importable in the current
  process**, checked against normalized `importlib.metadata` distribution names. Because
  dist-name↔import-name and conda-vs-PyPI naming are imperfect, this **errs toward "unsatisfied"**
  when uncertain (worst case: one unnecessary relaunch offer — safe). Empty result ⇒ no relaunch.

### 2. `plugin_management/pixi_env.py` (new) — pixi CLI wrapper (Qt-free service)

Thin `subprocess` wrapper around the pixi commands (run from the workspace root). All commands
are non-interactive (`--no-progress`, no TTY).
- `FEATURE_PREFIX = "plugin-"`, `PLUGINS_ENV = "microdrop-plugins"`;
  `feature_name(manifest_name) -> "plugin-<name>"`.
- `add_plugin_dependencies(manifest_name, conda, pypi)`:
  1. **Snapshot** `pyproject.toml` + `pixi.lock` (for revert).
  2. `pixi add --feature <feat> <conda specs>` and/or
     `pixi add --feature <feat> --pypi <pypi specs>` (per the `pixi add` docs — `--feature`
     routes into a named feature's tables).
  3. Ensure the `microdrop-plugins` environment includes `<feat>` and every other
     `plugin-*` feature (`pixi workspace environment add microdrop-plugins --feature …` /
     `pixi workspace feature` — exact maintenance commands verified in the plan; the invariant
     is *env = default + all installed plugin features*).
  4. **Conflict pre-check:** `pixi lock`. If it fails to solve → **restore the snapshot** and
     raise `PixiConflictError(message)`.
  5. `pixi install -e microdrop-plugins`.
- `remove_plugin_dependencies(manifest_name)` — drop `<feat>` from the env + remove the feature
  (`pixi workspace environment …` / `pixi workspace feature remove`). Best-effort; logged.
- All failures raise typed errors (`PixiError`/`PixiConflictError`) the action surfaces.

### 3. Installer integration (`installer.py`)

- `install_from_zip` extracts `pyproject.toml` (allowlist change above).
- `install_from_zip(...)` now returns an **`InstallResult` dataclass** (`manifest:
  PluginManifest`, `requires_relaunch: bool`) instead of the bare manifest; the action reads
  `result.manifest` / `result.requires_relaunch`. After the existing register step:
  - `deps = read_plugin_dependencies(target/"pyproject.toml")` (if present).
  - `missing = unsatisfied(deps)`.
  - If `missing`: `pixi_env.add_plugin_dependencies(manifest.name, deps.conda, deps.pypi)` (which
    conflict-checks + installs); set `requires_relaunch = True`.
  - Else `requires_relaunch = False`.
  - **On `PixiConflictError`/`PixiError`** (deps couldn't be added): **roll back the whole
    install** — `manager.deregister_plugin(manifest.name)` (if registered) + `rmtree` the install
    dir + `pixi_env.remove_plugin_dependencies(...)` (best-effort, in case a partial feature was
    written) — then re-raise so the action shows an error dialog. A conflicting plugin never
    lingers half-installed/un-enableable.
- `uninstall_plugin` also calls `pixi_env.remove_plugin_dependencies(name)` (best-effort) before
  deleting the dir.

### 4. Relaunch UX + helper (`menus.py` `InstallPluginAction`, `plugin_management/relaunch.py`)

- `InstallPluginAction.perform`: after a successful install, if `requires_relaunch`, show
  (via `pyface_wrapper.confirm`, Yes/No, manifest label escaped):
  > *"<label> was installed. It needs additional packages that were added to the environment —
  > they become available after a relaunch."*
  - **Yes** → `relaunch.relaunch_into_plugins_env()`.
  - **No** → `information(...)`: *"<label> will be available the next time you launch
    MicroDrop."*
  If `not requires_relaunch`, the existing "Installed <label> — enable it in Manage Plugins"
  message.
- `relaunch.py` — `relaunch_into_plugins_env()`: cleanly quit the running Qt app and re-exec the
  launcher under the plugins env, e.g. `pixi run -e microdrop-plugins python
  examples/run_device_viewer_pluggable.py <orig args>` (the exact relaunch command derivation —
  original argv / pixi task — is settled in the plan; it must run the *same* entry point in the
  `microdrop-plugins` env). Implementation note: stop the GUI loop, then `os.execvp` (or spawn +
  `application.exit()`).

### 5. Launch-time safety (already covered)

A plugin whose deps are still missing (user chose "No", hasn't relaunched) simply fails to
enable: `PluginGroupManager._resolve_factories` raises `ImportError` and `enable()` aborts the
group cleanly (logged) — so restore-on-launch and the Manage dialog never half-load it. No new
code strictly required; optionally the Manage dialog can show such a group as "needs relaunch".

## Data flow (install of a dep-bearing plugin)

```
Install Plugin… → install_from_zip:
   validate (allowlist now permits pyproject.toml) → consent → extract (incl. pyproject.toml)
   → register manifest
   → deps = read_plugin_dependencies(); missing = unsatisfied(deps)
   → missing? pixi_env.add_plugin_dependencies:
        snapshot pyproject.toml+lock → pixi add --feature → ensure env → pixi lock (conflict?)
          conflict → restore snapshot + (roll back install) + raise → error dialog
          ok → pixi install -e microdrop-plugins → requires_relaunch=True
   → action: requires_relaunch? Yes/No dialog
        Yes → relaunch_into_plugins_env()
        No  → "available next launch"
```

## Error handling

- `PixiConflictError` → restore the manifest/lock snapshot, roll back the plugin install, and
  show an error dialog naming the conflict; nothing is left half-applied.
- Other `PixiError` (pixi missing, network) → error dialog; if the env wasn't changed, the plugin
  install is rolled back too (so we never register a plugin whose deps silently failed).
- The relaunch self-exec is best-effort; if it fails, fall back to the "available next launch"
  message.

## Files

**New:** `plugin_management/plugin_deps.py`, `plugin_management/pixi_env.py`,
`plugin_management/relaunch.py`.
**Edit:** `plugin_management/installer.py` (allowlist + deps step + `InstallResult` + uninstall
hook), `plugin_management/menus.py` (`InstallPluginAction` relaunch dialog).

## Verification (no pytest)

- `py_compile` + `pixi` import smokes for `plugin_deps` (parse a fixture `pyproject.toml`;
  `unsatisfied` over a present vs absent dep) and `pixi_env` name helpers.
- A **guarded** pixi integration check on a throwaway copy of the workspace (or a temp pixi
  project): add a trivial dep to a feature + env, `pixi lock`, confirm it solves, then
  remove — to validate the exact `pixi workspace environment/feature` invocations. **Never** run
  these against the real workspace manifest in a smoke (they mutate `pyproject.toml`/`pixi.lock`).
- Manual GUI end-to-end: build a demo plugin whose `pyproject.toml` needs a small extra package;
  install → conflict-free → relaunch dialog → Yes relaunches into `microdrop-plugins` and the
  plugin enables; No defers; a conflicting dep is refused with rollback; a plugin with no extra
  deps installs with no relaunch.

## Known limitations (accepted)

- Installing a dep-bearing plugin **edits the workspace `pyproject.toml` + `pixi.lock`** (dirties
  the git tree) — inherent to a pixi-managed env.
- Satisfaction detection is best-effort on names → may offer an unnecessary relaunch (never the
  reverse). Plugins can avoid ambiguity by declaring deps whose dist names match import names.
- Single-process / single-user workstation assumption (matches the rest of plugin management).
- The exact pixi env/feature maintenance command sequence is validated in the plan against pixi
  0.63 (the model — env = default + all `plugin-*` features — is fixed; the CLI calls are the
  detail).
