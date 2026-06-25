# Dependency-Aware Plugin Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a `.microdrop_plugin` archive carry a `pyproject.toml` declaring extra conda/PyPI deps; on install, put missing deps into a per-plugin pixi feature + a `microdrop-plugins` environment (conflict-checked, snapshot/rollback), and relaunch the app into that env **only when a dep isn't already importable**, via a Yes/No dialog.

**Architecture:** Two Qt-free service modules (`plugin_deps` = parse + satisfaction check; `pixi_env` = pure pixi command-builders + a thin subprocess runner) feed the installer; the menu action shows the relaunch dialog and a `relaunch` helper re-execs into the env. `PluginGroupManager._resolve_factories`' existing import-abort is the backstop for a not-yet-relaunched plugin.

**Tech Stack:** pixi 0.63 (`add --feature`, `workspace environment add --force`, `workspace feature remove`, `lock`, `install -e`), `tomllib` (stdlib), `importlib.metadata`, `subprocess`, PySide6/pyface (dialogs), envisage.

**Spec:** `docs/superpowers/specs/2026-06-25-plugin-dependency-resolution-design.md`

## Global Constraints

- **Working dir for source commands:** `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src`. The **pixi workspace root** is its parent `microdrop-py/` (where `pyproject.toml` + `pixi.lock` live). Commits land in the submodule on `feature/peripheral-hot-load`.
- **Testing convention (this project):** NO pytest. Each task gates on `python -m py_compile` + a `pixi run` import/introspection smoke (run via `cd microdrop-py && pixi run bash -c "cd src && python -c '...'"`), then manual GUI at the end.
- **NEVER run mutating pixi commands against the real workspace in a smoke.** `pixi add`/`workspace environment add`/`workspace feature remove`/`install`/`lock` edit the committed `microdrop-py/pyproject.toml` + `pixi.lock`. Smokes verify pure command *builders* (argv lists) only. The one allowed pixi execution is inside a **throwaway `pixi init` temp project** (Task 2 Step 6).
- **Conventions:** dataclasses for inert data; HasTraits elsewhere; f-strings only; logger via `from logger.logger_service import get_logger`; no Qt in service/model layers (`plugin_deps`/`pixi_env`/`installer` are Qt-free; the dialog + relaunch are view-layer); manifest-derived strings shown in dialogs are HTML-escaped via `escape_html_multiline`.
- **Commit trailer:** end every commit with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Env/feature names (verbatim):** environment `microdrop-plugins`; feature `plugin-<manifest.name>`.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `plugin_management/plugin_deps.py` | parse a plugin `pyproject.toml`'s dep tables; `unsatisfied()` satisfaction check | Create |
| `plugin_management/pixi_env.py` | pure pixi command builders + thin runner; `add_plugin_dependencies`/`remove_plugin_dependencies` with snapshot/rollback | Create |
| `plugin_management/relaunch.py` | re-exec the app into the `microdrop-plugins` env | Create |
| `plugin_management/installer.py` | allowlist `pyproject.toml`; `InstallResult`; deps step + conflict rollback; uninstall hook | Modify |
| `plugin_management/menus.py` | `InstallPluginAction` relaunch Yes/No dialog | Modify |

---

## Task 1: `plugin_deps.py` — parse + satisfaction check

**Files:** Create `plugin_management/plugin_deps.py`

**Interfaces:**
- Produces: `@dataclass PluginDependencies(conda: list[str], pypi: list[str])`; `read_plugin_dependencies(source) -> PluginDependencies` (source = a `pyproject.toml` Path, or its text/bytes; missing file → empty); `unsatisfied(deps) -> list[str]` (declared deps not importable in the current process; errs toward "unsatisfied").

- [ ] **Step 1: Create the module**

Create `plugin_management/plugin_deps.py`:

```python
"""Parse a plugin archive's pyproject.toml dependency tables and check which
declared deps are missing from the current environment.

Qt-free, pure data. Mirrors the main env's pyproject shape: conda specs from
[tool.pixi.dependencies], PyPI specs from [project.dependencies] +
[tool.pixi.pypi-dependencies]. Only string version values are converted to
specs; dict values (channel/path/editable) contribute just the bare name
(lossy — noted as a limitation)."""

import importlib.metadata as importlib_metadata
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Union


@dataclass
class PluginDependencies:
    conda: List[str] = field(default_factory=list)
    pypi: List[str] = field(default_factory=list)


def _table_spec(name, value):
    """A pixi/conda or PyPI MatchSpec from a manifest table entry."""
    if isinstance(value, str) and value not in ("", "*"):
        return f"{name}{value}"
    return name


def _load(source: Union[str, bytes, Path]) -> dict:
    if isinstance(source, (str, Path)) and Path(str(source)).exists():
        return tomllib.loads(Path(source).read_text(encoding="utf-8"))
    if isinstance(source, bytes):
        return tomllib.loads(source.decode("utf-8"))
    return tomllib.loads(str(source))


def read_plugin_dependencies(source: Union[str, bytes, Path]) -> PluginDependencies:
    """Parse conda + PyPI deps from a plugin pyproject.toml. Missing file or
    tables → empty lists. Never raises for an absent file."""
    if isinstance(source, (str, Path)) and not Path(str(source)).exists():
        return PluginDependencies()
    try:
        data = _load(source)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return PluginDependencies()

    pixi = (data.get("tool") or {}).get("pixi") or {}
    conda_table = pixi.get("dependencies") or {}
    conda = [_table_spec(n, v) for n, v in conda_table.items()]

    pypi = list((data.get("project") or {}).get("dependencies") or [])
    pypi_table = pixi.get("pypi-dependencies") or {}
    pypi += [_table_spec(n, v) for n, v in pypi_table.items()]
    return PluginDependencies(conda=conda, pypi=pypi)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _dep_name(spec: str) -> str:
    """The bare package name from a MatchSpec / PEP 508 string."""
    return re.split(r"[<>=!~;\s\[]", spec.strip(), 1)[0]


def _installed_dist_names() -> set:
    names = set()
    for dist in importlib_metadata.distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            names.add(_normalize(name))
    return names


def unsatisfied(deps: PluginDependencies) -> List[str]:
    """Declared deps NOT present as an installed distribution in the current
    process. Errs toward 'unsatisfied' (conda pkgs without dist-info, name
    mismatches) so at worst we offer an unnecessary relaunch — never the
    reverse."""
    installed = _installed_dist_names()
    missing = []
    for spec in list(deps.conda) + list(deps.pypi):
        name = _normalize(_dep_name(spec))
        if name and name not in installed:
            missing.append(spec)
    return missing
```

- [ ] **Step 2: Compile**

Run: `python -m py_compile plugin_management/plugin_deps.py`
Expected: no output.

