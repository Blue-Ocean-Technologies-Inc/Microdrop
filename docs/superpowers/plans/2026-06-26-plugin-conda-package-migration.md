# Plugins-as-conda-packages Full Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every MicroDrop plugin an installed conda package (built with `pixi-build-python`, installed from a `.conda` via a local conda channel + `pixi add`, deps resolved by pixi) discovered via Python entry points; migrate magnet; and delete the `.microdrop_plugin` zip system, `pixi_env.py`, app-data extraction, and JSON directory discovery.

**Architecture:** A plugin = a `pixi-build-python` conda package advertising a `microdrop.plugins` entry point + a package-data `microdrop_plugin.toml`. Install copies the built `.conda` into a local channel, `pixi add`s it (conda solver resolves deps), and relaunches. Discovery is entry-points-only; bundled (dist == `microdrop_py`) vs installed (any other dist) is decided by the entry point's distribution. The existing runtime (`PluginGroupManager.enable/disable` + reactive mounting) is reused unchanged.

**Tech Stack:** pixi 0.63.2 (`pixi-build-python` preview backend, local conda channels), Python `importlib.metadata`/`importlib.resources`/`tomllib`, Envisage/Pyface, the `plugin_management` package.

## Global Constraints

- **Built file = conda `.conda`**, produced by `pixi build`. Install = local conda channel + `pixi add`; uninstall = `pixi remove`. **No `pixi_env.py`** (pixi resolves deps).
- **Discovery = entry points only**, group `microdrop.plugins` (exact). The `MICRODROP_ENTRYPOINT_PLUGINS` flag and `default_plugins/` JSON directory discovery are removed.
- **Bundled vs installed = distribution:** an entry point whose `dist` is the app's own (`microdrop_py`/`microdrop-py`, normalized by lowercasing and `_`↔`-`) is **bundled/disable-only**; any other dist is **installed/uninstallable**.
- **Default environment** for installs. Installing mutates the workspace `pyproject.toml` + `pixi.lock` (reverted by `pixi remove`); snapshot+rollback both on any install failure.
- **R1 is the go/no-go:** local-channel install must work on pixi 0.63 / win-64 before any teardown (Task 6). Task 1 nails the exact commands; later tasks use exactly those.
- **No pytest** (project convention): verify via `py_compile` + `pixi run` import/CLI smokes + manual GUI. Mutating-pixi smokes run only in guarded/throwaway contexts or are reverted — never left committed against the workspace.
- **TOML manifest** mirrors the JSON shape: `schema_version=1`, `name`, `label`, `version`, `packages` (non-empty), `groups[{name,label,plugins:["module:Class"],enabled_key,post_enable_publish_topic?}]`.
- Work from `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src` (submodule, branch `feat/plugin_management`). The magnet entry point edits the **outer** `microdrop-py/pyproject.toml` (committed in the outer repo). Commit messages end with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

## File structure

**New (submodule):**
- `plugin_management/package_installer.py` — install/uninstall a conda `.conda` via local channel + pixi.
- `examples/build_plugin_conda.py` — build the demo plugin's `.conda` (replaces `build_plugin_zip.py`).
- `peripheral_controller/microdrop_plugin.toml` — magnet group manifest (package data).

**Modified:**
- `plugin_management/paths.py` — replace app-data `installed_plugins/`+`sys.path`+`iter_manifest_dirs` with `plugin_channel_dir()`.
- `plugin_management/entry_point_discovery.py` — always-on; record each entry point's `dist` name.
- `plugin_management/group_manager.py` — discovery from entry points only; `PluginGroup.dist_name`; `installed_plugins()` by dist.
- `plugin_management/manifest.py` — drop JSON file-loading `load_manifest` (keep `manifest_from_dict` + dataclasses + `ManifestError`).
- `plugin_management/menus.py` — `.conda` install + package uninstall actions.
- `plugin_management/uninstall_dialog.py` — list installed packages (unchanged tuple shape).
- Outer `microdrop-py/pyproject.toml` — magnet `[project.entry-points."microdrop.plugins"]`.

**Removed:** `plugin_management/installer.py`, `plugin_management/pixi_env.py`, `examples/build_plugin_zip.py`, `default_plugins/magnet_peripherals/microdrop_plugin.json` (and the `default_plugins/` tree), `examples/demo_plugins/scipy_analysis/` (the zip demo).

---

### Task 1: R1 — nail the local-channel install commands (GO/NO-GO)

**Files:** none committed (exploratory; records the exact working command sequence).

**Interfaces:**
- Produces: the verified command sequence for (a) building a plugin `.conda`, (b) indexing a local channel dir, (c) registering the channel, (d) `pixi add`/`pixi remove`. The controller records these and feeds them into Task 2. No git commit.

