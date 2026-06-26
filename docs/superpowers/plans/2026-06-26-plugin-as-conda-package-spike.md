# Plugin-as-conda-package Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove a MicroDrop plugin can be a real `pixi-build-python` conda package that declares its own deps (scipy) and is discovered via Python entry points, loaded through the existing `PluginGroupManager` — validating we could later replace the custom zip/manifest/app-data/`pixi_env` system.

**Architecture:** Repackage the existing `scipy_analysis` demo as a buildable conda package with a `microdrop.plugins` entry point and a TOML package-data manifest. pixi builds + installs it (resolving scipy). A new flag-gated discovery module reads installed packages' entry points + their `microdrop_plugin.toml` and feeds the existing manager. The runtime hot-load is reused unchanged. The whole spike is additive and reversible.

**Tech Stack:** pixi 0.63.2 (`pixi-build-python` preview backend), hatchling, Python `importlib.metadata` / `importlib.resources` / `tomllib` (stdlib), Envisage/Pyface, the existing `plugin_management` package.

## Global Constraints

- **Additive + reversible:** do NOT modify or remove the existing `.microdrop_plugin` zip format, `installer.py`, `paths.py`, `pixi_env.py`, app-data extraction, or the existing `examples/demo_plugins/scipy_analysis/` archive demo. Only NEW files + ONE flag-gated hook + ONE pure refactor (`manifest_from_dict`) are allowed.
- **No pytest** (project convention): verify via `python -m py_compile`, `pixi run` import/CLI smokes, and manual GUI. Write smokes inline in the task; do not add a pytest suite.
- **Entry-point group is EXACTLY** `microdrop.plugins`.
- **TOML manifest shape mirrors the JSON manifest:** `schema_version = 1`, `name`, `label`, `version`, `packages` (non-empty list), `groups` (each: `name`, `label`, `plugins` = list of `"module:Class"`, `enabled_key`, optional `post_enable_publish_topic`).
- **Discovery flag:** entry-point discovery is gated by env var `MICRODROP_ENTRYPOINT_PLUGINS=1` (off by default).
- **scipy is the `[package.run-dependencies]` conda dep** (the operative one pixi resolves); also kept in `[project.dependencies]` for hatchling wheel metadata.
- **Default environment** for the spike. The build path-dep mutates the OUTER `microdrop-py/pyproject.toml` + `pixi.lock` — keep that change LOCAL/uncommitted; revert with `pixi remove scipy_analysis` (or `git checkout -- pyproject.toml pixi.lock`).
- **Go/No-Go gate is Task 2 checkpoint 2** (does the preview build backend carry `[project.entry-points]` into installed dist metadata). Do not start Tasks 3+ integration code until Task 2 passes.
- Work from `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src` (submodule, branch `feat/plugin_management`). Commit messages end with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

## File structure

**New (committed, submodule):**
- `examples/demo_plugins/scipy_analysis_pkg/pyproject.toml` — the buildable conda package config (pixi-build-python + entry point + project deps).
- `examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/__init__.py`
- `examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/plugin.py` — copied verbatim from the existing demo.
- `examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/dock_pane.py` — copied verbatim from the existing demo.
- `examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/microdrop_plugin.toml` — TOML group manifest (package data).
- `plugin_management/entry_point_discovery.py` — flag-gated entry-point discovery.

**Modified (committed, submodule):**
- `plugin_management/manifest.py` — factor `manifest_from_dict(data)` out of `load_manifest` (pure refactor; JSON path unchanged).
- `plugin_management/group_manager.py` — one flag-gated block in `_discover_groups`.

**Modified (LOCAL/uncommitted, OUTER repo):**
- `microdrop-py/pyproject.toml` — `preview = ["pixi-build"]` + the `scipy_analysis` path dependency (Task 2; reverted at the end of the spike).

---

### Task 1: The buildable plugin package

**Files:**
- Create: `examples/demo_plugins/scipy_analysis_pkg/pyproject.toml`
- Create: `examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/__init__.py`
- Create: `examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/plugin.py` (copy)
- Create: `examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/dock_pane.py` (copy)
- Create: `examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/microdrop_plugin.toml`

**Interfaces:**
- Produces: an importable package `scipy_analysis` (with `scipy_analysis.plugin:ScipyAnalysisPlugin`) that advertises a `microdrop.plugins` entry point and ships `microdrop_plugin.toml` as package data.

