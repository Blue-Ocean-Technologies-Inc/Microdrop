# Plugin Hot-Load Without Relaunch — Design

**Date:** 2026-07-16
**Scope:** `plugin_management` only — new `hot_load.py`; snapshot/diff
helpers + `EnvChangeResult` in `package_installer.py`; `register_manifest`
added to `i_plugin_group_manager.py`; the four `confirm_and_relaunch` call
sites in `browse_controller.py` / `manage_controller.py` /
`update_controller.py` routed through one `finish_change(...)` helper.
**Goal:** after a plugin package is installed or removed, decide from a
`pixi list --json` diff whether the change is safe to apply to the live
interpreter. When it is, re-discover entry points, register the new
manifest's groups and enable them so dock panes/menus appear immediately —
no relaunch. When it is not, fall back to today's relaunch prompt.
**Related:** Microdrop issue #491 (plugin-management improvements).

**Baseline note:** this design assumes the *working tree* state of
`package_installer.py`, not `HEAD`. The uncommitted `_run(["install"])`
calls in `install_from_channel` and `uninstall_package` are load-bearing
here (they are what makes the env on disk match the lock before we diff),
as are the uncommitted `relaunch.py` changes to the `pixi run microdrop`
task form.

## Existing infrastructure (reused, not rebuilt)

- `package_installer.install_from_channel(name, version=None)` — registers
  the channel, `pixi add`, `pixi install`, with pyproject/lock
  snapshot+rollback on failure.
- `package_installer.uninstall_package(name)` — `pixi remove` + `pixi
  install`, best-effort.
- `package_installer._run(args, cwd=...)` — the pixi subprocess wrapper;
  raises `InstallError` on non-zero exit.
- `entry_point_discovery.discover_entry_point_manifests()` — pure,
  stateless, imports no plugin code; returns `[(PluginManifest, dist_name)]`.
  Safe to re-run at any time.
- `PluginGroupManager.register_manifest(manifest, dist_name)` — splices a
  freshly-installed manifest's groups into the live registry without
  clobbering loaded ones; raises if a colliding group name is loaded.
  **Currently has no production caller** — this design supplies it.
- `PluginGroupManager.apply(application, desired)` — reconciles group load
  state, calls `enable()`/`disable()`, and persists the enabled flag.
- `PluginGroupManager._norm_dist(name)` — normalises case and `_`/`-` so
  conda `magnet-microdrop-plugin` matches dist `magnet_microdrop_plugin`.
- `PluginGroupManager.enable()` — resolves `"module:Class"` specs via
  `importlib.import_module`, `add_plugin` + `start_plugin` on the live
  application, snapshot-diffs the service registry to capture runtime
  service ids.
- `LiveTaskExtensionsController` — reactively mounts/unmounts dock panes and
  rebuilds the menu bar when `TASK_EXTENSIONS` change. The hot-load path
  never touches the view layer; this controller does it.
- `manage_model.pre_uninstall(manifest_name)` — disables + deregisters a
  plugin's groups *before* its package is removed.
- `run_with_wait(work, on_success=..., on_error=...)` — worker thread for
  `work`, callbacks marshalled to the GUI thread.
- `relaunch.confirm_and_relaunch(task, msg_html)` — the standard
  "relaunch now / later" popup.

## Why this is possible at all

`pixi install` writes into `.pixi/envs/default/Lib/site-packages`, which is
the same prefix the running interpreter imports from when the app is
launched via `pixi run microdrop` (the `microdrop` task in
`pyproject.toml`). `relaunch_app` re-execs into *that same environment* — so
the relaunch changes nothing about the env, it only obtains a fresh
interpreter. The relaunch exists solely to dodge the in-process import
problem.

`relaunch.py`'s stated rationale ("a live interpreter can't safely import
packages added mid-run") is too broad. Importing a *brand-new* package into
a live interpreter is fine, and `enable()` already does exactly that today
for never-before-imported plugin code when a group is toggled on. The
genuinely unsafe cases are *upgrading* or *removing* an already-imported
package: stale modules in `sys.modules`, live objects of old classes, and
on Windows, replacement of loaded `.pyd`/`.dll` files.

