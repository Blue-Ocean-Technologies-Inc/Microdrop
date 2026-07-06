# Plugin Update Check on Launch — Design

**Date:** 2026-07-03
**Scope:** `plugin_management` only — new `update_model.py` /
`update_view.py` / `update_controller.py`; hooks in `plugin.py`; small
helper additions in `package_installer.py`.
**Goal:** on every app launch, silently fetch the plugins channel, diff
against the previous launch's cached copy and the installed set, and —
only when there is something to say — show an information dialog listing
available updates and newly available plugins, with an Update All button
that installs updates and then offers the standard relaunch popup.
**Related:** Microdrop issue #491 (plugin-management improvements).

## Existing infrastructure (reused, not rebuilt)

- `package_installer.search_channel()` — fetches the channel via
  `pixi search "*" -c <url> --json` AND rewrites the app-data cache
  (`paths.plugin_index_file()` → `plugin_index.json` under
  `ETSConfig.application_home`) on success only.
- `package_installer.read_cached_index()` — last launch's copy, `[]` if
  absent/unreadable.
- `package_installer.install_from_channel(name)` — installs the latest
  version of a package from the channel (pixi add), with rollback.
- `browse_model._version_key()` — version comparator.
- `run_with_wait(...)` — threaded worker + wait dialog, success/error
  marshalled to the GUI thread.
- `relaunch.confirm_and_relaunch(task, msg_html)` — the standard
  "relaunch now / later" popup used by manual installs.
- `PluginManagementPlugin._restore_groups_on_launch` — runs once at
  `application:application_initialized`.

## Design

### 1. Launch check (plugin.py)

A second run-once observer on
`application:application_initialized` (after `_restore_groups_on_launch`
by declaration order; independent of it) starts a **daemon thread**:

```python
old = package_installer.read_cached_index()      # BEFORE the fetch rewrites it
new = package_installer.search_channel()          # writes the new cache
installed = installed_plugin_dists()              # {dist name: version}
report = compute_update_report(old, new, installed)
if report.has_content:
    GUI.invoke_later(show_update_dialog, report, self.application)
```

- Launch is never blocked; no wait dialog for the fetch.
- `InstallError` (offline, pixi missing, parse failure) → `logger.info`,
  no UI, cache untouched (search_channel only writes on success).
- The check runs exactly once per launch (`_update_check_started` Bool
  guard, same pattern as `_groups_restored`).

### 2. Installed set — `installed_plugin_dists()` (package_installer.py)

`{dist.name: dist.version}` for every distribution exposing an entry
point in group `microdrop.plugins` (via `importlib.metadata`). Dist
names match channel package names exactly (`heater-microdrop-plugin`).

### 3. Diff — `compute_update_report(old, new, installed)` (update_model.py)

Pure function; unit-tested. Collapses `old`/`new` package lists to
{name: latest version} with `_version_key`, then:

- **updates**: `name in installed` and channel latest > installed
  version → `(name, installed_version, latest_version)`.
- **new plugins**: `name not in installed` and `name` absent from the
  OLD list → `(name, latest_version)`. **First-launch baseline:** if
  `old` is empty (no cache yet), new-plugin detection is skipped
  entirely — the fetch writes the baseline and only updates are
  reported. Prevents every package showing as "new" on a fresh install.
- Returns an `UpdateReport` (HasTraits, Qt-free): `updates = List`,
  `new_plugins = List`, `has_content` property.

### 4. Dialog — MVC trio mirroring browse_*

- **`update_model.py`** (Qt-free): `UpdateReport` + `compute_update_report`
  + `do_update_all()` — worker-safe, loops
  `install_from_channel(name)` over `updates`, collects per-package
  success/failure, returns `(succeeded: list, failed: list[(name, err)])`.
  No trait mutation off the GUI thread (project threading rule).
- **`update_view.py`**: TraitsUI View, two bordered sections that hide
  when empty (`visible_when`): "Updates available" rows
  `name  installed → latest`, "New plugins available" rows
  `name  version` plus a hint line "Install new plugins via
  Tools ▸ Manage Plugins ▸ Browse". Buttons: **Update All** (visible
  only when updates non-empty) and **Later**.
- **`update_controller.py`**: TraitsUI Handler. Update All →
  `run_with_wait` around `do_update_all`; on done: if any succeeded →
  `confirm_and_relaunch(task, <html listing updated packages>)`; if any
  failed → error dialog (pyface_wrapper) listing failures; dialog
  closes. Later → close. Dialog opened `kind="livemodal"` from
  `GUI.invoke_later` (same as the Manage dialog). The `task` handed to
  `confirm_and_relaunch` is `application.active_window.active_task`
  (None-safe — the helper already degrades gracefully).

### 5. Non-goals (YAGNI)

- No per-package update selection — one Update All button (as asked).
- No install-new-from-dialog — new plugins are informational; the
  Browse dialog already installs.
- No periodic re-check while running; launch only.
- No settings toggle to disable the check (add later if it annoys).

## Error handling

- Fetch failure → silent (log info), no dialog.
- Cache read failure → treated as empty old list (baseline semantics).
- Update failure(s) → error dialog listing the failed packages with
  reasons; relaunch offered iff at least one package updated.
- Dialog code never runs off the GUI thread; the worker only returns
  data.

## Testing

Written but not run (project policy); manual GUI verification by user:

- Unit tests for `compute_update_report`: update detected, no-op when
  equal/older, new plugin vs old cache, first-launch baseline (old
  empty → no "new" spam), installed-but-absent-from-channel ignored.
- Unit test for `installed_plugin_dists` shape (mock metadata).
- Manual: launch with stale installed version → dialog lists update;
  Update All → wait dialog → relaunch popup; fresh cache → silent
  launch; offline → silent launch.
