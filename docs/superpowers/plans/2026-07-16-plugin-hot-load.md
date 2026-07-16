# Plugin Hot-Load Without Relaunch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a plugin package is installed, decide from a `pixi list --json` diff whether the change is safe to apply to the live interpreter; when it is, re-discover entry points and enable the new plugin's groups so its dock panes appear immediately — no relaunch.

**Architecture:** `package_installer.py` gains an env snapshot/diff and returns an honest `EnvChangeResult`. A new `hot_load.py` owns the gate plus the import/Envisage surgery (`invalidate_caches` → `discover_entry_point_manifests` → `sys.modules` guard → `register_manifest` → `apply`). `relaunch.py` gains a `finish_change()` helper that either shows a confirmation or falls back to today's relaunch prompt. pixi subprocesses run on a worker thread; the hot-load runs on the GUI thread via `run_with_wait`'s `on_success`.

**Tech Stack:** Python 3.13 (pixi default env), Traits/TraitsUI, Envisage, PySide6, pytest, pixi.

**Spec:** `docs/superpowers/specs/2026-07-16-plugin-hot-load-design.md` (read it first — it explains *why* the gate is shaped this way).

## Global Constraints

- **Branch:** work on `feat/plugin-hot-load-spec` in the `microdrop-py/src` submodule. **Never commit to `main`.**
- **Baseline:** this plan builds on two commits that landed just before it — `a303f235` (the `_run(["install"])` calls in `install_from_channel` / `uninstall_package`) and `5be1f242` (`relaunch.py`'s `pixi run microdrop` task form). Do not revert either. The working tree is clean at the start of Task 1; keep it that way by staging only the files each Commit step names — never `git add -A`.
- **f-strings everywhere**, including log messages. Never `%s`, `%r`, or `.format()`.
- **Dialogs** only via `microdrop_application.dialogs.pyface_wrapper`. Never raw `QMessageBox` or `pyface.api` directly.
- **Logging:** `from logger.logger_service import get_logger` then `logger = get_logger(__name__)`.
- **Commits:** Conventional Commits — `type(scope): subject`, imperative, ~50 chars including the prefix. Scope is `plugin_management`.
- **Never mint a new name when an existing one expresses it.** Reuse `_norm_dist`, `apply()`, `run_with_wait`, `confirm_and_relaunch`.
- **TEST POLICY (standing owner preference, used on the four prior features
  in this repo):** **NEVER run pytest** and **never launch the app**
  (`pixi run microdrop`). Write the test files exactly as specified and commit
  them — they are deliverables the owner runs manually.
- **Verify with py_compile + a headless logic smoke instead.** This is the
  established pattern here and it is how you check your work:
  ```bash
  # syntax
  cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && python -m py_compile <files you touched>
  # logic smoke — real execution, no pytest
  cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c '<exercise the function, print the result>'"
  ```
  Always go through `pixi run` for smokes — a bare `python` crashes on
  `import numpy` (`0xc06d007f`) because the env's DLL dirs are off PATH.
  `py_compile` is the exception: it never imports numpy, so bare `python` is fine.
- **Report honestly.** A smoke is not the test suite. Never write "tests
  pass", "verified", or "all green" in a commit message or report — say what
  the smoke printed and that pytest was not run. The committed test files are
  **unrun**; Task 5 (owner-performed) is the real gate.

## File Structure

| File | Responsibility |
|---|---|
| `plugin_management/package_installer.py` (modify) | pixi subprocess layer. Gains `EnvDiff`, `env_snapshot`, `diff_snapshots`, `_parse_list_json`; `InstallResult` → `EnvChangeResult`. Stays Qt-free and knows nothing about plugins or groups. |
| `plugin_management/hot_load.py` (create) | The gate + import/Envisage surgery. Knows nothing about pixi or Qt. |
| `plugin_management/i_plugin_group_manager.py` (modify) | Add `register_manifest` to the service interface. |
| `plugin_management/relaunch.py` (modify) | Add `finish_change(task, msg_html, ok)`. |
| `plugin_management/browse_controller.py` (modify) | Install flow — the path that actually takes the fast lane. |
| `plugin_management/manage_controller.py` (modify) | Install-version / upgrade / uninstall flows. |
| `plugin_management/manage_model.py` (modify) | Return the `EnvChangeResult` from the three worker methods. |
| `plugin_management/tests/test_env_diff.py` (create) | Snapshot + diff unit tests. |
| `plugin_management/tests/test_hot_load.py` (create) | Gate, guard, and orchestration tests. |
| `plugin_management/tests/test_relaunch.py` (create) | `finish_change` branch tests. |
| `plugin_management/tests/test_package_installer.py` (modify) | Drive `requires_relaunch` off a mocked diff. |

`update_controller.py` / `update_model.py` are **deliberately untouched** — `do_update_all` returns `(succeeded, failed)` name lists across many packages, and update-all only ever touches already-installed plugins, so its diff always contains `changed` and it can never take the fast path.

---

### Task 1: Env snapshot and diff

**Files:**
- Modify: `plugin_management/package_installer.py`
- Test: `plugin_management/tests/test_env_diff.py` (create)

**Interfaces:**
- Consumes: `package_installer._run(args, cwd=None)` (existing; raises `InstallError` on non-zero exit), `package_installer.InstallError` (existing).
- Produces:
  - `EnvDiff(added: dict, changed: dict, removed: dict)` — frozen dataclass. `added`/`removed` map `name -> version`; `changed` maps `name -> (old_version, new_version)`. Properties `is_pure_addition` and `is_pure_removal` (both `bool`).
  - `env_snapshot(*, cwd=None) -> dict` — `{name: (version, build, kind)}`.
  - `diff_snapshots(before: dict, after: dict) -> EnvDiff`.
  - `_parse_list_json(stdout: str) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

Create `plugin_management/tests/test_env_diff.py`:

```python
"""Tests for the pixi environment snapshot + diff that gates hot-loading."""
import json

import pytest
from types import SimpleNamespace

from plugin_management import package_installer
from plugin_management.package_installer import (
    EnvDiff, diff_snapshots, env_snapshot)


def _snap(**pkgs):
    """{name: (version, build, kind)} from name="version" kwargs."""
    return {n: (v, "b0", "conda") for n, v in pkgs.items()}


def test_diff_detects_added():
    d = diff_snapshots(_snap(a="1.0"), _snap(a="1.0", b="2.0"))
    assert d.added == {"b": "2.0"}
    assert d.changed == {} and d.removed == {}


def test_diff_detects_removed():
    d = diff_snapshots(_snap(a="1.0", b="2.0"), _snap(a="1.0"))
    assert d.removed == {"b": "2.0"}
    assert d.added == {} and d.changed == {}


def test_diff_detects_changed_version():
    d = diff_snapshots(_snap(a="1.0"), _snap(a="1.1"))
    assert d.changed == {"a": ("1.0", "1.1")}


def test_diff_build_only_change_counts_as_changed():
    """A same-version rebuild replaces files on disk under live modules."""
    before = {"a": ("1.0", "b0", "conda")}
    after = {"a": ("1.0", "b1", "conda")}
    assert diff_snapshots(before, after).changed == {"a": ("1.0", "1.0")}


def test_diff_kind_change_counts_as_changed():
    before = {"a": ("1.0", "b0", "conda")}
    after = {"a": ("1.0", "b0", "pypi")}
    assert diff_snapshots(before, after).changed == {"a": ("1.0", "1.0")}


def test_is_pure_addition_only_when_nothing_else_moved():
    assert EnvDiff({"b": "1"}, {}, {}).is_pure_addition is True
    assert EnvDiff({"b": "1"}, {"a": ("1", "2")}, {}).is_pure_addition is False
    assert EnvDiff({"b": "1"}, {}, {"c": "1"}).is_pure_addition is False


def test_is_pure_removal_only_when_nothing_else_moved():
    assert EnvDiff({}, {}, {"c": "1"}).is_pure_removal is True
    assert EnvDiff({"b": "1"}, {}, {"c": "1"}).is_pure_removal is False
    assert EnvDiff({}, {"a": ("1", "2")}, {"c": "1"}).is_pure_removal is False


def test_env_snapshot_parses_records(monkeypatch):
    payload = [{"name": "numpy", "version": "2.1.0", "build": "py313h0",
                "kind": "conda"}]
    monkeypatch.setattr(package_installer, "_run",
                        lambda a, cwd=None: SimpleNamespace(
                            stdout=json.dumps(payload)))
    assert env_snapshot() == {"numpy": ("2.1.0", "py313h0", "conda")}


def test_env_snapshot_tolerates_leading_warnings(monkeypatch):
    """pixi prints warnings before the JSON, exactly as `search` does."""
    payload = [{"name": "numpy", "version": "2.1.0", "build": "b0",
                "kind": "conda"}]
    stdout = f" WARN something deprecated\n{json.dumps(payload)}"
    monkeypatch.setattr(package_installer, "_run",
                        lambda a, cwd=None: SimpleNamespace(stdout=stdout))
    assert env_snapshot()["numpy"][0] == "2.1.0"


def test_parse_list_json_without_array_raises():
    with pytest.raises(package_installer.InstallError):
        package_installer._parse_list_json("no json here")
```

- [ ] **Step 2: Do not run the tests**

Skip execution (see Global Constraints). For reference, were they run now they
would fail collection with `ImportError: cannot import name 'EnvDiff' from
'plugin_management.package_installer'` — that is the shape of failure the
implementation in Step 3 resolves.

- [ ] **Step 3: Implement**

In `plugin_management/package_installer.py`, add `field`-free dataclass imports if needed (`from dataclasses import dataclass` is already imported) and insert after the existing `InstallResult` dataclass:

```python
@dataclass(frozen=True)
class EnvDiff:
    """What a pixi command did to the environment, keyed by package name.

    ``added``/``removed`` map name -> version; ``changed`` maps
    name -> (old_version, new_version)."""

    added: dict
    changed: dict
    removed: dict

    @property
    def is_pure_addition(self):
        """True when packages were only ADDED — nothing upgraded, downgraded,
        rebuilt or removed. The only shape safe to import into a live
        interpreter."""
        return not self.changed and not self.removed

    @property
    def is_pure_removal(self):
        """True when packages were only REMOVED. Safe after pre_uninstall has
        already disabled the affected groups."""
        return not self.changed and not self.added
```

Add near `_parse_search_json`:

```python
def _parse_list_json(stdout: str) -> list[dict]:
    """Parse `pixi list --json` stdout (which may be preceded by warning
    lines) into the package record list."""
    start = stdout.find("[")
    if start == -1:
        raise InstallError("no JSON array in pixi list output")
    try:
        return json.loads(stdout[start:])
    except ValueError as e:
        raise InstallError(f"could not parse pixi list JSON: {e}") from e


def env_snapshot(*, cwd=None) -> dict:
    """{name: (version, build, kind)} for every package in the workspace env.

    `pixi list` defaults to the platform best matching this machine — the
    same platform, and the same prefix, the running interpreter uses."""
    proc = _run(["list", "--json"], cwd=cwd)
    return {r["name"]: (r["version"], r["build"], r["kind"])
            for r in _parse_list_json(proc.stdout)}


def diff_snapshots(before, after) -> EnvDiff:
    """Classify per-package differences between two env_snapshot() results.

    Compares the FULL (version, build, kind) record, so a same-version
    rebuild counts as changed — it still replaces files on disk underneath
    whatever is already imported."""
    added = {n: rec[0] for n, rec in after.items() if n not in before}
    removed = {n: rec[0] for n, rec in before.items() if n not in after}
    changed = {n: (before[n][0], after[n][0])
               for n in before.keys() & after.keys()
               if before[n] != after[n]}
    return EnvDiff(added=added, changed=changed, removed=removed)
```

- [ ] **Step 4: Syntax check + logic smoke (never pytest)**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && python -m py_compile plugin_management/package_installer.py plugin_management/tests/test_env_diff.py
```
Expected: no output.

Then exercise the diff for real:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c \"
from plugin_management.package_installer import diff_snapshots
before = {'numpy': ('2.1', 'b0', 'conda'), 'gone': ('1.0', 'b0', 'conda')}
after  = {'numpy': ('2.1', 'b1', 'conda'), 'new': ('1.0', 'b0', 'conda')}
d = diff_snapshots(before, after)
print('added', d.added); print('changed', d.changed); print('removed', d.removed)
print('pure_addition', d.is_pure_addition, 'pure_removal', d.is_pure_removal)
\""
```
Expected exactly:
```
added {'new': '1.0'}
changed {'numpy': ('2.1', '2.1')}
removed {'gone': '1.0'}
pure_addition False pure_removal False
```
The `changed` entry proves a build-only bump is caught. If it is absent, the
comparison is on version alone and the gate is unsafe — fix before committing.

- [ ] **Step 5: Commit**

```bash
git add plugin_management/package_installer.py plugin_management/tests/test_env_diff.py
git commit -m "feat(plugin_management): add pixi env snapshot and diff"
```

---

### Task 2: EnvChangeResult and installer wiring

**Files:**
- Modify: `plugin_management/package_installer.py`
- Test: `plugin_management/tests/test_package_installer.py`

**Interfaces:**
- Consumes: `EnvDiff`, `env_snapshot`, `diff_snapshots` (Task 1).
- Produces:
  - `EnvChangeResult(name: str, diff: EnvDiff | None, requires_relaunch: bool)` — replaces `InstallResult`.
  - `install_from_channel(name, channel_url=PLUGIN_CHANNEL_URL, *, cwd=None, version=None) -> EnvChangeResult`
  - `upgrade_package(name, channel_url=PLUGIN_CHANNEL_URL, *, cwd=None) -> EnvChangeResult`
  - `uninstall_package(name, *, cwd=None) -> EnvChangeResult` (previously returned `None`)

- [ ] **Step 1: Write the failing tests**

In `plugin_management/tests/test_package_installer.py`, add to the imports at the top:

```python
from types import SimpleNamespace
```

Then append these tests to the file:

```python
def _rec(name, version, build="b0", kind="conda"):
    return {"name": name, "version": version, "build": build, "kind": kind}


class _FakeRun:
    """Stands in for package_installer._run.

    Serves a different `pixi list --json` payload on each successive `list`
    call, so an install can be made to look purely additive or not."""

    def __init__(self, *list_payloads):
        self.payloads = list(list_payloads)
        self.calls = []

    def __call__(self, args, cwd=None):
        self.calls.append(list(args))
        if args[:1] == ["list"]:
            return SimpleNamespace(stdout=json.dumps(self.payloads.pop(0)))
        return None


def test_install_pure_addition_does_not_require_relaunch(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")
    fake = _FakeRun([_rec("numpy", "2.1.0")],
                    [_rec("numpy", "2.1.0"), _rec("my-plugin", "1.0.0")])
    monkeypatch.setattr(package_installer, "_run", fake)

    result = package_installer.install_from_channel(
        "my-plugin", "https://c", cwd=tmp_path)

    assert result.requires_relaunch is False
    assert result.diff.added == {"my-plugin": "1.0.0"}


def test_install_that_bumps_a_dep_requires_relaunch(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")
    fake = _FakeRun([_rec("numpy", "2.1.0")],
                    [_rec("numpy", "2.2.0"), _rec("my-plugin", "1.0.0")])
    monkeypatch.setattr(package_installer, "_run", fake)

    result = package_installer.install_from_channel(
        "my-plugin", "https://c", cwd=tmp_path)

    assert result.requires_relaunch is True
    assert result.diff.changed == {"numpy": ("2.1.0", "2.2.0")}


def test_install_snapshot_failure_still_installs_and_asks_relaunch(
        tmp_path, monkeypatch):
    """A broken `pixi list` must never break the install — it degrades to the
    relaunch prompt."""
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")

    def fake_run(args, cwd=None):
        if args[:1] == ["list"]:
            raise package_installer.InstallError("list exploded")
        return None
    monkeypatch.setattr(package_installer, "_run", fake_run)

    result = package_installer.install_from_channel(
        "my-plugin", "https://c", cwd=tmp_path)

    assert result.name == "my-plugin"
    assert result.diff is None
    assert result.requires_relaunch is True


def test_uninstall_pure_removal_does_not_require_relaunch(tmp_path, monkeypatch):
    fake = _FakeRun([_rec("numpy", "2.1.0"), _rec("my-plugin", "1.0.0")],
                    [_rec("numpy", "2.1.0")])
    monkeypatch.setattr(package_installer, "_run", fake)

    result = package_installer.uninstall_package("my-plugin", cwd=tmp_path)

    assert result.requires_relaunch is False
    assert result.diff.removed == {"my-plugin": "1.0.0"}


def test_uninstall_failure_requires_relaunch(tmp_path, monkeypatch):
    """`pixi remove` failing is swallowed (existing contract) but must never
    claim the hot path."""
    def fake_run(args, cwd=None):
        if args[:1] == ["remove"]:
            raise package_installer.InstallError("boom")
        return SimpleNamespace(stdout=json.dumps([_rec("numpy", "2.1.0")]))
    monkeypatch.setattr(package_installer, "_run", fake_run)

    result = package_installer.uninstall_package("my-plugin", cwd=tmp_path)

    assert result.diff is None
    assert result.requires_relaunch is True
```

Also update the existing `test_install_from_channel_adds_and_returns` — its `_run` fake returns `None`, so the snapshot fails and `requires_relaunch` stays `True` for the *right* reason now. Make that explicit by replacing its final assertion block with:

```python
    assert ["add", "scipy_analysis"] in calls
    assert result.name == "scipy_analysis"
    # The fake _run returns None, so snapshotting fails -> unknown -> relaunch.
    assert result.diff is None
    assert result.requires_relaunch is True
```

- [ ] **Step 2: Do not run the tests**

Skip execution (see Global Constraints). For reference: the five new tests
would fail with `AttributeError: 'NoneType' object has no attribute
'requires_relaunch'` from `uninstall_package`, and `assert True is False` on
the pure-addition tests, since the current code hardcodes
`requires_relaunch=True`.

- [ ] **Step 3: Implement**

In `plugin_management/package_installer.py`, replace the `InstallResult` dataclass with:

```python
@dataclass
class EnvChangeResult:
    """The outcome of an env-mutating pixi command.

    ``diff`` is None when the environment could not be snapshotted; callers
    must treat that as 'unknown' and relaunch."""

    name: str
    diff: EnvDiff | None
    requires_relaunch: bool
```

Add these helpers below `diff_snapshots`:

```python
def _try_snapshot(cwd):
    """env_snapshot() or None. Snapshotting must never break an install: it
    runs through _run, which raises InstallError on a non-zero exit."""
    try:
        return env_snapshot(cwd=cwd)
    except Exception as e:
        logger.warning(f"could not snapshot the pixi environment: {e}")
        return None


def _diff_or_none(before, after):
    """EnvDiff, or None when either snapshot is missing."""
    if before is None or after is None:
        return None
    return diff_snapshots(before, after)
```

Replace the body of `install_from_channel` (keep its existing docstring's first paragraph, updated) with:

```python
def install_from_channel(name, channel_url=PLUGIN_CHANNEL_URL, *, cwd=None,
                         version=None) -> EnvChangeResult:
    """Register the channel and `pixi add <name>` so the solver resolves the
    package + its deps. When ``version`` is given, pin it (`pixi add
    <name>==<version>`) to install that specific version (down/upgrade).
    Snapshot/restore pyproject + lock on any failure.

    Snapshots the environment either side of the install so the caller can
    tell a purely-additive change (hot-loadable) from one that moved a
    package already imported by this interpreter (needs a relaunch)."""
    cwd = Path(cwd or WORKSPACE_DIR)
    snapshot = _snapshot(cwd)
    before = _try_snapshot(cwd)
    spec = f"{name}=={version}" if version else name
    try:
        _ensure_channel_registered(channel_url, cwd)
        _run(["add", spec], cwd=cwd)
        _run(["install"], cwd=cwd)
    except Exception:
        _restore(cwd, snapshot)
        raise
    diff = _diff_or_none(before, _try_snapshot(cwd))
    logger.info(f"installed plugin '{spec}' from {channel_url}")
    return EnvChangeResult(
        name=name, diff=diff,
        requires_relaunch=diff is None or not diff.is_pure_addition)
```

Update `upgrade_package`'s return annotation to `-> EnvChangeResult` (body unchanged).

Replace `uninstall_package` with:

```python
def uninstall_package(name, *, cwd=None) -> EnvChangeResult:
    """`pixi remove <name>` + `pixi install`. Best-effort: a failure is logged,
    not raised, and reports requires_relaunch=True so a failed removal never
    claims the hot path."""
    cwd = Path(cwd or WORKSPACE_DIR)
    before = _try_snapshot(cwd)
    try:
        _run(["remove", name], cwd=cwd)
        _run(["install"], cwd=cwd)
    except InstallError as e:
        logger.warning(f"`pixi remove {name}` failed: {e}")
        return EnvChangeResult(name=name, diff=None, requires_relaunch=True)
    diff = _diff_or_none(before, _try_snapshot(cwd))
    return EnvChangeResult(
        name=name, diff=diff,
        requires_relaunch=diff is None or not diff.is_pure_removal)
```

- [ ] **Step 4: Syntax-check only**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && python -m py_compile plugin_management/package_installer.py plugin_management/tests/test_package_installer.py
```
Expected: no output. Do **not** run pytest.

For the owner's later manual run: `test_install_from_channel_rolls_back`
should still pass unchanged — its fake `_run` returns `None` for the `list`
call, `_try_snapshot` swallows the resulting `AttributeError`, and the `add`
call still raises, so the rollback assertion holds.

- [ ] **Step 5: Verify no stale references to the old name**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && grep -rn "InstallResult" --include=*.py .
```
Expected: no output. If anything matches, update it to `EnvChangeResult`.

- [ ] **Step 6: Commit**

```bash
git add plugin_management/package_installer.py plugin_management/tests/test_package_installer.py
git commit -m "feat(plugin_management): compute requires_relaunch from diff"
```

---

### Task 3: The hot-load gate and guard

**Files:**
- Create: `plugin_management/hot_load.py`
- Modify: `plugin_management/i_plugin_group_manager.py`
- Test: `plugin_management/tests/test_hot_load.py` (create)

**Interfaces:**
- Consumes: `EnvDiff` (Task 1); `entry_point_discovery.discover_entry_point_manifests() -> [(PluginManifest, dist_name)]`; `PluginGroupManager._norm_dist(name) -> str`; `PluginGroupManager.register_manifest(manifest, dist_name="")`; `PluginGroupManager.apply(application, desired)`; `PluginGroupManager.is_loaded(group_name) -> bool`; `PluginManifest.groups -> [PluginGroupSpec]`; `PluginGroupSpec.name`, `PluginGroupSpec.plugins -> ["module.path:ClassName"]`.
- Produces:
  - `hot_load.hot_load_installed(application, manager, dist_name, diff) -> bool` — True when the plugin is live; False means the caller must offer the relaunch prompt. **GUI thread only.**
  - `hot_load._live_modules(manifest) -> generator[str]`

- [ ] **Step 1: Write the failing tests**

Create `plugin_management/tests/test_hot_load.py`:

```python
"""Tests for the hot-load gate: when may a just-installed plugin be applied
to the LIVE app instead of relaunching?"""
import sys

import pytest

from plugin_management import group_manager, hot_load
from plugin_management.group_manager import PluginGroupManager
from plugin_management.manifest import manifest_from_dict
from plugin_management.package_installer import EnvDiff
from plugin_management.tests.test_group_manager_adoption import FakeApp

PURE_ADDITION = EnvDiff(added={"my-plugin": "1.0"}, changed={}, removed={})
BUMPED_DEP = EnvDiff(added={"my-plugin": "1.0"},
                     changed={"numpy": ("2.1", "2.2")}, removed={})

DIST = "my-microdrop-plugin"


@pytest.fixture(autouse=True)
def isolated_preferences(monkeypatch):
    """Keep enable/disable from writing the REAL application preferences."""
    from apptools.preferences.api import Preferences
    store = Preferences()
    monkeypatch.setattr(group_manager, "get_default_preferences",
                        lambda: store)
    return store


@pytest.fixture
def dummy_module(tmp_path, monkeypatch):
    """A real, importable, TOP-LEVEL module that is not yet in sys.modules.

    The guard keys on the top-level package name, so a dummy living inside
    `plugin_management` would always trip it — this has to be its own root."""
    (tmp_path / "hotload_dummy_pkg.py").write_text(
        "from envisage.plugin import Plugin\n"
        "\n"
        "class HotDummyPlugin(Plugin):\n"
        "    id = 'hotload_dummy_pkg.plugin'\n",
        encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "hotload_dummy_pkg"
    sys.modules.pop("hotload_dummy_pkg", None)


def _manifest(module):
    return manifest_from_dict({
        "schema_version": 1,
        "name": "my_plugin",
        "packages": [module],
        "groups": [{
            "name": "my_group",
            "plugins": [f"{module}:HotDummyPlugin"],
            "enabled_key": "plugin_group_enabled.my_group",
        }],
    })


def _patch_discovery(monkeypatch, manifest, dist=DIST):
    monkeypatch.setattr(hot_load, "discover_entry_point_manifests",
                        lambda: [(manifest, dist)])


def test_hot_loads_and_enables_a_pure_addition(monkeypatch, dummy_module):
    _patch_discovery(monkeypatch, _manifest(dummy_module))
    app, manager = FakeApp(), PluginGroupManager()

    assert hot_load.hot_load_installed(app, manager, DIST, PURE_ADDITION) is True
    assert manager.is_loaded("my_group")
    assert [c for c in app.calls if c[0] == "add"] == [("add", "HotDummyPlugin")]


def test_refuses_when_diff_is_none(monkeypatch, dummy_module):
    _patch_discovery(monkeypatch, _manifest(dummy_module))
    manager = PluginGroupManager()
    assert hot_load.hot_load_installed(FakeApp(), manager, DIST, None) is False
    assert "my_group" not in manager.groups


def test_refuses_when_a_dep_was_bumped(monkeypatch, dummy_module):
    _patch_discovery(monkeypatch, _manifest(dummy_module))
    manager = PluginGroupManager()
    assert hot_load.hot_load_installed(
        FakeApp(), manager, DIST, BUMPED_DEP) is False
    assert "my_group" not in manager.groups


def test_refuses_when_nothing_was_discovered(monkeypatch):
    monkeypatch.setattr(hot_load, "discover_entry_point_manifests", lambda: [])
    assert hot_load.hot_load_installed(
        FakeApp(), PluginGroupManager(), DIST, PURE_ADDITION) is False


def test_refuses_when_dist_name_does_not_match(monkeypatch, dummy_module):
    _patch_discovery(monkeypatch, _manifest(dummy_module), dist="someone-else")
    assert hot_load.hot_load_installed(
        FakeApp(), PluginGroupManager(), DIST, PURE_ADDITION) is False


def test_dist_name_match_ignores_case_and_underscores(monkeypatch, dummy_module):
    _patch_discovery(monkeypatch, _manifest(dummy_module),
                     dist="My_Microdrop_Plugin")
    assert hot_load.hot_load_installed(
        FakeApp(), PluginGroupManager(), DIST, PURE_ADDITION) is True


def test_refuses_when_the_module_is_already_imported(monkeypatch, dummy_module):
    """Reinstall-after-uninstall: the lock diff says 'pure addition', but
    import_module would hand back the STALE module."""
    import importlib
    importlib.import_module(dummy_module)          # simulate it being live
    _patch_discovery(monkeypatch, _manifest(dummy_module))
    manager = PluginGroupManager()

    assert hot_load.hot_load_installed(
        FakeApp(), manager, DIST, PURE_ADDITION) is False
    assert "my_group" not in manager.groups


def test_refuses_when_a_colliding_group_is_loaded(monkeypatch, dummy_module):
    manifest = _manifest(dummy_module)
    _patch_discovery(monkeypatch, manifest)
    app, manager = FakeApp(), PluginGroupManager()
    manager.register_manifest(manifest, dist_name=DIST)
    manager.enable(app, "my_group")               # already live

    assert hot_load.hot_load_installed(
        app, manager, DIST, PURE_ADDITION) is False


def test_refuses_when_the_plugin_cannot_be_imported(monkeypatch):
    """A manifest pointing at a module that does not exist: enable() cannot
    resolve it, the group never loads, and relaunch is a real remedy."""
    _patch_discovery(monkeypatch, _manifest("hotload_missing_pkg"))
    manager = PluginGroupManager()
    assert hot_load.hot_load_installed(
        FakeApp(), manager, DIST, PURE_ADDITION) is False


def test_live_modules_keys_on_the_top_level_package():
    """`plugin_management` is always imported here, so a spec nested under it
    must report the ROOT package, not the leaf module."""
    manifest = _manifest("plugin_management.tests.whatever")
    assert list(hot_load._live_modules(manifest)) == ["plugin_management"]
```

- [ ] **Step 2: Do not run the tests**

Skip execution (see Global Constraints). For reference, they would fail
collection with `ModuleNotFoundError: No module named
'plugin_management.hot_load'`.

- [ ] **Step 3: Create `plugin_management/hot_load.py`**

```python
"""Apply a freshly-installed plugin to the LIVE app instead of relaunching.

``pixi install`` writes into the same site-packages the running interpreter
imports from, so a brand-new package is importable without a restart —
``enable()`` already imports never-before-seen plugin code every time a group
is toggled on. What is NOT safe is upgrading or removing an already-imported
package: modules cannot be un-imported, live objects keep their old classes,
and on Windows a loaded .pyd/.dll cannot be replaced.

Two INDEPENDENT checks gate the fast path:

1. The env diff must be purely additive (``EnvDiff.is_pure_addition``).
2. None of the modules ``enable()`` would import may already be in
   ``sys.modules``. The diff alone reports a reinstall-after-uninstall as a
   pure addition, but ``import_module`` would hand back the stale module and
   silently run the old code under the new version's name.

Anything unexpected returns False and the caller falls back to the relaunch
prompt — always correct, just slower.
"""
import importlib
import sys

from plugin_management.entry_point_discovery import (
    discover_entry_point_manifests)
from plugin_management.group_manager import PluginGroupManager
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _live_modules(manifest):
    """Top-level modules ``enable()`` would import that are ALREADY loaded.

    Keys on exactly what ``group_manager._resolve_plugin_class`` imports,
    rather than mapping package names to modules — conda names, python dist
    names and module names all differ, and native libs map to no dist at all,
    so any mapping-based check under-reports in the unsafe direction."""
    for spec in manifest.groups:
        for plugin_spec in spec.plugins:          # "module.path:ClassName"
            top = plugin_spec.partition(":")[0].split(".")[0]
            if top in sys.modules:
                yield top


def hot_load_installed(application, manager, dist_name, diff) -> bool:
    """Register + enable a just-installed distribution's plugin groups on the
    live application.

    GUI THREAD ONLY: mutates the manager's traits and fires the
    TASK_EXTENSIONS delta that LiveTaskExtensionsController reconciles into
    mounted dock panes.

    Returns True when the plugin is live and no relaunch is needed; False
    means the caller must offer the relaunch prompt."""
    try:
        return _hot_load_installed(application, manager, dist_name, diff)
    except Exception:
        logger.exception(
            f"hot-load of '{dist_name}' failed; falling back to relaunch")
        return False


def _hot_load_installed(application, manager, dist_name, diff):
    if diff is None or not diff.is_pure_addition:
        logger.info(f"hot-load refused for '{dist_name}': the env change is "
                    f"not purely additive")
        return False

    # The metadata cache is mtime-keyed and would self-invalidate, but the
    # FileFinder / sys.path_importer_cache layer that enable()'s
    # import_module goes through is not.
    importlib.invalidate_caches()

    norm = PluginGroupManager._norm_dist
    mine = [(m, d) for m, d in discover_entry_point_manifests()
            if norm(d) == norm(dist_name)]
    if not mine:
        logger.warning(
            f"hot-load refused: no manifest discovered for '{dist_name}'")
        return False

    for manifest, _ in mine:
        live = sorted(set(_live_modules(manifest)))
        if live:
            logger.info(f"hot-load refused for '{dist_name}': modules already "
                        f"imported: {live}")
            return False

    names = []
    try:
        for manifest, dist in mine:
            manager.register_manifest(manifest, dist_name=dist)
            names += [g.name for g in manifest.groups]
    except RuntimeError as e:
        logger.warning(f"hot-load refused for '{dist_name}': {e}")
        return False

    # apply() rather than enable(): it is the public reconcile entry point AND
    # it persists the enabled flag, so a hot-installed plugin comes back on
    # the next launch exactly like a toggled one.
    manager.apply(application, {n: True for n in names})

    not_loaded = [n for n in names if not manager.is_loaded(n)]
    if not_loaded:
        logger.warning(f"hot-load of '{dist_name}' left groups unloaded: "
                       f"{not_loaded}; relaunch needed")
        return False

    logger.info(f"hot-loaded '{dist_name}': enabled groups {names}")
    return True
```

- [ ] **Step 4: Add `register_manifest` to the interface**

In `plugin_management/i_plugin_group_manager.py`, add after the `groups` trait and before `is_loaded`:

```python
    def register_manifest(self, manifest, dist_name="") -> None:
        """Register a freshly-installed manifest's groups at runtime. Raises
        if a colliding group name is currently loaded."""
```

- [ ] **Step 5: Syntax check + logic smoke (never pytest)**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && python -m py_compile plugin_management/hot_load.py plugin_management/i_plugin_group_manager.py plugin_management/tests/test_hot_load.py
```
Expected: no output.

Then prove the two refusal paths without any plugin installed:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c \"
from plugin_management import hot_load
from plugin_management.package_installer import EnvDiff
from plugin_management.manifest import manifest_from_dict
bumped = EnvDiff(added={'p': '1'}, changed={'numpy': ('2.1','2.2')}, removed={})
print('bumped dep ->', hot_load.hot_load_installed(None, None, 'p', bumped))
print('diff None  ->', hot_load.hot_load_installed(None, None, 'p', None))
m = manifest_from_dict({'schema_version': 1, 'name': 'x', 'packages': ['plugin_management'],
    'groups': [{'name': 'g', 'plugins': ['plugin_management.tests.z:C'],
                'enabled_key': 'plugin_group_enabled.g'}]})
print('live modules ->', list(hot_load._live_modules(m)))
\""
```
Expected exactly:
```
bumped dep -> False
diff None  -> False
live modules -> ['plugin_management']
```
Both refusals must return before touching `application`/`manager` (both passed
as `None` here) — if either raises `AttributeError`, the gate is checking in
the wrong order. `live modules` proves the guard keys on the ROOT package.

- [ ] **Step 6: Re-read hot_load.py against the spec**

Since nothing is executed, this read is the only correctness check available.
Confirm by eye, against
`docs/superpowers/specs/2026-07-16-plugin-hot-load-design.md` §3-§4:
the gate refuses a non-pure-addition diff *before* any import work; the
`sys.modules` guard runs *before* `register_manifest`; `apply()` is used
rather than `enable()`; and the `is_loaded` check runs after `apply()`.

- [ ] **Step 7: Commit**

```bash
git add plugin_management/hot_load.py plugin_management/i_plugin_group_manager.py plugin_management/tests/test_hot_load.py
git commit -m "feat(plugin_management): add hot-load gate and guard"
```

---

### Task 4: Wire the controllers

**Files:**
- Modify: `plugin_management/relaunch.py`
- Modify: `plugin_management/browse_controller.py:77-95`
- Modify: `plugin_management/manage_controller.py:151-196`
- Modify: `plugin_management/manage_model.py:174-199`
- Test: `plugin_management/tests/test_relaunch.py` (create)

**Interfaces:**
- Consumes: `hot_load.hot_load_installed(application, manager, dist_name, diff) -> bool` (Task 3); `EnvChangeResult.diff` / `.requires_relaunch` (Task 2); `relaunch.confirm_and_relaunch(task, msg_html)` (existing); `information(parent, message, title)` from `microdrop_application.dialogs.pyface_wrapper` (existing); `IPluginGroupManager` (existing service interface).
- Produces: `relaunch.finish_change(task, msg_html, ok) -> None`.

- [ ] **Step 1: Write the failing test**

Create `plugin_management/tests/test_relaunch.py`:

```python
"""finish_change picks the right ending: a plain confirmation when the change
is already live, the relaunch offer when it is not."""
from plugin_management import relaunch


def test_finish_change_informs_when_already_live(monkeypatch):
    seen = {}
    monkeypatch.setattr(relaunch, "information",
                        lambda **kw: seen.update(kw))
    monkeypatch.setattr(relaunch, "confirm_and_relaunch",
                        lambda *a: seen.update(relaunched=True))

    relaunch.finish_change(None, "Installed and enabled <b>X</b>.", True)

    assert seen["message"] == "Installed and enabled <b>X</b>."
    assert "relaunched" not in seen


def test_finish_change_offers_relaunch_when_not_live(monkeypatch):
    seen = {}
    monkeypatch.setattr(relaunch, "information",
                        lambda **kw: seen.update(informed=True))
    monkeypatch.setattr(relaunch, "confirm_and_relaunch",
                        lambda task, msg: seen.update(msg=msg))

    relaunch.finish_change(None, "Installed <b>X</b>.", False)

    assert seen["msg"] == "Installed <b>X</b>."
    assert "informed" not in seen
```

- [ ] **Step 2: Do not run the test**

Skip execution (see Global Constraints). For reference, it would fail with
`AttributeError: module 'plugin_management.relaunch' has no attribute
'finish_change'`.

- [ ] **Step 3: Add `finish_change` to `relaunch.py`**

Append to `plugin_management/relaunch.py`:

```python
def finish_change(task, msg_html, ok):
    """Report the outcome of an env change. ``ok`` means it is already live —
    say so and stop. Otherwise fall back to the standard relaunch offer."""
    if ok:
        information(parent=None, title="Plugin ready", message=msg_html)
        return
    confirm_and_relaunch(task, msg_html)
```

- [ ] **Step 4: Do not run the test**

Skip execution. Syntax-check instead:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && python -m py_compile plugin_management/relaunch.py plugin_management/tests/test_relaunch.py
```
Expected: no output.

- [ ] **Step 5: Wire `browse_controller.py`**

Replace the import on line 20:

```python
from plugin_management.hot_load import hot_load_installed
from plugin_management.i_plugin_group_manager import IPluginGroupManager
from plugin_management.relaunch import finish_change
```

Replace the `run_with_wait(...)` block at the end of `install_selected` with:

```python
        run_with_wait(
            lambda: model.do_install(pkg.name, pkg.version),
            title="Installing plugin",
            message=f"Installing {pkg.name} {pkg.version}…",
            on_success=lambda r: self._finish_install(pkg, r),
            on_error=lambda e: error_dialog(
                parent=None, title="Install failed", message=str(e)))
```

Add these two methods to `BrowsePluginsHandler`:

```python
    def _finish_install(self, pkg, result):
        """GUI thread: try to apply the install live, then report."""
        ok = self._hot_load(pkg.name, result)
        name = escape_html_multiline(pkg.name)
        version = escape_html_multiline(pkg.version)
        verb = "Installed and enabled" if ok else "Installed"
        finish_change(self.task, f"{verb} <b>{name}</b> {version}.", ok)

    def _hot_load(self, dist_name, result):
        """False (relaunch) whenever the live application or its group manager
        is unreachable — e.g. the standalone installer demo."""
        application = getattr(
            getattr(self.task, "window", None), "application", None)
        if application is None:
            return False
        manager = application.get_service(IPluginGroupManager)
        if manager is None:
            return False
        return hot_load_installed(application, manager, dist_name, result.diff)
```

- [ ] **Step 6: Wire `manage_model.py`**

Add `return` to the three worker methods so the controller's `on_success(r)` receives the result:

```python
    def do_install_version(self, dist_name, version):
        """Install a specific version of a package (version dropdown select)."""
        return package_installer.install_from_channel(dist_name, version=version)

    def do_upgrade(self, dist_name):
        """Upgrade a package to the latest channel version (upgrade button)."""
        return package_installer.upgrade_package(dist_name)

    def do_uninstall(self, dist_name):
        """Worker-thread safe: remove the package (no trait mutation)."""
        return package_installer.uninstall_package(dist_name)
```

- [ ] **Step 7: Wire `manage_controller.py`**

Replace the import on line 35 (`from .relaunch import confirm_and_relaunch`) with:

```python
from .hot_load import hot_load_installed
from .relaunch import finish_change
```

Replace `_after_change` (lines 204-205) with:

```python
    def _hot_load(self, dist_name, result):
        """GUI thread: try to apply an install live. The model already holds
        the application and the group manager."""
        return hot_load_installed(self.model.application, self.model.manager,
                                  dist_name, result.diff)
```

In `_prompt_install_version`, replace the `done=` callback with:

```python
                  done=lambda r: (self.model.refresh_installed(),
                                  finish_change(
                                      self.task,
                                      f"Installed <b>{_esc(label)}</b> "
                                      f"{_esc(new_version)}.",
                                      self._hot_load(dist, r))))
```

In `_on_upgrade`, replace the `done=` callback with:

```python
                  done=lambda r: (self.model.refresh_installed(),
                                  finish_change(
                                      self.task,
                                      f"Upgraded <b>{_esc(label)}</b>.",
                                      self._hot_load(dist, r))))
```

In `_on_uninstall`, replace the `done=` callback with (no hot-load call —
`pre_uninstall` already unloaded the groups and there is nothing to import):

```python
                  done=lambda r: (self.model.refresh_installed(),
                                  finish_change(
                                      self.task,
                                      f"Uninstalled <b>{_esc(label)}</b>.",
                                      not r.requires_relaunch)))
```

- [ ] **Step 8: Verify no stale relaunch wiring remains**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && grep -rn "confirm_and_relaunch\|_after_change" --include=*.py plugin_management/
```
Expected: matches ONLY in `relaunch.py` (the definition and `finish_change`'s fallback) and `update_controller.py` (deliberately untouched). No matches in `browse_controller.py` or `manage_controller.py`.

- [ ] **Step 9: Syntax-check only**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && python -m py_compile plugin_management/relaunch.py plugin_management/browse_controller.py plugin_management/manage_controller.py plugin_management/manage_model.py plugin_management/tests/test_relaunch.py
```
Expected: no output. Do **not** run pytest.

- [ ] **Step 10: Commit**

```bash
git add plugin_management/relaunch.py plugin_management/browse_controller.py plugin_management/manage_controller.py plugin_management/manage_model.py plugin_management/tests/test_relaunch.py
git commit -m "feat(plugin_management): hot-load installs, skip relaunch"
```

---

### Task 5: Manual verification — PERFORMED BY THE OWNER, NOT BY AN AGENT

**Agents: do not execute this task.** Do not launch the app, do not run
pytest. Stop after Task 4, report what was written and that none of it has
been run, and hand these steps to the owner.

Nothing in Tasks 1-4 has been executed, so this is the *only* correctness
gate the change gets. The owner may also want to run the unit suite once here:
`cd microdrop-py && pixi run bash -c "cd src && QT_QPA_PLATFORM=offscreen pytest plugin_management/tests/ -v"`.

**Prerequisite:** Redis must be running (`redis-server`, or `python examples/start_redis_server.py`).

- [ ] **Step 1: Launch the app**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run microdrop
```

- [ ] **Step 2: Fresh install takes the fast path**

Tools → Browse Plugins → select `heater-microdrop-plugin` (not currently installed) → Install → accept the consent dialog.

Expected: a **"Plugin ready"** dialog reading "Installed and enabled …", **no relaunch prompt**, and the heater dock pane + menu entries appear without restarting. The log shows `hot-loaded 'heater-microdrop-plugin': enabled groups [...]`.

- [ ] **Step 3: Uninstall takes the fast path**

Tools → Manage Plugins → uninstall the heater plugin.

Expected: **no relaunch prompt**; the pane disappears.

- [ ] **Step 4: Reinstall in the same session is REFUSED (the key case)**

Without restarting, Browse Plugins → install `heater-microdrop-plugin` again.

Expected: **a relaunch prompt**. The log shows `hot-load refused for 'heater-microdrop-plugin': modules already imported: ['peripheral_controller']`. This proves the `sys.modules` guard — if this silently hot-loads instead, the guard is broken and the plan must not be marked complete.

- [ ] **Step 5: Upgrade is REFUSED**

Manage Plugins → upgrade `magnet-microdrop-plugin`.

Expected: **a relaunch prompt**; the log shows the refusal naming the changed package.

- [ ] **Step 6: Record the outcome**

Report each step's actual result. If any step deviates, stop and report rather than marking the plan complete.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 Env snapshot + diff | Task 1 |
| §1 `EnvChangeResult` rename, uninstall failure contract, model methods return | Tasks 2, 4 |
| §2 Gate rules (install pure-addition / uninstall pure-removal) | Tasks 2 (rules), 3 (enforcement) |
| §3 Hot-load orchestration + `apply()` + `is_loaded` check | Task 3 |
| §4 `sys.modules` guard | Task 3 |
| §5 Error handling (snapshot failure, broad except, known `enable()` gap) | Tasks 2, 3 |
| §6 Threading (worker installs, GUI-thread hot-load) | Task 4 |
| §7 `finish_change` + controller integration; `update_controller` untouched | Task 4 |
| §7 `register_manifest` on `IPluginGroupManager` | Task 3 |
| Testing (unit) | Tasks 1-4 |
| Testing (manual) | Task 5 |

No spec requirement is unimplemented.

**Type consistency:** `EnvDiff(added, changed, removed)` and its `is_pure_addition` / `is_pure_removal` properties are used identically in Tasks 1, 2 and 3. `EnvChangeResult(name, diff, requires_relaunch)` is produced in Task 2 and consumed as `r.diff` / `r.requires_relaunch` in Task 4. `hot_load_installed(application, manager, dist_name, diff)` is defined in Task 3 and called with that exact argument order in Task 4.