This task mutates a THROWAWAY pixi project (never the real workspace) and needs the network. If pixi can't fetch the build backend / index a local channel, report BLOCKED.

- [ ] **Step 1: Build the spike plugin into a `.conda`**

Run (the spike package already exists at `examples/demo_plugins/scipy_analysis_pkg/`):
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c '
set -e
OUT=$(mktemp -d)
pixi build --manifest-path src/examples/demo_plugins/scipy_analysis_pkg/pyproject.toml --output-dir "$OUT" 2>&1 | tail -5
ls -la "$OUT"
echo "BUILT_DIR=$OUT"
'
```
Expected: a `scipy_analysis-0.1.0-*.conda` file in `$OUT`. If `pixi build` needs different flags, find the working form and record it.

- [ ] **Step 2: Stand up a THROWAWAY consuming project + local channel and install from the built file**

Run (everything in a throwaway dir; never touch the real workspace):
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run bash -c '
set -e
TMP=$(mktemp -d); CH="$TMP/channel"; PROJ="$TMP/proj"
mkdir -p "$CH/noarch" "$PROJ"
# 1) put the built .conda into the channel (copy from Step 1 output dir):
cp <BUILT_DIR>/scipy_analysis-0.1.0-*.conda "$CH/noarch/"
# 2) INDEX the channel — try, in order, whichever works on this pixi:
( pixi exec rattler-index "$CH" ) || ( python -m conda_index "$CH" ) || echo "INDEX_TRY_FAILED"
ls -R "$CH" | head
# 3) consuming project that adds the local channel + the package:
cd "$PROJ"; pixi init --channel conda-forge >/dev/null 2>&1
pixi workspace channel add "file://$CH" 2>&1 | tail -2
pixi add scipy_analysis 2>&1 | tail -5
pixi list 2>/dev/null | grep -E "scipy_analysis|scipy " && echo "INSTALL OK"
pixi remove scipy_analysis 2>&1 | tail -2 && echo "REMOVE OK"
rm -rf "$TMP"
'
```
Expected: the channel indexes, `pixi workspace channel add` + `pixi add scipy_analysis` resolves and installs `scipy_analysis` **and** scipy, `INSTALL OK`, then `REMOVE OK`. Try the indexing alternatives in order; record which one works (and the exact `pixi build` / channel-add / add / remove forms).

- [ ] **Step 3: Record the verified sequence (no commit)**

Write the exact working commands (build, index, channel-add, add, remove — with the real flags) into the task report. **If no indexing method makes `pixi add` resolve the local package**, report NO-GO with what was tried; the controller decides the fallback (direct `.conda` path dep, or wheel+pypi) before any further task. There is no code commit for this task.

---

### Task 2: `package_installer.py` + channel dir (install/uninstall a `.conda`)

**Files:**
- Modify: `plugin_management/paths.py`
- Create: `plugin_management/package_installer.py`
- Create: `examples/build_plugin_conda.py`

**Interfaces:**
- Consumes: Task 1's verified command sequence (the controller supplies the exact `build`/`index`/`channel add` forms in the dispatch).
- Produces: `paths.plugin_channel_dir() -> Path`; `package_installer.InstallResult(name: str, requires_relaunch: bool)`, `InstallError`, `InstallCancelled`, `package_name_from_conda(path) -> str`, `install_conda_file(conda_path, *, confirm=None) -> InstallResult`, `uninstall_package(name) -> None`.

- [ ] **Step 1: Repurpose `paths.py` for the local channel dir**

Replace the body of `plugin_management/paths.py` with (drops app-data `installed_plugins/` + `sys.path` + `iter_manifest_dirs`, which the conda-package model no longer uses):
```python
"""Filesystem location of the local conda channel that holds installed plugin
packages (built .conda files), under the app-data dir."""

from pathlib import Path

from traits.etsconfig.api import ETSConfig


def plugin_channel_dir() -> Path:
    """The local conda channel dir (under ETSConfig.application_home) into which
    installed plugin .conda files are copied + indexed. Created if missing, with
    a noarch/ subdir (conda channels are organised by subdir)."""
    path = Path(ETSConfig.application_home) / "plugin_channel"
    (path / "noarch").mkdir(parents=True, exist_ok=True)
    return path
```

- [ ] **Step 2: Create `package_installer.py`**