`importlib.metadata`'s `FastPath.lookup` is keyed on the directory's
`st_mtime`, so a newly installed `.dist-info` self-invalidates and
`entry_points()` would see it without help. We still call
`importlib.invalidate_caches()` — it is needed for the `FileFinder` /
`sys.path_importer_cache` layer that `enable()`'s `import_module` goes
through, and it closes the same-mtime-tick gap on coarse filesystems.

## Design

### 1. Env snapshot + diff (`package_installer.py`)

```python
def env_snapshot(*, cwd=None) -> dict:
    """{name: (version, build, kind)} from `pixi list --json`.

    Defaults to the platform best matching this machine, which is the
    platform the running interpreter is using."""
    proc = _run(["list", "--json"], cwd=cwd)
    return {r["name"]: (r["version"], r["build"], r["kind"])
            for r in json.loads(proc.stdout)}
```

```python
@dataclass(frozen=True)
class EnvDiff:
    added: dict     # name -> version
    changed: dict   # name -> (old_version, new_version)
    removed: dict   # name -> version

    @property
    def is_pure_addition(self):
        return not self.changed and not self.removed

    @property
    def is_pure_removal(self):
        return not self.changed and not self.added
```

`diff_snapshots(before, after) -> EnvDiff` compares the full
`(version, build)` tuple, so a rebuild at the same version counts as
`changed`.

`InstallResult` is **renamed `EnvChangeResult`** — it is now returned by
uninstall as well as install:

```python
@dataclass
class EnvChangeResult:
    name: str
    diff: EnvDiff | None       # None when snapshotting failed
    requires_relaunch: bool
```

`install_from_channel` snapshots around its existing pixi calls and returns
`requires_relaunch = not (diff and diff.is_pure_addition)`.
`uninstall_package` — which currently returns `None` — returns the same
dataclass with `requires_relaunch = not (diff and diff.is_pure_removal)`.

`uninstall_package` currently *swallows* `InstallError` (logs a warning and
returns). It keeps that contract: on a failed `pixi remove` it returns
`EnvChangeResult(name, diff=None, requires_relaunch=True)`, so a failed
uninstall degrades to the relaunch prompt rather than silently claiming the
fast path.

Both snapshot calls are individually wrapped so a snapshot failure can never
break the install (see §5).

The three worker-thread model methods that currently discard the installer's
return value — `manage_model.do_install_version`, `do_upgrade`, and
`do_uninstall` — must `return` the `EnvChangeResult` so the controller's
`on_success(r)` can read `r.diff`.

### 2. The gate rules

| Flow | Safe when | Rule |
|---|---|---|
| install / install-version / upgrade / update-all | pure additions | `not diff.is_pure_addition` → relaunch |
| uninstall | pure removals | `not diff.is_pure_removal` → relaunch |

The asymmetry is deliberate:

- **`changed` is unsafe in both directions** — new files on disk underneath
  live modules in memory.
- **A removal during *install*** means the solver dropped a package to
  satisfy the new plugin. Its modules may be live *and still in use by a
  running plugin*. Unsafe.
- **A removal during *uninstall*** is the entire point. `pre_uninstall` has
  already disabled and deregistered the affected groups, and orphaned
  dependencies will not be re-imported by anything.

**Consequence, stated plainly:** upgrade, install-version, and update-all
will *always* relaunch, because the plugin's own version change lands in
`changed`. The fast path realistically fires for exactly two flows — fresh
install of a new plugin, and clean uninstall. This is a smaller win than
"no more relaunches", and it is the intended, conservative scope.

### 3. Hot-load (`hot_load.py`, new)

```python
def hot_load_installed(application, manager, dist_name, diff) -> bool:
    """True if the plugin was registered + enabled live.
    False means the caller must fall back to the relaunch prompt."""
    if diff is None or not diff.is_pure_addition:
        return False
    importlib.invalidate_caches()
    norm = PluginGroupManager._norm_dist          # existing static, see below
    mine = [(m, d) for m, d in discover_entry_point_manifests()
            if norm(d) == norm(dist_name)]
    if not mine:
        return False                       # discovered nothing -> be conservative
    if any(_live_modules(m) for m, _ in mine):
        return False                       # stale sys.modules -> relaunch
    names = []
    try:
        for manifest, dist in mine:
            manager.register_manifest(manifest, dist_name=dist)
            names += [g.name for g in manifest.groups]
    except RuntimeError:                   # colliding group currently loaded
        return False
    manager.apply(application, {n: True for n in names})
    if not all(manager.is_loaded(n) for n in names):
        return False                       # imports failed -> relaunch may help
    return True
```