- [ ] **Step 1: Copy the existing demo code verbatim**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src
mkdir -p examples/demo_plugins/scipy_analysis_pkg/scipy_analysis
cp examples/demo_plugins/scipy_analysis/scipy_analysis/plugin.py \
   examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/plugin.py
cp examples/demo_plugins/scipy_analysis/scipy_analysis/dock_pane.py \
   examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/dock_pane.py
```
Expected: the two files exist under the new `scipy_analysis_pkg/scipy_analysis/`. (`plugin.py`/`dock_pane.py` are unchanged — the entry-point + conda-package wrapping is all in the new metadata files.)

- [ ] **Step 2: Create the package `__init__.py`** (empty)

`examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/__init__.py`:
```python
```

- [ ] **Step 3: Create `microdrop_plugin.toml`** (TOML group manifest, package data)

`examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/microdrop_plugin.toml`:
```toml
schema_version = 1
name = "scipy_analysis"
label = "Scipy Random Analysis (conda-package spike)"
version = "0.1.0"
packages = ["scipy_analysis"]

[[groups]]
name = "scipy_analysis"
label = "Scipy Random Analysis (dock pane)"
plugins = ["scipy_analysis.plugin:ScipyAnalysisPlugin"]
enabled_key = "microdrop.scipy_analysis_enabled"
```

- [ ] **Step 4: Create the buildable `pyproject.toml`**

`examples/demo_plugins/scipy_analysis_pkg/pyproject.toml`:
```toml
[project]
name = "scipy_analysis"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["scipy>=1.10"]

[project.entry-points."microdrop.plugins"]
scipy_analysis = "scipy_analysis"

[build-system]
build-backend = "hatchling.build"
requires = ["hatchling"]

[tool.hatch.build.targets.wheel]
packages = ["scipy_analysis"]

[package]
name = "scipy_analysis"
version = "0.1.0"

[package.build.backend]
name = "pixi-build-python"
version = "0.*"
channels = ["https://prefix.dev/conda-forge"]

[package.host-dependencies]
hatchling = "*"

[package.run-dependencies]
scipy = ">=1.10"
```

- [ ] **Step 5: Verify the python compiles and the two manifests parse**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && \
  python -m py_compile examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/plugin.py \
                       examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/dock_pane.py && \
  python -c '
import tomllib
from pathlib import Path
base = Path(\"examples/demo_plugins/scipy_analysis_pkg\")
man = tomllib.loads((base/\"scipy_analysis\"/\"microdrop_plugin.toml\").read_text(\"utf-8\"))
print(\"manifest name/groups:\", man[\"name\"], [g[\"name\"] for g in man[\"groups\"]])
pp = tomllib.loads((base/\"pyproject.toml\").read_text(\"utf-8\"))
print(\"entry points:\", pp[\"project\"][\"entry-points\"][\"microdrop.plugins\"])
print(\"build backend:\", pp[\"package\"][\"build\"][\"backend\"][\"name\"])
print(\"run deps:\", pp[\"package\"][\"run-dependencies\"])
'"
```
Expected: no compile output; `manifest name/groups: scipy_analysis ['scipy_analysis']`; `entry points: {'scipy_analysis': 'scipy_analysis'}`; `build backend: pixi-build-python`; `run deps: {'scipy': '>=1.10'}`.

- [ ] **Step 6: Commit**

```bash
git add examples/demo_plugins/scipy_analysis_pkg
git commit -m "Spike: buildable scipy_analysis conda package (pixi-build-python + entry point + TOML manifest)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: GO/NO-GO — build, install, entry-point probe (Checkpoints 1 & 2)

**Files:**
- Modify (LOCAL/uncommitted, OUTER repo): `microdrop-py/pyproject.toml`

**Interfaces:**
- Produces: a documented go/no-go result. NOTHING is committed (the outer-repo manifest change stays local and is reverted at spike end). If the entry-point probe fails, STOP and report — do not start Task 3.

This task mutates the real workspace `microdrop-py/pyproject.toml` + `pixi.lock` and needs the network (pixi fetches the `pixi-build-python` backend + scipy). If offline, report BLOCKED.

- [ ] **Step 1: Add the build path dependency to the main workspace**

Edit `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/pyproject.toml`:
1. In `[tool.pixi.workspace]`, add a `preview` key (or extend it if present):
```toml
preview = ["pixi-build"]
```
2. In `[tool.pixi.dependencies]`, add the path dependency (relative to `microdrop-py/`):
```toml
scipy_analysis = { path = "src/examples/demo_plugins/scipy_analysis_pkg" }
```

- [ ] **Step 2: Build + install, confirm scipy lands in the env (Checkpoint 1)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi install 2>&1 | tail -20
pixi run python -c "import importlib.util as u; print('scipy installed:', u.find_spec('scipy') is not None); print('scipy_analysis installed:', u.find_spec('scipy_analysis') is not None)"
```
Expected: `pixi install` completes without error; `scipy installed: True`; `scipy_analysis installed: True`. If the build fails, capture the error — this is a Checkpoint-1 failure (build backend / preview feature issue); report and STOP.