- [ ] **Step 3: Parse + satisfaction smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
from plugin_management.plugin_deps import read_plugin_dependencies, unsatisfied
toml = \"\"\"
[project]
dependencies = [\"boto3>=1.2\"]
[tool.pixi.dependencies]
numpy = \">=1.20\"
pyside6 = \"*\"
[tool.pixi.pypi-dependencies]
rich = \">=13\"
\"\"\"
d = read_plugin_dependencies(toml)
print(\"conda:\", d.conda)
print(\"pypi:\", d.pypi)
u = unsatisfied(d)
print(\"pyside6 satisfied (not in missing):\", not any(s.startswith(\"pyside6\") for s in u))
print(\"boto3 unsatisfied (in missing):\", any(s.startswith(\"boto3\") for s in u))
print(\"empty file -> no deps:\", read_plugin_dependencies(\"/no/such/pyproject.toml\").conda == [])
'"
```
Expected: `conda: ['numpy>=1.20', 'pyside6']`; `pypi: ['boto3>=1.2', 'rich>=13']`; `pyside6 satisfied (not in missing): True` (PySide6 is installed); `boto3 unsatisfied (in missing): True` (boto3 is not); `empty file -> no deps: True`.

- [ ] **Step 4: Commit**

```bash
git add plugin_management/plugin_deps.py
git commit -m "Add plugin_deps: parse plugin pyproject deps + satisfaction check

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `pixi_env.py` — pixi command builders + add/remove (with temp-project verification)

**Files:** Create `plugin_management/pixi_env.py`

**Interfaces:**
- Produces: `PixiError`, `PixiConflictError`; `PLUGINS_ENV = "microdrop-plugins"`; `feature_name(manifest_name) -> str`; pure builders `add_conda_cmd`/`add_pypi_cmd`/`env_add_cmd`/`env_remove_cmd`/`feature_remove_cmd`/`lock_cmd`/`install_env_cmd`/`feature_list_cmd` (each → `list[str]` of pixi args, no leading `"pixi"`); `add_plugin_dependencies(manifest_name, conda, pypi)`; `remove_plugin_dependencies(manifest_name)`.

- [ ] **Step 1: Create the module**

Create `plugin_management/pixi_env.py`:

```python
"""Add/remove a plugin's dependencies in the pixi-managed workspace.

Each dependency-bearing plugin gets a feature ``plugin-<name>``; the
``microdrop-plugins`` environment = default + every such feature. Adding deps is
conflict-checked with ``pixi lock`` and snapshot/rolled-back on failure. Qt-free
service; the command BUILDERS are pure (unit-testable) and ``_run`` is the only
side-effecting part.

WARNING: these commands edit the workspace ``pyproject.toml`` + ``pixi.lock``.
Never invoke the mutating helpers outside a real install / a throwaway test
project.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The pixi workspace root (microdrop-py/, parent of src/) — has pyproject.toml.
WORKSPACE_DIR = Path(__file__).resolve().parents[2]

PLUGINS_ENV = "microdrop-plugins"
FEATURE_PREFIX = "plugin-"


class PixiError(Exception):
    """A pixi command failed."""


class PixiConflictError(PixiError):
    """The workspace could not be solved with the plugin's dependencies."""


def feature_name(manifest_name: str) -> str:
    return FEATURE_PREFIX + manifest_name


# --- pure command builders (argv after "pixi"; unit-testable) --------

def add_conda_cmd(feature, specs):
    return ["add", "--no-progress", "--feature", feature, *specs]


def add_pypi_cmd(feature, specs):
    return ["add", "--no-progress", "--feature", feature, "--pypi", *specs]


def env_add_cmd(env, features):
    cmd = ["workspace", "environment", "add", env, "--force"]
    for f in features:
        cmd += ["--feature", f]
    return cmd


def env_remove_cmd(env):
    return ["workspace", "environment", "remove", env]


def feature_remove_cmd(feature):
    return ["workspace", "feature", "remove", feature]


def feature_list_cmd():
    return ["workspace", "feature", "list"]


def lock_cmd():
    return ["lock", "--no-progress"]


def install_env_cmd(env):
    return ["install", "--no-progress", "-e", env]


# --- runner ------------------------------------------------------------

def _run(args, *, cwd=None):
    """Run ``pixi <args>`` non-interactively in the workspace. Raises PixiError
    on a nonzero exit, with stderr in the message."""
    proc = subprocess.run(
        ["pixi", *args], cwd=str(cwd or WORKSPACE_DIR),
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise PixiError(
            f"`pixi {' '.join(args)}` failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc


def _plugin_features(cwd=None):
    """The current ``plugin-*`` feature names from the manifest."""
    out = _run(feature_list_cmd(), cwd=cwd).stdout
    return sorted(
        line.strip() for line in out.splitlines()
        if line.strip().startswith(FEATURE_PREFIX)
    )


def _snapshot(cwd):
    files = {}
    for name in ("pyproject.toml", "pixi.lock"):
        p = Path(cwd) / name
        if p.exists():
            files[name] = p.read_bytes()
    return files


def _restore(cwd, snapshot):
    for name, data in snapshot.items():
        (Path(cwd) / name).write_bytes(data)


def add_plugin_dependencies(manifest_name, conda, pypi, *, cwd=None):
    """Add a plugin's deps to its feature + the microdrop-plugins env, conflict-
    checked. Snapshot/restore pyproject.toml + pixi.lock on any failure. Raises
    PixiConflictError if the workspace can't be solved with the deps."""
    cwd = Path(cwd or WORKSPACE_DIR)
    feat = feature_name(manifest_name)
    snapshot = _snapshot(cwd)
    try:
        if conda:
            _run(add_conda_cmd(feat, list(conda)), cwd=cwd)
        if pypi:
            _run(add_pypi_cmd(feat, list(pypi)), cwd=cwd)
        _run(env_add_cmd(PLUGINS_ENV, _plugin_features(cwd=cwd)), cwd=cwd)
        try:
            _run(lock_cmd(), cwd=cwd)
        except PixiError as e:
            raise PixiConflictError(
                f"'{manifest_name}' dependencies could not be solved against the "
                f"environment: {e}"
            ) from e
        _run(install_env_cmd(PLUGINS_ENV), cwd=cwd)
    except Exception:
        _restore(cwd, snapshot)
        raise
    logger.info(f"added dependencies for plugin '{manifest_name}' to {PLUGINS_ENV}")


def remove_plugin_dependencies(manifest_name, *, cwd=None):
    """Drop a plugin's feature + update/remove the microdrop-plugins env.
    Best-effort; logs and continues on per-step failure."""
    cwd = Path(cwd or WORKSPACE_DIR)
    feat = feature_name(manifest_name)
    try:
        _run(feature_remove_cmd(feat), cwd=cwd)
    except PixiError as e:
        logger.debug(f"feature remove for '{feat}' skipped: {e}")
        return
    try:
        remaining = _plugin_features(cwd=cwd)
        if remaining:
            _run(env_add_cmd(PLUGINS_ENV, remaining), cwd=cwd)
        else:
            _run(env_remove_cmd(PLUGINS_ENV), cwd=cwd)
    except PixiError as e:
        logger.warning(f"updating {PLUGINS_ENV} after removing '{feat}' failed: {e}")
```

- [ ] **Step 2: Compile**

Run: `python -m py_compile plugin_management/pixi_env.py`
Expected: no output.

- [ ] **Step 3: Pure command-builder smoke (no execution)**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
from plugin_management import pixi_env as px
print(\"feat:\", px.feature_name(\"demo\"))
print(\"add_conda:\", px.add_conda_cmd(\"plugin-demo\", [\"numpy>=1.20\"]))
print(\"add_pypi:\", px.add_pypi_cmd(\"plugin-demo\", [\"boto3\"]))
print(\"env_add:\", px.env_add_cmd(\"microdrop-plugins\", [\"plugin-a\",\"plugin-b\"]))
print(\"lock:\", px.lock_cmd(), \"| install:\", px.install_env_cmd(\"microdrop-plugins\"))
print(\"feat_remove:\", px.feature_remove_cmd(\"plugin-demo\"))
'"
```
Expected:
`feat: plugin-demo`;
`add_conda: ['add', '--no-progress', '--feature', 'plugin-demo', 'numpy>=1.20']`;
`add_pypi: ['add', '--no-progress', '--feature', 'plugin-demo', '--pypi', 'boto3']`;
`env_add: ['workspace', 'environment', 'add', 'microdrop-plugins', '--force', '--feature', 'plugin-a', '--feature', 'plugin-b']`;
`lock: ['lock', '--no-progress'] | install: ['install', '--no-progress', '-e', 'microdrop-plugins']`;
`feat_remove: ['workspace', 'feature', 'remove', 'plugin-demo']`.

- [ ] **Step 4: VERIFY the command sequence against a THROWAWAY pixi project**

This proves the `add --feature` → `environment add` → `lock` sequence actually works on pixi 0.63 (and exposes any flag/order corrections) **without touching the real workspace**. Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c '
set -e
TMP=$(mktemp -d)
cd "$TMP"
pixi init --channel conda-forge >/dev/null 2>&1
pixi add --no-progress --feature plugin-demo tqdm >/dev/null 2>&1 && echo "feature add OK"
pixi workspace environment add microdrop-plugins --force --feature plugin-demo >/dev/null 2>&1 && echo "env add OK"
pixi lock --no-progress >/dev/null 2>&1 && echo "lock solves OK"
pixi workspace feature list 2>/dev/null | grep -q plugin-demo && echo "feature listed OK"
pixi workspace feature remove plugin-demo >/dev/null 2>&1 && echo "feature remove OK"
cd / && rm -rf "$TMP"
'
```
Expected: `feature add OK`, `env add OK`, `lock solves OK`, `feature listed OK`, `feature remove OK`. **If any line is missing**, the corresponding pixi command/flag differs on this pixi version — adjust the matching builder in `pixi_env.py` (and note it in the report) before continuing. (Requires network for the conda solve; if offline, report BLOCKED.)

- [ ] **Step 5: Commit**

```bash
git add plugin_management/pixi_env.py
git commit -m "Add pixi_env: per-plugin feature + microdrop-plugins env with rollback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `relaunch.py` — re-exec into the plugins env

**Files:** Create `plugin_management/relaunch.py`

**Interfaces:**
- Produces: `relaunch_into_plugins_env(application=None) -> None` — quits the app and re-execs the current entry point under `pixi run -e microdrop-plugins`.

- [ ] **Step 1: Create the module**

Create `plugin_management/relaunch.py`:

```python
"""Relaunch the running app into the microdrop-plugins pixi environment so a
just-installed plugin's freshly-added dependencies become importable.

A live interpreter can't safely import packages added to a *different* pixi
environment mid-run, so we re-exec the same entry point under
``pixi run -e microdrop-plugins``.
"""

import os
import sys

from plugin_management.pixi_env import PLUGINS_ENV, WORKSPACE_DIR
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _relaunch_argv():
    """`pixi run -e <env> python <script> <args...>` for the current process."""
    return [
        "pixi", "run", "-e", PLUGINS_ENV,
        "python", *sys.argv,
    ]


def relaunch_into_plugins_env(application=None):
    """Quit the app (if given) and re-exec into the plugins env. Best-effort:
    on failure, logs and returns so the caller can fall back to a message."""
    argv = _relaunch_argv()
    logger.info(f"relaunching into {PLUGINS_ENV}: {' '.join(argv)}")
    try:
        # Ask the envisage app to exit cleanly first (saves window state).
        if application is not None:
            try:
                application.exit()
            except Exception:
                logger.exception("relaunch: application.exit() failed; continuing")
        # Replace this process. os.chdir so pixi finds the workspace manifest.
        os.chdir(str(WORKSPACE_DIR))
        os.execvp(argv[0], argv)
    except Exception:
        logger.exception("relaunch into plugins env failed")
```

- [ ] **Step 2: Compile + import smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c "cd src && python -c '
import sys; sys.argv = [\"examples/run_device_viewer_pluggable.py\", \"--device\", \"mock\"]
from plugin_management.relaunch import _relaunch_argv
print(_relaunch_argv())
'"
```
Expected: `['pixi', 'run', '-e', 'microdrop-plugins', 'python', 'examples/run_device_viewer_pluggable.py', '--device', 'mock']`.

- [ ] **Step 3: Commit**

```bash
git add plugin_management/relaunch.py
git commit -m "Add relaunch helper: re-exec the app into microdrop-plugins env

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Installer integration — allowlist, deps step, `InstallResult`, rollback, uninstall hook

**Files:** Modify `plugin_management/installer.py`

**Interfaces:**
- Consumes: Task 1 `read_plugin_dependencies`/`unsatisfied`; Task 2 `pixi_env.add_plugin_dependencies`/`remove_plugin_dependencies`/`PixiError`.
- Produces: `@dataclass InstallResult(manifest, requires_relaunch: bool)`; `install_from_zip(...) -> InstallResult`; `uninstall_plugin` also removes the plugin's pixi deps.

- [ ] **Step 1: Add imports + `InstallResult`**

In `plugin_management/installer.py`, after the existing imports add:

```python
from dataclasses import dataclass

from plugin_management import pixi_env
from plugin_management.plugin_deps import read_plugin_dependencies, unsatisfied
```

and after the `InstallCancelled` class add:

```python
@dataclass
class InstallResult:
    manifest: object              # PluginManifest
    requires_relaunch: bool       # True if deps were added that need a relaunch
```

- [ ] **Step 2: Allowlist `pyproject.toml`**

In `_validate_entries`, change the allowlist line:

```python
    allowed_tops = set(manifest.packages) | {paths.MANIFEST_FILENAME}
```

to:

```python
    allowed_tops = set(manifest.packages) | {paths.MANIFEST_FILENAME, "pyproject.toml"}
```

- [ ] **Step 3: Deps step + rollback in `install_from_zip`**

In `install_from_zip`, replace the tail:

```python
    _purge_package_modules(manifest.packages)
    paths.ensure_on_sys_path()
    manager.register_manifest(manifest, str(target))
    logger.info(f"installed plugin '{manifest.name}' to {target}")
    return manifest
```

with:

```python
    _purge_package_modules(manifest.packages)
    paths.ensure_on_sys_path()
    manager.register_manifest(manifest, str(target))
    logger.info(f"installed plugin '{manifest.name}' to {target}")

    # Dependency resolution: if the archive declared deps not already importable,
    # add them to a per-plugin pixi feature + the microdrop-plugins env. A solve
    # failure rolls the whole install back so a conflicting plugin never lingers.
    requires_relaunch = False
    deps = read_plugin_dependencies(target / "pyproject.toml")
    missing = unsatisfied(deps)
    if missing:
        logger.info(f"plugin '{manifest.name}' needs dependencies: {missing}")
        try:
            pixi_env.add_plugin_dependencies(manifest.name, deps.conda, deps.pypi)
        except Exception:
            logger.exception(
                f"installing dependencies for '{manifest.name}' failed; "
                f"rolling back the install"
            )
            _rollback_install(manager, manifest, target)
            raise
        requires_relaunch = True

    return InstallResult(manifest=manifest, requires_relaunch=requires_relaunch)


def _rollback_install(manager, manifest, target):
    """Undo a registered+extracted install whose dependency step failed."""
    try:
        manager.deregister_plugin(manifest.name)
    except Exception:
        logger.exception(f"rollback: deregister of '{manifest.name}' failed")
    try:
        pixi_env.remove_plugin_dependencies(manifest.name)
    except Exception:
        logger.exception(f"rollback: pixi cleanup for '{manifest.name}' failed")
    _purge_package_modules(manifest.packages)
    try:
        if Path(target).exists():
            shutil.rmtree(target)
    except Exception:
        logger.exception(f"rollback: rmtree of '{target}' failed")
```

Also update the `install_from_zip` docstring's final sentence from "Returns the PluginManifest." to "Returns an InstallResult (manifest + requires_relaunch).".

- [ ] **Step 4: Remove the plugin's deps on uninstall**

In `uninstall_plugin`, after `manager.deregister_plugin(manifest_name)` and before the `rmtree`, add the pixi cleanup:

```python
    _purge_package_modules(packages)
    manager.deregister_plugin(manifest_name)

    # Drop the plugin's pixi feature from the microdrop-plugins env (best-effort).
    try:
        pixi_env.remove_plugin_dependencies(manifest_name)
    except Exception:
        logger.exception(f"uninstall: pixi cleanup for '{manifest_name}' failed")

    source = Path(source_dir)
```

- [ ] **Step 5: Compile**

Run: `python -m py_compile plugin_management/installer.py`
Expected: no output.

- [ ] **Step 6: Install smoke — no-deps archive returns InstallResult(requires_relaunch=False)**

Run (a plugin with NO pyproject.toml installs unchanged; pixi is never invoked):
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile, zipfile, json
from pathlib import Path
from traits.etsconfig.api import ETSConfig
ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdtest_\")
from plugin_management.group_manager import PluginGroupManager
from plugin_management import installer
m = PluginGroupManager()
tmp = Path(tempfile.mkdtemp())
man={\"schema_version\":1,\"name\":\"demo_plugin\",\"label\":\"D\",\"version\":\"0.1\",\"packages\":[\"demo_pkg\"],\"groups\":[{\"name\":\"demo_group\",\"label\":\"D\",\"plugins\":[\"demo_pkg.plugin:DemoPlugin\"],\"enabled_key\":\"microdrop.demo_enabled\"}]}
arc=tmp/\"d.microdrop_plugin\"
with zipfile.ZipFile(arc,\"w\") as zf:
    zf.writestr(\"microdrop_plugin.json\", json.dumps(man)); zf.writestr(\"demo_pkg/__init__.py\",\"\"); zf.writestr(\"demo_pkg/plugin.py\",\"class DemoPlugin: pass\")
res = installer.install_from_zip(arc, m, confirm=lambda x: True)
print(\"InstallResult manifest:\", res.manifest.name, \"| requires_relaunch:\", res.requires_relaunch)
installer.uninstall_plugin(None, m, \"demo_plugin\")
print(\"uninstalled clean:\", \"demo_group\" not in m.groups)
'"
```
Expected: `InstallResult manifest: demo_plugin | requires_relaunch: False`; `uninstalled clean: True`. (No pixi call — the archive has no `pyproject.toml`.)

- [ ] **Step 7: Commit**

```bash
git add plugin_management/installer.py
git commit -m "Installer: resolve plugin deps via pixi feature + InstallResult/rollback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `InstallPluginAction` relaunch dialog

**Files:** Modify `plugin_management/menus.py`

**Interfaces:**
- Consumes: Task 4 `InstallResult`; Task 3 `relaunch_into_plugins_env`.

- [ ] **Step 1: Update `InstallPluginAction.perform`'s tail**

In `plugin_management/menus.py`, in `InstallPluginAction.perform`, replace the install + success block:

```python
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

with:

```python
        try:
            result = installer.install_from_zip(path, manager, confirm=_consent)
        except installer.InstallCancelled:
            return
        except Exception as e:
            error_dialog(parent=None, title="Install failed", message=str(e))
            return

        label = escape_html_multiline(result.manifest.label)
        if not result.requires_relaunch:
            information(
                parent=None, title="Plugin installed",
                message=f"Installed <b>{label}</b>.<br><br>"
                        f"Enable it from Tools → Manage Plugins.",
            )
            return

        # The plugin pulled in dependencies that were just added to the
        # environment; they only become importable after a relaunch.
        if confirm(parent=None, title="Relaunch required",
                   message=f"Installed <b>{label}</b>.<br><br>It needs additional "
                           f"packages that were added to the environment — they "
                           f"become available after a relaunch.<br><br>"
                           f"Relaunch MicroDrop now?",
                   cancel=False) == YES:
            from plugin_management.relaunch import relaunch_into_plugins_env
            relaunch_into_plugins_env(task.window.application)
        else:
            information(
                parent=None, title="Relaunch later",
                message=f"<b>{label}</b> will be available the next time you "
                        f"launch MicroDrop.",
            )
```

(`escape_html_multiline`, `confirm`, `information`, `error as error_dialog`, `YES` are already imported in `perform` from `pyface_wrapper`.)

- [ ] **Step 2: Compile + introspection smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -m py_compile plugin_management/menus.py && python -c 'import plugin_management.menus as mn; print(\"InstallPluginAction:\", mn.InstallPluginAction().name)'"
```
Expected: no compile output, then `InstallPluginAction: &Install Plugin…`.

- [ ] **Step 3: Commit**

```bash
git add plugin_management/menus.py
git commit -m "Install action: relaunch Yes/No dialog when a plugin adds dependencies

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Integration smoke + manual verification

**Files:** none.

- [ ] **Step 1: Full wiring import smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
from plugin_management.plugin_deps import read_plugin_dependencies, unsatisfied
from plugin_management import pixi_env, installer
from plugin_management.relaunch import relaunch_into_plugins_env
print(\"InstallResult:\", hasattr(installer, \"InstallResult\"))
print(\"PLUGINS_ENV:\", pixi_env.PLUGINS_ENV)
print(\"ALL WIRING OK\")
'"
```
Expected: `InstallResult: True`, `PLUGINS_ENV: microdrop-plugins`, `ALL WIRING OK`.

- [ ] **Step 2: Manual end-to-end (Redis up, `--device mock`)** — tick each; stop + report on failure

- [ ] **No-deps plugin:** install a `.microdrop_plugin` with no `pyproject.toml` (e.g. the magnet demo) → installed with the normal "enable it in Manage Plugins" message, **no** relaunch dialog, **no** change to `microdrop-py/pyproject.toml`/`pixi.lock` (`git status` clean).
- [ ] **Deps plugin, no conflict:** build a demo plugin whose `pyproject.toml` declares one small extra package not already present (e.g. a tiny PyPI pkg) → install → consent → the **Relaunch required** dialog appears; the package is added under a `plugin-<name>` feature + the `microdrop-plugins` env in `pyproject.toml`; `pixi.lock` updated.
- [ ] **Relaunch Yes:** click Yes → the app re-execs into `microdrop-plugins`; after relaunch, enabling the plugin works (its dep imports).
- [ ] **Relaunch No:** click No → "available next launch" message; the plugin stays registered but enabling it now is a clean no-op/aborted (dep missing) until a manual relaunch into the env.
- [ ] **Conflict:** a plugin declaring a dep that can't co-exist with our pins → install is refused with an error dialog, and `git status` shows `pyproject.toml`/`pixi.lock` **unchanged** (snapshot restored) and the plugin dir is gone (rolled back).
- [ ] **Uninstall:** uninstalling a deps plugin removes its `plugin-<name>` feature from `pyproject.toml` and drops it from `microdrop-plugins` (or removes the env if it was the last).

- [ ] **Step 3: Update project memory**

Append to `project_plugin_hot_load_unload.md`: dependency-aware install — an archive may carry a `pyproject.toml` (conda `[tool.pixi.dependencies]` + PyPI `[project.dependencies]`/`[tool.pixi.pypi-dependencies]`); `plugin_deps` parses + `unsatisfied()` checks the running process; `pixi_env` puts missing deps in a `plugin-<name>` feature + the `microdrop-plugins` env (conflict-checked via `pixi lock`, snapshot/rollback); the install action shows a Yes/No **relaunch** dialog only when a dep isn't already importable; `relaunch.py` re-execs `pixi run -e microdrop-plugins`. Mutating pixi edits `microdrop-py/pyproject.toml`+`pixi.lock` (accepted). Tracks issue #491.

---

## Self-Review

**Spec coverage:**
- §Archive addition (pyproject.toml deps + allowlist) → Task 4 Step 2, Task 1. ✓
- §Component 1 (plugin_deps parse + unsatisfied) → Task 1. ✓
- §Component 2 (pixi_env feature/env, conflict-check, snapshot/rollback) → Task 2. ✓
- §Component 3 (installer InstallResult + deps step + conflict rollback + uninstall hook) → Task 4. ✓
- §Component 4 (relaunch UX + helper) → Task 3 (helper) + Task 5 (dialog). ✓
- §Component 5 (launch-time import-abort backstop) → no code (existing `_resolve_factories` behavior); noted in Task 6 manual checks. ✓
- §Verification (guarded temp-project pixi check; manual GUI) → Task 2 Step 4 + Task 6. ✓

**Type consistency:** `PluginDependencies(conda, pypi)` + `read_plugin_dependencies`/`unsatisfied` (Task 1) consumed in Task 4. `pixi_env.add_plugin_dependencies(manifest_name, conda, pypi)`/`remove_plugin_dependencies(manifest_name)`/`PixiError`/`PLUGINS_ENV`/`feature_name` (Task 2) consumed in Tasks 3, 4. `InstallResult(manifest, requires_relaunch)` (Task 4) consumed in Task 5. `relaunch_into_plugins_env(application)` (Task 3) called in Task 5. The action already imports `escape_html_multiline`/`confirm`/`information`/`error as error_dialog`/`YES` (verified against the current `menus.py`).

**Placeholder scan:** none — every code step is complete; commands state expected output. The one deliberate empirical step (Task 2 Step 4) verifies/corrects the exact pixi CLI against the installed pixi rather than guessing.