It goes through `manager.apply(...)` rather than calling `enable()` directly
because `apply()` is the existing public reconcile entry point *and* it
persists the enabled flag — so a hot-installed plugin survives the next
launch the same way a toggled one does.

### 4. The `sys.modules` guard

```python
def _live_modules(manifest):
    """Top-level modules enable() would import that are already loaded."""
    for spec in manifest.groups:
        for plugin_spec in spec.plugins:          # "module.path:ClassName"
            top = plugin_spec.partition(":")[0].split(".")[0]
            if top in sys.modules:
                yield top
```

This guards *exactly* what `_resolve_plugin_class` imports, rather than
approximating via package names (conda names, python dist names, and module
names all differ, and native libs map to no dist at all — any mapping-based
check would silently under-report).

It is **not** redundant with the gate. Two real cases trip it, both of which
the gate alone reports as "pure addition" and would wrongly wave through:

1. **Reinstall after uninstall in the same session.** Uninstall now takes
   the fast path and leaves the plugin's modules in `sys.modules`. A
   subsequent reinstall is a pure addition by the lock, but
   `import_module` would hand back the *stale* module — silently running
   the old code while reporting the new version.
2. **Top-level package collision.** `magnet-microdrop-plugin` ships a
   top-level `peripheral_controller` package. A second plugin claiming that
   name while magnet is loaded is correctly refused rather than silently
   binding to magnet's already-imported module.

### 5. Error handling

Governing principle: **the gate must never break the install.** The package
is on disk and correct by the time we diff; a failure to *reason* about it
degrades to today's behaviour, never to a failed install.

- **`env_snapshot()` fails** (pixi non-zero, unparseable JSON). Wrapped in
  try/except at both call sites → `diff = None` → `requires_relaunch = True`
  → relaunch prompt. This needs care: `env_snapshot` goes through `_run`,
  which raises `InstallError`, so an unguarded *before*-snapshot would abort
  an install that had not started yet.
- **`hot_load_installed` raises unexpectedly.** Broad try/except inside it;
  log and return `False` → relaunch. This matches the module's neighbours —
  `discover_entry_point_manifests`, `enable`, and
  `LiveTaskExtensionsController` all log-and-continue rather than propagate.
- **Install rollback** is unchanged: `_snapshot`/`_restore` of
  `pyproject.toml` + `pixi.lock` still fire on any pixi failure.

**Known gap (accepted, out of scope).** `enable()` swallows per-plugin
exceptions and sets `group.loaded = True` regardless, so a plugin whose
class imports fine but whose `start()` throws reports as loaded with no
pane. That is exactly how it behaves today when toggled on — not a
regression, and fixing it means changing `enable()`'s contract for the
existing toggle path. The *fully* unimportable case **is** detectable
(`enable()` returns early without setting `loaded` when
`_resolve_plugin_class` fails for every spec) and is caught by the
`all(manager.is_loaded(n))` check in §3 — that is the one case where
relaunching is a real remedy rather than superstition.

### 6. Threading

```
worker thread   (run_with_wait's work fn)
  before = env_snapshot()
  pixi add / pixi remove ; pixi install
  after  = env_snapshot()
  -> EnvChangeResult(name, diff, requires_relaunch)

GUI thread      (run_with_wait's on_success)
  ok = hot_load_installed(app, manager, dist, r.diff)
  finish_change(task, msg_html, ok)
```

The split is forced, not stylistic: pixi subprocesses must stay off the GUI
thread, but `hot_load_installed` mutates `PluginGroupManager` traits and
fires the `TASK_EXTENSIONS` delta that `LiveTaskExtensionsController`
reconciles, so it must run on the GUI thread. `run_with_wait` already
provides exactly this split (`on_success` is GUI-thread), so no new
threading primitive is needed, and the MVC rule that the model is mutated
only on the GUI thread is preserved.

### 7. Controller integration

One shared helper replaces the four current `confirm_and_relaunch` call
sites:

```python
def finish_change(task, msg_html, ok):
    if ok:
        information(parent=None, title="Plugin ready", message=msg_html)
    else:
        confirm_and_relaunch(task, msg_html)
```

(`information` / `confirm` / `YES` come from
`microdrop_application.dialogs.pyface_wrapper`, as `relaunch.py` already
does — never raw QMessageBox.)

Because the fast path auto-enables, the success message must say so:
`browse_controller`'s current `"Installed <b>X</b> 1.2.3."` becomes
`"Installed and enabled <b>X</b> 1.2.3."` on the hot-load branch. The
relaunch branch keeps today's wording, since nothing is enabled yet.

**Every install path calls `hot_load_installed` uniformly** — no
special-casing by flow. The gate decides, and paths that can never be safe
simply fail it on the first line and cost nothing:

- `browse_controller.install_selected` — `on_success` runs
  `hot_load_installed(...)` then `finish_change(...)`. This is the path that
  actually takes the fast lane.
- `manage_controller._prompt_install_version` / `_on_upgrade` — same two
  calls. Their diffs always contain `changed`, so `hot_load_installed`
  returns `False` immediately and behaviour is unchanged. Routing them
  through the same code keeps one path and means a future loosening of the
  gate needs no new wiring.
- `update_controller` — update-all; same two calls, always `changed`, always
  relaunch.
- `manage_controller._on_uninstall` — the one exception. `pre_uninstall`
  still runs first, then `finish_change(task, msg, not r.requires_relaunch)`
  with **no** `hot_load_installed` call, because uninstall imports nothing
  and has nothing to register.

`register_manifest` is added to `IPluginGroupManager`
(`i_plugin_group_manager.py`), which currently declares only `is_loaded` /
`enable` / `disable` / `apply` / `adopt_running` / `restore_persisted`.
Consumers hold the manager by protocol and cannot reach `register_manifest`
today.

## Testing

Unit tests in `plugin_management/tests/` — all pure, no Qt, no Envisage, no
real pixi:

1. `diff_snapshots` classification — added / changed / removed; a
   **build-only** change (same version, new build) must count as `changed`;
   both `is_pure_*` properties.
2. `env_snapshot` parsing — monkeypatch `_run` with a captured
   `pixi list --json` fixture.
3. The rule table — pure addition → no relaunch; removal-during-install →
   relaunch; upgrade (`changed`) → relaunch; pure removal on uninstall → no
   relaunch.
4. `_live_modules` — a manifest whose plugin spec module is in `sys.modules`
   trips the guard.
5. `hot_load_installed` against a fake manager (reusing the fake-manager
   pattern in `test_group_manager_adoption.py`) — asserts `register_manifest`
   + `apply` are called on the happy path, and that each refusal branch
   returns `False`.
6. Snapshot failure → `diff is None` → `requires_relaunch is True`, install
   still reports success.

`test_package_installer.py` currently asserts `result.requires_relaunch is
True` unconditionally and must be updated to drive it off a mocked diff. It
also references `InstallResult` by name (rename to `EnvChangeResult`).

**Manual verification** (the real proof — launch via `pixi run microdrop`):

- Browse Plugins → install `heater-microdrop-plugin` (not currently
  installed) → expect **no** relaunch prompt; pane appears live.
- Uninstall it → expect **no** relaunch prompt; pane disappears.
- Reinstall it in the same session → expect **a relaunch prompt** (module
  guard trips). This is the case that validates the guard and is the most
  likely to reveal a design error.
- Upgrade `magnet-microdrop-plugin` → expect **a relaunch prompt**
  (`changed` non-empty).

## Out of scope

- Loosening the gate to "only relaunch if a changed package is actually
  imported". Rejected for now: conda names, python dist names and module
  names diverge, and native libs map to no dist, so any mapping-based check
  under-reports in the unsafe direction.
- Making `enable()` report per-plugin start failures (changes the contract
  for the existing toggle path).
- Unloading modules on uninstall. Python cannot reliably un-import; the
  `sys.modules` guard exists precisely because we accept this.
- Frozen/PyInstaller builds (`src/pyinstaller.spec`): there is no pixi env
  and `pixi` may not be on PATH, so `install_from_channel` already fails at
  the `subprocess.run(["pixi", ...])` call. Orthogonal to this change.