- [ ] **Step 3: Probe the entry point (Checkpoint 2 — GO/NO-GO)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run python -c "
import importlib.metadata as md
eps = list(md.entry_points(group='microdrop.plugins'))
print('entry points found:', [(e.name, e.value) for e in eps])
print('GO' if any(e.name == 'scipy_analysis' for e in eps) else 'NO-GO')
"
```
Expected (GO): `entry points found: [('scipy_analysis', 'scipy_analysis')]` then `GO`.
If it prints `NO-GO` (the preview backend did not propagate `[project.entry-points]` into the installed dist metadata): **STOP**. Record the result in the report and evaluate the spec's fallbacks (naming/namespace convention; a different entry-point group; declaring the entry point in the generated conda recipe). Do not proceed to Task 3.

- [ ] **Step 4: Record the go/no-go result (no commit)**

Write the Checkpoint 1 & 2 outcomes (and any build errors) into the task report. Do NOT commit the outer `pyproject.toml`/`pixi.lock` change — it stays local for the rest of the spike and is reverted at the end. There is no code commit for this task.

---

### Task 3: `manifest_from_dict` adapter (pure refactor of manifest.py)

**Files:**
- Modify: `plugin_management/manifest.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `manifest_from_dict(data: dict) -> PluginManifest` (validates an already-parsed mapping; raises `ManifestError`). `load_manifest` keeps its signature and behavior, now delegating to it.

- [ ] **Step 1: Extract `manifest_from_dict` and have `load_manifest` call it**

In `plugin_management/manifest.py`, replace the body of `load_manifest` (everything from `if not isinstance(data, dict):` through the final `return PluginManifest(...)`) so that the validation/construction lives in a new `manifest_from_dict`, and `load_manifest` only does text→dict then delegates. The result:

```python
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
    return manifest_from_dict(data)


def manifest_from_dict(data) -> PluginManifest:
    """Validate an already-parsed manifest mapping (from JSON or TOML) into a
    PluginManifest. Raises ManifestError on any problem."""
    if not isinstance(data, dict):
        raise ManifestError("manifest must be a mapping")

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
            raise ManifestError(f"group #{i} must be a mapping")
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
(The only wording change is the two "must be a JSON object"/"JSON object" messages becoming "mapping", since the function now serves TOML too.)

- [ ] **Step 2: Verify the JSON path is unchanged and a TOML dict produces the same manifest**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
import tomllib
from plugin_management.manifest import load_manifest, manifest_from_dict
# existing JSON manifest still loads
m = load_manifest(\"default_plugins/magnet_peripherals/microdrop_plugin.json\")
print(\"json ok:\", m.name, [g.name for g in m.groups])
# the spike TOML manifest loads via the shared adapter
data = tomllib.loads(open(\"examples/demo_plugins/scipy_analysis_pkg/scipy_analysis/microdrop_plugin.toml\").read())
t = manifest_from_dict(data)
print(\"toml ok:\", t.name, t.packages, [(g.name, g.plugins, g.enabled_key) for g in t.groups])
'"
```
Expected: `json ok: magnet_peripherals ['magnet_backend', 'magnet_ui']`; `toml ok: scipy_analysis ['scipy_analysis'] [('scipy_analysis', ['scipy_analysis.plugin:ScipyAnalysisPlugin'], 'microdrop.scipy_analysis_enabled')]`.

- [ ] **Step 3: Commit**