Create `plugin_management/package_installer.py`. Use the EXACT pixi commands the controller recorded from R1 in the marked spots (`_INDEX_CMD`, `_channel_add_cmd`, `pixi add`, `pixi remove`):
```python
"""Install/uninstall a plugin distributed as a built conda package (.conda).

The .conda is copied into a local conda channel under app-data, the channel is
indexed + registered with the workspace, and ``pixi add <name>`` installs the
package — letting the conda solver resolve the plugin's run-dependencies. No
custom dependency wiring. Qt-free; snapshots pyproject.toml + pixi.lock for
rollback.
"""
import json
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

from plugin_management import paths
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: pixi workspace root (microdrop-py/, parent of src/).
WORKSPACE_DIR = Path(__file__).resolve().parents[2]


class InstallError(Exception):
    """A .conda is malformed/unsafe, or pixi could not install it."""


class InstallCancelled(Exception):
    """The user declined at the consent prompt."""


@dataclass
class InstallResult:
    name: str
    requires_relaunch: bool


def _run(args, *, cwd=None):
    proc = subprocess.run(["pixi", *args], cwd=str(cwd or WORKSPACE_DIR),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise InstallError(
            f"`pixi {' '.join(args)}` failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def package_name_from_conda(conda_path) -> str:
    """The conda package name read from the .conda's info/index.json (a .conda is
    a zip containing an info-*.tar.zst; we read the embedded index.json)."""
    p = Path(conda_path)
    try:
        with zipfile.ZipFile(p) as zf:
            info_member = next(n for n in zf.namelist()
                               if n.startswith("info-") and n.endswith(".tar.zst"))
            import tarfile, zstandard
            with zf.open(info_member) as raw:
                dctx = zstandard.ZstdDecompressor()
                with dctx.stream_reader(raw) as r, tarfile.open(fileobj=r, mode="r|") as tar:
                    for m in tar:
                        if m.name.lstrip("./") == "info/index.json":
                            data = json.loads(tar.extractfile(m).read().decode("utf-8"))
                            return data["name"]
    except Exception as e:
        raise InstallError(f"could not read package name from {p.name}: {e}") from e
    raise InstallError(f"{p.name} has no info/index.json")


def _snapshot(cwd):
    files = {}
    for name in ("pyproject.toml", "pixi.lock"):
        fp = Path(cwd) / name
        if fp.exists():
            files[name] = fp.read_bytes()
    return files


def _restore(cwd, snapshot):
    for name, data in snapshot.items():
        (Path(cwd) / name).write_bytes(data)


def _index_channel(channel_dir):
    # <<< R1: replace with the verified indexing command (e.g. rattler-index) >>>
    _run(["exec", "rattler-index", str(channel_dir)])


def _ensure_channel_registered(channel_dir, cwd):
    # <<< R1: verified `pixi workspace channel add` form; idempotent >>>
    url = (Path(channel_dir)).as_uri()
    try:
        _run(["workspace", "channel", "add", url], cwd=cwd)
    except InstallError as e:
        if "already" not in str(e).lower():
            raise


def install_conda_file(conda_path, *, confirm=None, cwd=None) -> InstallResult:
    """Copy a built .conda into the local channel, index+register it, and
    ``pixi add`` the package (resolving its deps). Snapshot/restore pyproject +
    lock on any failure. Returns InstallResult(name, requires_relaunch=True)."""
    cwd = Path(cwd or WORKSPACE_DIR)
    src = Path(conda_path)
    if src.suffix != ".conda" or not src.is_file():
        raise InstallError(f"{src.name} is not a .conda file")
    name = package_name_from_conda(src)

    if confirm is not None and not confirm(name):
        raise InstallCancelled(f"install of '{name}' declined")

    channel = paths.plugin_channel_dir()
    dest = channel / "noarch" / src.name
    snapshot = _snapshot(cwd)
    copied = False
    try:
        shutil.copy2(src, dest); copied = True
        _index_channel(channel)
        _ensure_channel_registered(channel, cwd)
        _run(["add", name], cwd=cwd)          # solver resolves name + deps
    except Exception:
        _restore(cwd, snapshot)
        if copied:
            dest.unlink(missing_ok=True)
            _index_channel_safe(channel)
        raise
    logger.info(f"installed plugin package '{name}' from {src.name}")
    return InstallResult(name=name, requires_relaunch=True)


def _index_channel_safe(channel_dir):
    try:
        _index_channel(channel_dir)
    except Exception as e:
        logger.debug(f"re-index after rollback failed: {e}")


def uninstall_package(name, *, cwd=None) -> None:
    """`pixi remove <name>` then drop its .conda(s) from the local channel.
    Best-effort; logs on per-step failure."""
    cwd = Path(cwd or WORKSPACE_DIR)
    try:
        _run(["remove", name], cwd=cwd)
    except InstallError as e:
        logger.warning(f"`pixi remove {name}` failed: {e}")
    channel = paths.plugin_channel_dir()
    for conda in (channel / "noarch").glob(f"{name}-*.conda"):
        try:
            conda.unlink()
        except OSError as e:
            logger.debug(f"could not delete {conda.name}: {e}")
    _index_channel_safe(channel)
```