```bash
git add plugin_management/manifest.py
git commit -m "manifest: factor manifest_from_dict out of load_manifest (shared by JSON + TOML)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `entry_point_discovery.py`

**Files:**
- Create: `plugin_management/entry_point_discovery.py`

**Interfaces:**
- Consumes: Task 3 `manifest_from_dict`, `ManifestError`.
- Produces: `ENTRY_POINT_GROUP = "microdrop.plugins"`; `enabled() -> bool` (reads `MICRODROP_ENTRYPOINT_PLUGINS`); `discover_entry_point_manifests() -> list[tuple[PluginManifest, str]]` (the str is a `"entry-point:<pkg>"` source label).

- [ ] **Step 1: Create the module**

`plugin_management/entry_point_discovery.py`:
```python
"""Discover installed plugin packages via Python entry points — an additive,
flag-gated alternative to directory-based manifest discovery.

A plugin package advertises itself with a ``microdrop.plugins`` entry point and
ships a ``microdrop_plugin.toml`` (same shape as microdrop_plugin.json) as
package data. We read that TOML and build the same PluginManifest the JSON path
produces, so the rest of PluginGroupManager is unchanged.
"""
import importlib.metadata as importlib_metadata
import importlib.resources as importlib_resources
import os
import tomllib

from plugin_management.manifest import manifest_from_dict, ManifestError
from logger.logger_service import get_logger

logger = get_logger(__name__)

ENTRY_POINT_GROUP = "microdrop.plugins"
MANIFEST_RESOURCE = "microdrop_plugin.toml"
_FLAG_ENV = "MICRODROP_ENTRYPOINT_PLUGINS"


def enabled() -> bool:
    """Entry-point discovery is opt-in for the spike, so the existing
    directory-based discovery is undisturbed when the flag is unset."""
    return os.environ.get(_FLAG_ENV) == "1"


def discover_entry_point_manifests():
    """Return ``[(PluginManifest, source_label)]`` for every installed package
    that advertises a ``microdrop.plugins`` entry point and ships a
    ``microdrop_plugin.toml``. Best-effort: a bad package is logged and skipped,
    never raised."""
    found = []
    for ep in importlib_metadata.entry_points(group=ENTRY_POINT_GROUP):
        pkg = ep.value
        try:
            resource = importlib_resources.files(pkg) / MANIFEST_RESOURCE
            data = tomllib.loads(resource.read_text(encoding="utf-8"))
            manifest = manifest_from_dict(data)
        except (ManifestError, OSError, ValueError, ModuleNotFoundError,
                tomllib.TOMLDecodeError) as e:
            logger.exception(f"skipping entry-point plugin '{pkg}': {e}")
            continue
        found.append((manifest, f"entry-point:{pkg}"))
    return found
```

- [ ] **Step 2: Compile**

Run: `cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run python -m py_compile src/plugin_management/entry_point_discovery.py`
Expected: no output.

- [ ] **Step 3: Discovery smoke (the spike package is installed from Task 2)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
from plugin_management import entry_point_discovery as ep
found = ep.discover_entry_point_manifests()
print(\"discovered:\", [(m.name, src, [g.name for g in m.groups]) for m, src in found])
print(\"enabled() default:\", ep.enabled())
import os; os.environ[\"MICRODROP_ENTRYPOINT_PLUGINS\"] = \"1\"; print(\"enabled() flagged:\", ep.enabled())
'"
```
Expected: `discovered: [('scipy_analysis', 'entry-point:scipy_analysis', ['scipy_analysis'])]`; `enabled() default: False`; `enabled() flagged: True`.

- [ ] **Step 4: Commit**

```bash
git add plugin_management/entry_point_discovery.py
git commit -m "Add entry_point_discovery: flag-gated microdrop.plugins entry-point + TOML manifest discovery

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Flag-gated discovery hook in PluginGroupManager (Checkpoint 3, CLI part)

**Files:**
- Modify: `plugin_management/group_manager.py` (`_discover_groups`)

**Interfaces:**
- Consumes: Task 4 `entry_point_discovery.enabled` / `discover_entry_point_manifests`; existing `self._add_manifest_groups`.
- Produces: when the flag is set, `PluginGroupManager().groups` additionally contains entry-point-discovered groups.

- [ ] **Step 1: Add the flag-gated block to `_discover_groups`**

In `plugin_management/group_manager.py`, in `_discover_groups`, immediately before `return groups`, add:
```python
        from plugin_management import entry_point_discovery
        if entry_point_discovery.enabled():
            for manifest, source in entry_point_discovery.discover_entry_point_manifests():
                self._add_manifest_groups(manifest, source_dir=source, into=groups)