Note: `zstandard` is available in the env (a conda-forge dep of the toolchain); if the R1 report shows it absent, the controller will say so and you import it lazily with a clear `InstallError`. Do NOT add a new dependency without the controller's go-ahead.

- [ ] **Step 3: Create the author build helper `examples/build_plugin_conda.py`**

```python
"""Build the scipy_analysis demo plugin into a .conda artifact (the install
format). Replaces build_plugin_zip.py — plugins are now conda packages.

Usage: pixi run python examples/build_plugin_conda.py [output_dir]
"""
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent / "demo_plugins" / "scipy_analysis_pkg"


def build(output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pixi", "build", "--manifest-path", str(PKG / "pyproject.toml"),
         "--output-dir", str(out)],
        check=True,
    )
    built = sorted(out.glob("scipy_analysis-*.conda"))
    print(f"built: {built[-1] if built else '(none found)'}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "dist_plugins")
```

- [ ] **Step 4: Compile + guarded install smoke**

Run (py_compile, then a GUARDED install into a throwaway-home so the real workspace pyproject isn't mutated — uses the .conda built by the helper):
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi run python -m py_compile src/plugin_management/paths.py src/plugin_management/package_installer.py src/examples/build_plugin_conda.py && echo "py_compile OK" && \
pixi run bash -c "cd src && python -c '
import tempfile
from pathlib import Path
from traits.etsconfig.api import ETSConfig
ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdhome_\")
from plugin_management import paths
print(\"channel dir:\", paths.plugin_channel_dir().name, \"(noarch exists:\", (paths.plugin_channel_dir()/\"noarch\").is_dir(), \")\")
from plugin_management import package_installer as pi
print(\"InstallResult/InstallError/funcs present:\", all(hasattr(pi, n) for n in (\"InstallResult\",\"InstallError\",\"install_conda_file\",\"uninstall_package\",\"package_name_from_conda\")))
'"
```
Expected: `py_compile OK`; `channel dir: plugin_channel (noarch exists: True )`; `InstallResult/.../present: True`. (The full install path — copy/index/add — is exercised end-to-end manually in Task 7, since it mutates a real channel + solves; this task verifies the module loads + the channel dir.)

- [ ] **Step 5: Commit**

```bash
git add plugin_management/paths.py plugin_management/package_installer.py examples/build_plugin_conda.py
git commit -m "Add package_installer: install/uninstall a plugin .conda via local channel + pixi

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Migrate magnet to an entry point (keep JSON for now)

**Files:**
- Create: `peripheral_controller/microdrop_plugin.toml`
- Modify (OUTER repo): `microdrop-py/pyproject.toml`

**Interfaces:**
- Produces: magnet discoverable via the `microdrop.plugins` entry point on the `microdrop_py` distribution.

- [ ] **Step 1: Create the magnet TOML manifest (package data)**

`peripheral_controller/microdrop_plugin.toml` (same content as `default_plugins/magnet_peripherals/microdrop_plugin.json`, in TOML):
```toml
schema_version = 1
name = "magnet_peripherals"
label = "Magnet Peripherals"
version = "1.0.0"
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

- [ ] **Step 2: Declare the magnet entry point on the main package**

In the OUTER `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/pyproject.toml`, add to `[project]` (create the table if absent):
```toml
[project.entry-points."microdrop.plugins"]
magnet_peripherals = "peripheral_controller"
```
Then re-install so the editable `microdrop_py` dist-info picks up the new entry point:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi install 2>&1 | tail -5
```

- [ ] **Step 3: Verify magnet is discoverable via the entry point**

Run (entry-point discovery is still flag-gated at this point — turn it on for the check):
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && MICRODROP_ENTRYPOINT_PLUGINS=1 pixi run bash -c "cd src && python -c '
import importlib.metadata as md
eps = [(e.name, e.module, e.dist.name) for e in md.entry_points(group=\"microdrop.plugins\")]
print(\"entry points:\", eps)
from plugin_management import entry_point_discovery as ep
found = [(m.name, [g.name for g in m.groups]) for m, src in ep.discover_entry_point_manifests()]
print(\"discovered manifests:\", found)
'"
```
Expected: the entry points include `('magnet_peripherals', 'peripheral_controller', 'microdrop-py')` (dist name may render as `microdrop-py` or `microdrop_py`); `discovered manifests:` includes `('magnet_peripherals', ['magnet_backend', 'magnet_ui'])`. (`scipy_analysis` may also appear if still installed — fine.)

- [ ] **Step 4: Commit (submodule only; the outer pyproject is committed separately by the controller)**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src
git add peripheral_controller/microdrop_plugin.toml
git commit -m "Magnet: add microdrop_plugin.toml package-data manifest (entry-point discovery)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(The outer `microdrop-py/pyproject.toml` magnet entry-point change is committed in the OUTER repo by the controller — note it in the report; do not try to commit it from the submodule.)

---

### Task 4: Discovery → entry-points-only + distribution classification

**Files:**
- Modify: `plugin_management/entry_point_discovery.py`
- Modify: `plugin_management/group_manager.py`

**Interfaces:**
- Consumes: Task 3 (magnet entry point exists).
- Produces: `discover_entry_point_manifests() -> [(PluginManifest, dist_name)]` (always on); `PluginGroup.dist_name`; `group_manager._discover_groups` uses entry points only; `installed_plugins()` keyed on dist.

- [ ] **Step 1: `entry_point_discovery.py` — always on, record dist**

Replace `plugin_management/entry_point_discovery.py` with:
```python
"""Discover installed plugin packages via Python entry points.

A plugin package advertises a ``microdrop.plugins`` entry point (value = its
importable package) and ships a ``microdrop_plugin.toml`` as package data. We
read that TOML into the same PluginManifest the rest of PluginGroupManager
consumes, and record the entry point's distribution name so callers can tell a
bundled plugin (shipped by the app's own distribution) from an installed one.
"""
import importlib.metadata as importlib_metadata
import importlib.resources as importlib_resources
import tomllib

from plugin_management.manifest import manifest_from_dict, ManifestError
from logger.logger_service import get_logger

logger = get_logger(__name__)

ENTRY_POINT_GROUP = "microdrop.plugins"
MANIFEST_RESOURCE = "microdrop_plugin.toml"


def _dist_name(ep) -> str:
    dist = getattr(ep, "dist", None)
    name = getattr(dist, "name", "") if dist is not None else ""
    return (name or "").strip()


def discover_entry_point_manifests():
    """``[(PluginManifest, dist_name)]`` for every installed package advertising a
    ``microdrop.plugins`` entry point and shipping a ``microdrop_plugin.toml``.
    Best-effort: a bad package is logged and skipped, never raised."""
    found = []
    for ep in importlib_metadata.entry_points(group=ENTRY_POINT_GROUP):
        pkg = ep.module
        try:
            resource = importlib_resources.files(pkg) / MANIFEST_RESOURCE
            data = tomllib.loads(resource.read_text(encoding="utf-8"))
            manifest = manifest_from_dict(data)
        except (ManifestError, OSError, ValueError, ModuleNotFoundError,
                tomllib.TOMLDecodeError) as e:
            logger.exception(f"skipping entry-point plugin '{pkg}': {e}")
            continue
        found.append((manifest, _dist_name(ep)))
    return found
```

- [ ] **Step 2: `group_manager.py` — entry-points-only discovery + `dist_name`**

In `plugin_management/group_manager.py`:

(a) Replace the `source_dir = Str()` trait on `PluginGroup` with `dist_name = Str()` (keep `manifest_name`/`manifest_label`).

(b) Replace `_discover_groups` body with entry-points-only discovery:
```python
    def _discover_groups(self):
        """Build the group map from every microdrop.plugins entry point.
        Reads package-data TOML only (no plugin imports), so a broken installed
        plugin can't break discovery."""
        from plugin_management import entry_point_discovery
        groups = {}
        for manifest, dist_name in entry_point_discovery.discover_entry_point_manifests():
            self._add_manifest_groups(manifest, dist_name=dist_name, into=groups)
        return groups
```

(c) Update `_add_manifest_groups` to take `dist_name` (replacing `source_dir`):
```python
    def _add_manifest_groups(self, manifest, dist_name="", into=None):
        """Create a PluginGroup per spec in ``manifest`` and put it in ``into``
        (defaults to self.groups). ``dist_name`` is the owning distribution (for
        bundled-vs-installed classification). Last writer wins on a collision."""
        target = self.groups if into is None else into
        for spec in manifest.groups:
            target[spec.name] = PluginGroup(
                name=spec.name,
                label=spec.label,
                plugin_specs=list(spec.plugins),
                enabled_key=spec.enabled_key,
                post_enable_publish_topic=spec.post_enable_publish_topic,
                manifest_name=manifest.name,
                manifest_label=manifest.label,
                dist_name=dist_name,
            )
```

(d) Update `register_manifest` to pass `dist_name` instead of `source_dir`:
```python
    def register_manifest(self, manifest, dist_name=""):
        """Register a freshly-installed manifest's groups at runtime. Refuses
        (raises) if a colliding group name is currently loaded."""
        for spec in manifest.groups:
            existing = self.groups.get(spec.name)
            if existing is not None and existing.loaded:
                raise RuntimeError(
                    f"group '{spec.name}' is currently enabled; disable it "
                    f"before reinstalling")
        self._add_manifest_groups(manifest, dist_name=dist_name)
```

(e) Replace `installed_plugins()` with distribution-based classification:
```python
    #: The app's own distribution — its plugins are bundled (disable-only).
    APP_DIST_NAMES = frozenset({"microdrop-py", "microdrop_py"})

    @staticmethod
    def _norm_dist(name):
        return (name or "").strip().lower().replace("_", "-")

    def installed_plugins(self):
        """User-installed plugins (whose owning distribution is NOT the app's
        own), one entry per distinct manifest, as (name, label, dist_name,
        [group_names]) in discovery order. Bundled plugins are excluded."""
        app = {self._norm_dist(n) for n in self.APP_DIST_NAMES}
        out = {}
        for group in self.groups.values():
            if self._norm_dist(group.dist_name) in app or not group.dist_name:
                continue
            entry = out.get(group.manifest_name)
            if entry is None:
                entry = (group.manifest_name,
                         group.manifest_label or group.manifest_name,
                         group.dist_name, [])
                out[group.manifest_name] = entry
            entry[3].append(group.name)
        return list(out.values())
```
`installed_plugin(name)` and `deregister_plugin(name)` are unchanged (they key on `manifest_name`). Remove the now-unused `from plugin_management import paths` import and the `Path` import if they become unused.

- [ ] **Step 3: Verify discovery + classification (headless)**

Run (no flag needed now — always on):
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig; ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdhome_\")
from plugin_management.group_manager import PluginGroupManager
m = PluginGroupManager()
print(\"groups:\", sorted(m.groups))
print(\"installed (non-bundled):\", [(n, d) for n, _l, d, _g in m.installed_plugins()])
print(\"magnet bundled (not in installed):\", \"magnet_peripherals\" not in [e[0] for e in m.installed_plugins()])
'"
```
Expected: `groups:` includes `magnet_backend`, `magnet_ui` (and `scipy_analysis` if its package is installed); `magnet bundled (not in installed): True` (magnet's dist is microdrop-py). If `scipy_analysis` is installed, it appears in `installed (non-bundled)` with dist `scipy_analysis`.

- [ ] **Step 4: Commit**

```bash
git add plugin_management/entry_point_discovery.py plugin_management/group_manager.py
git commit -m "Discovery: entry-points-only + distribution-based bundled/installed classification

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: UI — `.conda` install + package uninstall actions

**Files:**
- Modify: `plugin_management/menus.py`
- Modify: `plugin_management/uninstall_dialog.py`

**Interfaces:**
- Consumes: Task 2 `package_installer`; Task 4 `installed_plugins()` (tuples `(name, label, dist_name, [groups])`).

- [ ] **Step 1: Rewrite `InstallPluginAction` + `UninstallPluginAction` in `menus.py`**

Replace the `InstallPluginAction` class body's `perform` with a `.conda` flow:
```python
class InstallPluginAction(TaskAction):
    """Pick a built plugin package (.conda) and install it via pixi. Shows an
    informed-consent dialog, then `pixi add`s the package (the solver resolves
    its dependencies) and offers a relaunch."""

    id = "install_plugin_action"
    name = "&Install Plugin…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Install Plugin: no task available")
            return
        from microdrop_application.dialogs.pyface_wrapper import (
            file_dialog, confirm, information, error as error_dialog, YES,
            escape_html_multiline,
        )
        from plugin_management import package_installer

        path = file_dialog(
            parent=None, action="open",
            wildcard="MicroDrop plugin package (*.conda)|*.conda",
        )
        if not path:
            return

        def _consent(name):
            safe = escape_html_multiline(name)
            body = (
                f"Install the plugin package <b>{safe}</b>?<br><br>"
                f"pixi will install it and resolve its dependencies into the "
                f"environment.<br><br>"
                f"<b>Warning:</b> installing runs third-party code that has not "
                f"been verified. Only install plugins you trust."
            )
            return confirm(parent=None, message=body,
                           title="Install Plugin?", cancel=False) == YES

        try:
            result = package_installer.install_conda_file(path, confirm=_consent)
        except package_installer.InstallCancelled:
            return
        except Exception as e:
            error_dialog(parent=None, title="Install failed", message=str(e))
            return

        safe = escape_html_multiline(result.name)
        if confirm(parent=None, title="Relaunch required",
                   message=f"Installed <b>{safe}</b>.<br><br>Its packages become "
                           f"available after a relaunch.<br><br>"
                           f"Relaunch MicroDrop now?",
                   cancel=False) == YES:
            from plugin_management.relaunch import relaunch_into_plugins_env
            relaunch_into_plugins_env(task.window.application)
        else:
            information(parent=None, title="Relaunch later",
                       message=f"<b>{safe}</b> will be available the next time "
                               f"you launch MicroDrop.")
```

Replace `UninstallPluginAction.perform`'s install-specific bits to call `package_installer.uninstall_package` and offer a relaunch (the `installed_plugins()` tuple is now `(name, label, dist_name, [groups])`):
```python
class UninstallPluginAction(TaskAction):
    """Uninstall a user-installed plugin package (auto-disable its loaded
    groups, then `pixi remove`). Bundled plugins are not listed."""

    id = "uninstall_plugin_action"
    name = "&Uninstall Plugin…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Uninstall Plugin: no task available")
            return
        from microdrop_application.dialogs.pyface_wrapper import (
            confirm, information, error as error_dialog, YES, escape_html_multiline,
        )
        from plugin_management.i_plugin_group_manager import IPluginGroupManager
        from plugin_management import package_installer
        from plugin_management.uninstall_dialog import UninstallPluginModel

        manager = task.window.application.get_service(IPluginGroupManager)
        if manager is None:
            logger.error("Uninstall Plugin: PluginGroupManager service not found")
            return

        installed = manager.installed_plugins()
        if not installed:
            information(parent=None, title="Uninstall Plugin",
                       message="No installed plugin packages to uninstall.")
            return

        model = UninstallPluginModel(installed)
        ui = model.edit_traits(kind="livemodal")
        if not ui.result:
            return
        name = model.selected
        label = {n: l for n, l, _d, _g in installed}.get(name, name)
        groups = {n: g for n, _l, _d, g in installed}.get(name, [])
        safe_label = escape_html_multiline(label)
        if confirm(parent=None,
                   message=f"Uninstall <b>{safe_label}</b>?<br><br>"
                           f"This removes its package from the environment.",
                   title="Uninstall Plugin?", cancel=False) != YES:
            return
        try:
            for group_name in groups:
                if manager.is_loaded(group_name):
                    manager.disable(task, group_name)
            manager.deregister_plugin(name)
            package_installer.uninstall_package(name)
        except Exception as e:
            error_dialog(parent=None, title="Uninstall failed", message=str(e))
            return
        if confirm(parent=None, title="Relaunch required",
                   message=f"Uninstalled <b>{safe_label}</b>.<br><br>Relaunch "
                           f"MicroDrop now to finish removing it?",
                   cancel=False) == YES:
            from plugin_management.relaunch import relaunch_into_plugins_env
            relaunch_into_plugins_env(task.window.application)
```
`ManagePluginsAction` is unchanged.

- [ ] **Step 2: Confirm `uninstall_dialog.py` accepts the tuple shape**

`UninstallPluginModel(installed)` already takes `[(name, label, _dir, _groups)]`; the tuple is now `(name, label, dist_name, [groups])` — same positional shape, so no change is needed. Read `plugin_management/uninstall_dialog.py` and confirm it only uses positions 0 (name) and 1 (label); if it references the 3rd element as a path, adjust it to treat position 2 as an opaque label. (Expected: no change.)

- [ ] **Step 3: Compile + introspection smoke**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -m py_compile plugin_management/menus.py plugin_management/uninstall_dialog.py && python -c 'import plugin_management.menus as mn; print(\"actions:\", mn.InstallPluginAction().name, \"|\", mn.UninstallPluginAction().name)'"
```
Expected: no compile output; `actions: &Install Plugin… | &Uninstall Plugin…`.

- [ ] **Step 4: Commit**

```bash
git add plugin_management/menus.py plugin_management/uninstall_dialog.py
git commit -m "UI: install plugins from .conda + uninstall via pixi remove (relaunch offers)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Remove the old system

**Files:**
- Remove: `plugin_management/installer.py`, `plugin_management/pixi_env.py`, `examples/build_plugin_zip.py`, `default_plugins/magnet_peripherals/microdrop_plugin.json`, `examples/demo_plugins/scipy_analysis/` (the whole dir).
- Modify: `plugin_management/manifest.py` (drop `load_manifest`), any module importing the removed names.

- [ ] **Step 1: Find every reference to the modules being removed**

Run:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src && \
grep -rn "from plugin_management import installer\|plugin_management.installer\|import pixi_env\|plugin_management.pixi_env\|load_manifest\|iter_manifest_dirs\|ensure_on_sys_path\|installed_plugins_dir\|build_plugin_zip\|\.microdrop_plugin" --include=*.py plugin_management examples microdrop_application | grep -v "package_installer"
```
Expected: references only in files this task edits/removes (`menus.py` already rewritten in Task 5 no longer imports `installer`; if any stray reference remains, it must be cleaned here). Record the list.

- [ ] **Step 2: Drop `load_manifest` from `manifest.py`**

In `plugin_management/manifest.py`, delete the `load_manifest` function and the now-unused `import json` and `from pathlib import Path` / `Union` if unused. Keep `manifest_from_dict`, `ManifestError`, `PluginManifest`, `PluginGroupSpec`, `SCHEMA_VERSION`.

- [ ] **Step 3: Remove the dead files**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src
git rm plugin_management/installer.py plugin_management/pixi_env.py examples/build_plugin_zip.py default_plugins/magnet_peripherals/microdrop_plugin.json
git rm -r examples/demo_plugins/scipy_analysis
# remove the default_plugins/ tree if now empty:
rmdir default_plugins/magnet_peripherals default_plugins 2>/dev/null || true
```

- [ ] **Step 4: Resolve any remaining import breakage + drop the legacy `paths.py` symbols**

Re-run the Step 1 grep; for each remaining reference (e.g. `plugin.py` importing `paths.ensure_on_sys_path`, or a restore hook calling removed code), edit it to the new API or delete the dead call. The launch-restore in `plugin.py` should no longer call `ensure_on_sys_path` (packages are installed in the env, already importable). **Then, once no caller references them, delete the now-unused legacy functions from `plugin_management/paths.py`** — `default_plugins_dir`, `installed_plugins_dir`, `ensure_on_sys_path`, `iter_manifest_dirs`, `MANIFEST_FILENAME`, and the `sys`/`Iterator`/`_PROJECT_ROOT` they used — leaving only `plugin_channel_dir()` (these were kept additively in Task 2 so intermediate commits stayed working). Then verify the package imports clean:
```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import plugin_management.manifest, plugin_management.paths, plugin_management.entry_point_discovery, plugin_management.group_manager, plugin_management.menus, plugin_management.package_installer, plugin_management.plugin
print(\"plugin_management imports clean\")
import tempfile
from traits.etsconfig.api import ETSConfig; ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdhome_\")
from plugin_management.group_manager import PluginGroupManager
print(\"magnet discovered:\", \"magnet_ui\" in PluginGroupManager().groups)
'"
```
Expected: `plugin_management imports clean`; `magnet discovered: True`.

- [ ] **Step 5: Commit**

```bash
git add -A plugin_management examples default_plugins
git commit -m "Remove the zip-install system: installer.py, pixi_env.py, JSON manifests, app-data discovery

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: End-to-end verification (headless + manual GUI)

**Files:** none (verification + spike write-up).

- [ ] **Step 1: Headless full-chain smoke**

```bash
cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c '
import tempfile
from traits.etsconfig.api import ETSConfig; ETSConfig.application_home = tempfile.mkdtemp(prefix=\"mdhome_\")
from plugin_management.group_manager import PluginGroupManager
m = PluginGroupManager()
print(\"groups:\", sorted(m.groups))
print(\"installed pkgs:\", [(n,d) for n,_l,d,_g in m.installed_plugins()])
import plugin_management.package_installer, plugin_management.menus  # import surface intact
print(\"OK\")
'"
```
Expected: magnet groups present; `OK`. (`scipy_analysis` appears under installed pkgs if its `.conda` is still installed from R1/Task 3.)

- [ ] **Step 2: Manual GUI end-to-end** (Redis up; tick each; the demo `.conda` built via `pixi run python examples/build_plugin_conda.py`)

- [ ] Launch `pixi run microdrop`. **Magnet** appears in Tools → Manage Plugins and enables (dock pane + status icon + protocol column) — proves the entry-point/TOML migration of a bundled plugin.
- [ ] **Tools → Install Plugin…** → pick the demo `scipy_analysis-*.conda` → consent → install runs `pixi add`, resolves scipy → **Relaunch required** → Yes.
- [ ] After relaunch: **Manage Plugins** lists **Scipy Random Analysis**; enable → the scipy histogram + KDE dock pane renders.
- [ ] **Tools → Uninstall Plugin…** lists scipy_analysis (NOT magnet) → uninstall → `pixi remove` → relaunch → it's gone; magnet still works.
- [ ] `git status` of the OUTER `microdrop-py/pyproject.toml`: contains the magnet entry point (committed) but no leftover `scipy_analysis` dep after uninstall.

- [ ] **Step 3: Record the migration outcome** in the task report (what worked, any rough edges: build time, index step, relaunch, dist classification). No code commit.

---

## Self-review notes for the executor

- **Hard gate:** Task 1 (R1) is the go/no-go. If local-channel install can't be made to work, STOP — the controller picks a fallback install mechanic before Tasks 2-7.
- **Ordering rationale:** magnet's entry point (Task 3) and the discovery switch (Task 4) land BEFORE the teardown (Task 6), so magnet never disappears. The new install code (Task 2) and UI (Task 5) land before removing the old installer (Task 6).
- **Outer-repo change:** only the magnet entry point in `microdrop-py/pyproject.toml` is an outer-repo edit; the controller commits it in the outer repo. Everything else is submodule.
- Additive-then-subtractive: nothing is deleted until its replacement is in place and verified.