```
(Local import keeps the change self-contained and additive. `source_dir="entry-point:<pkg>"` is not under `installed_plugins/`, so such a group is treated as bundled / disable-only — acceptable for the spike; pixi-based uninstall is out of scope.)

- [ ] **Step 2: Verify the group appears and its plugin class resolves (Checkpoint 3, headless)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen MICRODROP_ENTRYPOINT_PLUGINS=1 pixi run bash -c "cd src && python -c '
import importlib
from traits.etsconfig.api import ETSConfig
import tempfile; ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdhome_\")
from plugin_management.group_manager import PluginGroupManager
m = PluginGroupManager()
g = m.groups.get(\"scipy_analysis\")
print(\"group present:\", g is not None, \"| specs:\", g.plugin_specs if g else None)
# resolve the plugin class (scipy must be importable -> proves native deps + entry-point load)
mod_path, cls = g.plugin_specs[0].split(\":\")
cls_obj = getattr(importlib.import_module(mod_path), cls)
print(\"plugin class resolved:\", cls_obj.__name__)
'"
```
Expected: `group present: True | specs: ['scipy_analysis.plugin:ScipyAnalysisPlugin']`; `plugin class resolved: ScipyAnalysisPlugin`. (Importing the dock pane / scipy happens at enable; resolving the class proves the package + its deps are importable in the env.)

- [ ] **Step 3: Verify discovery stays OFF without the flag (no regression to the existing system)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig; ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdhome_\")
from plugin_management.group_manager import PluginGroupManager
m = PluginGroupManager()
print(\"scipy_analysis present without flag:\", \"scipy_analysis\" in m.groups)
print(\"magnet still discovered:\", \"magnet_ui\" in m.groups)
'"
```
Expected: `scipy_analysis present without flag: False`; `magnet still discovered: True`.

- [ ] **Step 4: Commit**

```bash
git add plugin_management/group_manager.py
git commit -m "group_manager: flag-gated entry-point group discovery (additive)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Manual GUI validation of the full loop + spike write-up (Checkpoint 4)

**Files:** none (manual + documentation).

**Interfaces:** consumes everything above; produces the spike's recorded outcome.

- [ ] **Step 1: Launch with entry-point discovery on** (the package is installed from Task 2; Redis running)

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && MICRODROP_ENTRYPOINT_PLUGINS=1 pixi run microdrop
```
Expected: the app starts; no errors about `scipy_analysis` during discovery (discovery reads the TOML only).

- [ ] **Step 2: Enable and verify the dock pane (tick each)**

- [ ] **Tools → Manage Plugins…** lists **Scipy Random Analysis (dock pane)**.
- [ ] Tick it → the dock pane mounts (the scipy histogram + KDE plot renders → proves scipy, installed by pixi as the package's dependency, is importable and the plugin loads through the existing runtime).
- [ ] Untick it → the pane unmounts cleanly (existing hot-unload path).

- [ ] **Step 3: Record the spike outcome**

In the task report, record: Checkpoint 1 (build+install+scipy), Checkpoint 2 (entry-point propagation GO/NO-GO), Checkpoint 3 (discovery→class resolve), Checkpoint 4 (GUI enable→pane). State the verdict: **does the package + entry-point approach work end-to-end**, and any rough edges (e.g. build time, preview-feature warnings, source_dir/uninstall classification). This verdict decides whether the full-migration design is worth pursuing.

- [ ] **Step 4: Revert the workspace mutation**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py
pixi remove scipy_analysis || git checkout -- pyproject.toml pixi.lock
git checkout -- pyproject.toml pixi.lock   # also drop the preview = ["pixi-build"] line if pixi remove left it
git status --short pyproject.toml pixi.lock   # expect clean
```
Expected: `microdrop-py/pyproject.toml` + `pixi.lock` back to their committed state (the spike's committed artifacts in the submodule remain; only the outer-repo env mutation is reverted).

---

## Notes for the executor

- Tasks 1, 3, 4, 5 produce committed submodule code. Task 2 commits nothing (records a go/no-go) and Task 6 is manual + revert.
- **Hard gate:** if Task 2 Step 3 prints `NO-GO`, stop the plan and report — the integration tasks (3–6) are pointless until entry-point propagation is solved. This is the whole reason the spike front-loads the risky validation.
- Everything is additive: the existing zip/manifest/app-data/`pixi_env` system is never touched, and entry-point discovery is off unless `MICRODROP_ENTRYPOINT_PLUGINS=1`.
- **Deferred on purpose:** the in-app "Install Plugin Package…" UI action (a button that runs `pixi add <path>` then offers relaunch) is NOT built in this spike. The spike installs via the CLI (Task 2) and validates the GUI *enable* (Task 6). Wiring the in-app install + relaunch UX belongs to the full-migration design, and only if the spike is GO — per the spec's out-of-scope. The user's "install via the UI" goal is satisfied later by that design, not the spike.
