# Plugin Remote-Channel Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the local-`.conda` file install flow with a Browse Plugins dialog that lists packages from the hosted conda channel, shows per-package details on demand, caches the list to app-data, and installs the selected package with `pixi`.

**Architecture:** A new MVC trio (`browse_model` / `browse_view` / `browse_controller`) mirrors the existing Manage-Plugins split. The data layer (`package_installer.search_channel` / `read_cached_index`) runs `pixi search --json` and caches the result to app-data. The "Install Plugin…" button repoints from a file dialog to the new dialog. Blocking subprocess work (search, install) runs on a worker thread behind the modal progress dialog.

**Tech Stack:** Python 3.13, Traits / TraitsUI, PySide6 (Qt, views only), `pixi` CLI via `subprocess`, pyface `ProgressDialog`.

## Global Constraints

- **Channel URL:** `https://prefix.dev/microdrop-plugins` — define once as `PLUGIN_CHANNEL_URL` in `plugin_management/consts.py`; never inline the literal elsewhere.
- **Threading rule (project memory `mvc-separation-directive`):** the model is mutated **only on the GUI thread**. Worker-thread callables (`run_with_wait`'s `work`) must NOT set model traits — they return data; the GUI-thread `on_success` applies it. Violating this updates Qt from a non-GUI thread and can crash.
- **Logging:** `from logger.logger_service import get_logger; logger = get_logger(__name__)`. Never `logging.getLogger`.
- **No bare `except: pass`** — catch `Exception` (or narrower) and log (`logger.warning`, or `logger.debug` for tolerated paths).
- **f-strings only** for formatting/log messages (no `%`/`.format()`).
- **Constants** in `consts.py`, UPPER_SNAKE_CASE, one name per constant (no aliasing).
- **Imports at module top** — no in-function imports to dodge dependencies (no circular imports are introduced by the top-level imports specified here).
- **Dialogs** go through `microdrop_application.dialogs.pyface_wrapper` (`confirm`/`information`/`error`, `YES`); never raw Qt message boxes.
- **Themed table columns** come from `microdrop_utils.traitsui_qt_helpers.ObjectColumn` (text color follows the theme), never raw `traitsui` `ObjectColumn`.
- **Test runs:** the fast unit tests in this plan are pure-logic and headless — run them per task with `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests/<file>.py -q"`. Do NOT auto-run the full app / Qt / Redis suites; defer manual app verification (Task 5) to the user.

---

## File Structure

- `plugin_management/consts.py` — **modify**: add `PLUGIN_CHANNEL_URL`.
- `plugin_management/paths.py` — **modify**: add `plugin_index_file()`; remove `plugin_channel_dir()`.
- `plugin_management/package_installer.py` — **modify**: add `search_channel`, `read_cached_index`, `install_from_channel`, `_parse_search_json`; generalize `_ensure_channel_registered`; simplify `uninstall_package`; remove dead local-file code.
- `plugin_management/browse_model.py` — **create**: `AvailablePackage`, `BrowsePluginsModel`, plus pure formatters `format_details`, `_format_size`, `_format_timestamp`, `_version_key`.
- `plugin_management/browse_view.py` — **create**: TraitsUI `browse_view`.
- `plugin_management/browse_controller.py` — **create**: `BrowsePluginsHandler` + `_consent_html`.
- `plugin_management/relaunch.py` — **modify**: add shared `confirm_and_relaunch(task, msg_html)`.
- `plugin_management/manager_model.py` — **modify**: remove `preview`/`do_install` (old file path).
- `plugin_management/manager_controller.py` — **modify**: repoint `install_plugin` to the new dialog; route `_after_change` through `confirm_and_relaunch`; drop dead `_consent_html`/`file_dialog`.
- `plugin_management/tests/` — **create**: `test_package_installer.py`, `test_browse_format.py`, `test_browse_model.py`.

---

## Task 1: Data layer — constants, cache path, search + parse

**Files:**
- Modify: `plugin_management/consts.py`
- Modify: `plugin_management/paths.py`
- Modify: `plugin_management/package_installer.py`
- Test: `plugin_management/tests/test_package_installer.py`

**Interfaces:**
- Consumes: existing `package_installer._run(args, *, cwd=None)` (raises `InstallError` on non-zero exit; returns the `CompletedProcess` with `.stdout`).
- Produces:
  - `consts.PLUGIN_CHANNEL_URL: str`
  - `paths.plugin_index_file() -> Path`
  - `package_installer._parse_search_json(stdout: str) -> list[dict]`
  - `package_installer.search_channel(channel_url: str, *, cwd=None) -> list[dict]`
  - `package_installer.read_cached_index() -> list[dict]`

- [ ] **Step 1: Add the constant**

In `plugin_management/consts.py`, append:

```python
PLUGIN_CHANNEL_URL = "https://prefix.dev/microdrop-plugins"
```

- [ ] **Step 2: Add the cache-path helper and remove the dead one**

In `plugin_management/paths.py`, replace `plugin_channel_dir()` with:

```python
def plugin_index_file() -> Path:
    """App-data file caching the last fetched channel package list (JSON).
    Lives under ETSConfig.application_home; the dir is created if missing."""
    home = Path(ETSConfig.application_home)
    home.mkdir(parents=True, exist_ok=True)
    return home / "plugin_index.json"
```

(Keep the module docstring accurate: it now describes the index cache, not a channel dir.)

- [ ] **Step 3: Write the failing tests**

Create `plugin_management/tests/__init__.py` (empty) and `plugin_management/tests/test_package_installer.py`:

```python
"""Tests for the channel search/parse/cache data layer."""
import json

import pytest

from plugin_management import package_installer, paths


SAMPLE_STDOUT = """ WARN some deprecation warning on stderr-ish text
Using channels: https://prefix.dev/microdrop-plugins/
{
  "noarch": [
    {
      "name": "scipy_analysis",
      "version": "0.1.0",
      "build": "pyh4616a5c_0",
      "depends": ["scipy >=1.10", "python >=3.11"],
      "size": 5485,
      "timestamp": 1782507668846,
      "fn": "scipy_analysis-0.1.0-pyh4616a5c_0.conda",
      "url": "https://prefix.dev/microdrop-plugins/noarch/scipy_analysis-0.1.0-pyh4616a5c_0.conda"
    }
  ]
}
"""


def test_parse_search_json_flattens_subdirs():
    pkgs = package_installer._parse_search_json(SAMPLE_STDOUT)
    assert [p["name"] for p in pkgs] == ["scipy_analysis"]
    assert pkgs[0]["version"] == "0.1.0"


def test_parse_search_json_no_json_raises():
    with pytest.raises(package_installer.InstallError):
        package_installer._parse_search_json("no json here")


def test_search_channel_writes_cache(tmp_path, monkeypatch):
    cache = tmp_path / "plugin_index.json"
    monkeypatch.setattr(paths, "plugin_index_file", lambda: cache)

    class _Proc:
        stdout = SAMPLE_STDOUT
    monkeypatch.setattr(package_installer, "_run", lambda *a, **k: _Proc())

    result = package_installer.search_channel("https://prefix.dev/microdrop-plugins")
    assert result[0]["name"] == "scipy_analysis"
    assert json.loads(cache.read_text(encoding="utf-8"))[0]["name"] == "scipy_analysis"


def test_read_cached_index_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "plugin_index_file", lambda: tmp_path / "missing.json")
    assert package_installer.read_cached_index() == []
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests/test_package_installer.py -q"`
Expected: FAIL (`AttributeError: module ... has no attribute '_parse_search_json'`).

- [ ] **Step 5: Implement the data layer**

In `plugin_management/package_installer.py`, add near the top (after existing imports — `json` is already imported):

```python
from plugin_management import paths
from plugin_management.consts import PLUGIN_CHANNEL_URL
```

(`paths` is already imported in this module — keep one import.) Then add:

```python
def _parse_search_json(stdout: str) -> list:
    """Parse `pixi search --json` stdout (which may be preceded by warning
    lines) into a flat list of package dicts across all subdirs."""
    start = stdout.find("{")
    if start == -1:
        raise InstallError("no JSON object in pixi search output")
    try:
        data = json.loads(stdout[start:])
    except ValueError as e:
        raise InstallError(f"could not parse pixi search JSON: {e}") from e
    packages = []
    for subdir_packages in data.values():
        if isinstance(subdir_packages, list):
            packages.extend(subdir_packages)
    return packages


def search_channel(channel_url: str = PLUGIN_CHANNEL_URL, *, cwd=None) -> list:
    """Run `pixi search "*" -c <channel_url> --json`, parse + flatten the
    result, write it to the app-data cache, and return the package list.
    Raises InstallError on subprocess or parse failure."""
    proc = _run(["search", "*", "-c", channel_url, "--json"], cwd=cwd)
    packages = _parse_search_json(proc.stdout)
    paths.plugin_index_file().write_text(json.dumps(packages), encoding="utf-8")
    return packages


def read_cached_index() -> list:
    """Return the last cached channel package list, or [] if absent/unreadable."""
    fp = paths.plugin_index_file()
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(f"could not read cached plugin index: {e}")
        return []
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests/test_package_installer.py -q"`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add plugin_management/consts.py plugin_management/paths.py plugin_management/package_installer.py plugin_management/tests/__init__.py plugin_management/tests/test_package_installer.py
git commit -m "Add channel search + app-data cache data layer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Detail-block formatting + version key

**Files:**
- Create: `plugin_management/browse_model.py` (formatters only this task)
- Test: `plugin_management/tests/test_browse_format.py`

**Interfaces:**
- Produces (module-level, Qt-free):
  - `browse_model.format_details(raw: dict) -> str`
  - `browse_model._format_size(size) -> str`
  - `browse_model._format_timestamp(ms) -> str`
  - `browse_model._version_key(version: str) -> tuple`

- [ ] **Step 1: Write the failing tests**

Create `plugin_management/tests/test_browse_format.py`:

```python
"""Tests for the package detail-block formatting + version key."""
from plugin_management import browse_model

RAW = {
    "name": "scipy_analysis",
    "version": "0.1.0",
    "build": "pyh4616a5c_0",
    "size": 5485,
    "timestamp": 1782507668846,
    "subdir": "noarch",
    "noarch": "python",
    "fn": "scipy_analysis-0.1.0-pyh4616a5c_0.conda",
    "url": "https://prefix.dev/microdrop-plugins/noarch/scipy_analysis-0.1.0-pyh4616a5c_0.conda",
    "md5": "537115f431813e38d5599fe2df20b178",
    "sha256": "f4aa51f8f1d696e91c5d8155f3f75985b7d24d1eac8bbeef910884f04365e7c2",
    "depends": ["scipy >=1.10", "python >=3.11", "python *"],
}


def test_format_size():
    assert browse_model._format_size(5485) == "5.36 KiB"
    assert browse_model._format_size(None) == ""


def test_format_timestamp_utc():
    assert browse_model._format_timestamp(1782507668846) == "2026-06-26 21:01:08 UTC"
    assert browse_model._format_timestamp(None) == ""


def test_format_details_full():
    text = browse_model.format_details(RAW)
    assert "scipy_analysis-0.1.0-pyh4616a5c_0" in text   # header (fn w/o .conda)
    assert "scipy_analysis" in text
    assert "0.1.0" in text
    assert "5.36 KiB" in text
    assert "2026-06-26 21:01:08 UTC" in text
    assert "Dependencies:" in text
    assert " - scipy >=1.10" in text
    assert "f4aa51f8f1d696e91c5d8155f3f75985b7d24d1eac8bbeef910884f04365e7c2" in text


def test_format_details_missing_fields_no_crash():
    text = browse_model.format_details({"name": "x"})
    assert "x" in text  # does not raise; blank size/timestamp


def test_version_key_orders():
    assert browse_model._version_key("0.2.0") > browse_model._version_key("0.1.0")
    assert browse_model._version_key("1.0") > browse_model._version_key("0.9.9")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests/test_browse_format.py -q"`
Expected: FAIL (`ModuleNotFoundError: No module named 'plugin_management.browse_model'`).

- [ ] **Step 3: Create `browse_model.py` with the formatters**

Create `plugin_management/browse_model.py`:

```python
"""Qt-free model for the Browse Plugins window.

Lists the packages available in the remote plugin channel (one row per
package), formats a package's full metadata for the details panel, and
delegates fetch/install to ``package_installer``. No Qt, no dialogs, no
threading — the controller (a Handler) owns those.
"""
import re
from datetime import datetime, timezone

from traits.api import Dict, HasTraits, Instance, List, Str, Bool

from plugin_management import package_installer
from plugin_management.consts import PLUGIN_CHANNEL_URL
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _format_size(size) -> str:
    """Bytes -> binary KiB string (matching pixi), or '' if unknown."""
    if size is None:
        return ""
    return f"{size / 1024:.2f} KiB"


def _format_timestamp(ms) -> str:
    """Milliseconds since epoch -> 'YYYY-MM-DD HH:MM:SS UTC', or '' if unknown."""
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC")


def _version_key(version: str) -> tuple:
    """Sort key for version strings: tuple of leading integers per dotted part."""
    parts = []
    for part in str(version).split("."):
        m = re.match(r"\d+", part)
        parts.append(int(m.group()) if m else 0)
    return tuple(parts)


def format_details(raw: dict) -> str:
    """Render a package's full metadata as the plain-text details block."""
    fn = raw.get("fn", "") or ""
    header = fn[:-len(".conda")] if fn.endswith(".conda") else raw.get("name", "")
    rows = [
        ("Name", raw.get("name", "")),
        ("Version", str(raw.get("version", ""))),
        ("Build", raw.get("build", "")),
        ("Size", _format_size(raw.get("size"))),
        ("Timestamp", _format_timestamp(raw.get("timestamp"))),
        ("Subdir", raw.get("subdir", "")),
        ("NoArch", raw.get("noarch", "") or ""),
        ("File Name", fn),
        ("URL", raw.get("url", "")),
        ("MD5", raw.get("md5", "")),
        ("SHA256", raw.get("sha256", "")),
    ]
    lines = [header, "-" * max(len(header), 33), ""]
    lines += [f"{label:<19} {value}" for label, value in rows]
    depends = raw.get("depends") or []
    if depends:
        lines += ["", "Dependencies:"] + [f" - {d}" for d in depends]
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests/test_browse_format.py -q"`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add plugin_management/browse_model.py plugin_management/tests/test_browse_format.py
git commit -m "Add package detail-block formatting + version key

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Remote install + dead-code removal in package_installer

**Files:**
- Modify: `plugin_management/package_installer.py`
- Test: `plugin_management/tests/test_package_installer.py`

**Interfaces:**
- Consumes: `_run`, `_snapshot`, `_restore`, `InstallError`, `InstallResult` (existing).
- Produces:
  - `package_installer._ensure_channel_registered(channel_url: str, cwd) -> None` (now takes a URL string)
  - `package_installer.install_from_channel(name: str, channel_url: str = PLUGIN_CHANNEL_URL, *, cwd=None) -> InstallResult`
  - `package_installer.uninstall_package(name: str, *, cwd=None) -> None` (simplified)

- [ ] **Step 1: Write the failing tests**

Append to `plugin_management/tests/test_package_installer.py`:

```python
def test_ensure_channel_registered_passes_url(monkeypatch):
    calls = []
    monkeypatch.setattr(package_installer, "_run",
                        lambda args, cwd=None: calls.append((list(args), cwd)))
    package_installer._ensure_channel_registered("https://prefix.dev/microdrop-plugins", cwd=None)
    assert calls[0][0] == ["workspace", "channel", "add",
                           "https://prefix.dev/microdrop-plugins"]


def test_install_from_channel_adds_and_returns(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")
    (tmp_path / "pixi.lock").write_text("lock", encoding="utf-8")
    calls = []
    monkeypatch.setattr(package_installer, "_run",
                        lambda args, cwd=None: calls.append(list(args)))
    result = package_installer.install_from_channel(
        "scipy_analysis", "https://prefix.dev/microdrop-plugins", cwd=tmp_path)
    assert ["add", "scipy_analysis"] in calls
    assert result.name == "scipy_analysis"
    assert result.requires_relaunch is True


def test_install_from_channel_rolls_back(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")
    (tmp_path / "pixi.lock").write_text("lock", encoding="utf-8")

    def fake_run(args, cwd=None):
        if args[:1] == ["add"]:
            raise package_installer.InstallError("boom")
    monkeypatch.setattr(package_installer, "_run", fake_run)
    with pytest.raises(package_installer.InstallError):
        package_installer.install_from_channel("x", "https://c", cwd=tmp_path)
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == "orig"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests/test_package_installer.py -q -k 'channel or roll'"`
Expected: FAIL (`install_from_channel` not defined; `_ensure_channel_registered` signature mismatch).

- [ ] **Step 3: Generalize `_ensure_channel_registered` and add `install_from_channel`**

In `plugin_management/package_installer.py`, replace `_ensure_channel_registered` with the URL-taking form:

```python
def _ensure_channel_registered(channel_url, cwd):
    """`pixi workspace channel add <url>`; tolerate an already-registered channel."""
    try:
        _run(["workspace", "channel", "add", channel_url], cwd=cwd)
    except InstallError as e:
        if "already" not in str(e).lower():
            raise
```

Add:

```python
def install_from_channel(name, channel_url=PLUGIN_CHANNEL_URL, *, cwd=None) -> InstallResult:
    """Register the channel and `pixi add <name>` so the solver resolves the
    package + its deps. Snapshot/restore pyproject + lock on any failure.
    Returns InstallResult(name, requires_relaunch=True)."""
    cwd = Path(cwd or WORKSPACE_DIR)
    snapshot = _snapshot(cwd)
    try:
        _ensure_channel_registered(channel_url, cwd)
        _run(["add", name], cwd=cwd)
    except Exception:
        _restore(cwd, snapshot)
        raise
    logger.info(f"installed plugin '{name}' from {channel_url}")
    return InstallResult(name=name, requires_relaunch=True)
```

- [ ] **Step 4: Remove the dead local-file code**

In `plugin_management/package_installer.py`, delete:
- `package_name_from_conda`, `read_conda_preview`, `install_conda_file`, `_conda_manifest`, `_zst_tar`, `_index_channel`, `_index_channel_safe`.
- The `PluginPreview` and `InstallCancelled` classes (now unused).
- Imports only those used: drop `io`, `shutil`, `tarfile`, `zipfile`, `backports.zstd as zstd`. Keep `json`, `subprocess`, `dataclass`, `Path`, `paths`, `PLUGIN_CHANNEL_URL`, `logger`, `WORKSPACE_DIR`, `InstallError`, `InstallResult`, `_run`, `_snapshot`, `_restore`, `_ensure_channel_registered`.

Replace `uninstall_package` with the simplified form (no local-channel cleanup):

```python
def uninstall_package(name, *, cwd=None) -> None:
    """`pixi remove <name>`. Best-effort; logs on failure."""
    cwd = Path(cwd or WORKSPACE_DIR)
    try:
        _run(["remove", name], cwd=cwd)
    except InstallError as e:
        logger.warning(f"`pixi remove {name}` failed: {e}")
```

- [ ] **Step 5: Run the full data-layer test file to verify it passes**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests/test_package_installer.py -q"`
Expected: PASS (7 passed). Also confirm the module imports cleanly:
`cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'import plugin_management.package_installer'"`
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```bash
git add plugin_management/package_installer.py plugin_management/tests/test_package_installer.py
git commit -m "Add remote-channel install; remove dead local-.conda code

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Browse model (fetch with cache fallback, install delegate)

**Files:**
- Modify: `plugin_management/browse_model.py`
- Test: `plugin_management/tests/test_browse_model.py`

**Interfaces:**
- Consumes: `package_installer.search_channel`, `read_cached_index`, `install_from_channel`; `format_details`, `_version_key` (Task 2).
- Produces:
  - `browse_model.AvailablePackage` with traits `name: Str`, `version: Str`, `raw: Dict`.
  - `browse_model.BrowsePluginsModel` with traits `channel_url: Str`, `packages: List(AvailablePackage)`, `selected: Instance(AvailablePackage)`, `details_text: Str`, `stale: Bool`.
  - Methods: `fetch_data() -> tuple[list, bool]` (**worker-safe; no trait mutation**), `set_packages(data, stale) -> None` (**GUI thread; mutates traits**), `do_install(name) -> InstallResult` (worker-safe).

- [ ] **Step 1: Write the failing tests**

Create `plugin_management/tests/test_browse_model.py`:

```python
"""Tests for BrowsePluginsModel fetch/fallback and row building."""
from plugin_management import browse_model, package_installer


def test_fetch_data_success(monkeypatch):
    pkgs = [{"name": "a", "version": "1.0"}]
    monkeypatch.setattr(package_installer, "search_channel", lambda url: pkgs)
    model = browse_model.BrowsePluginsModel()
    data, stale = model.fetch_data()
    assert data == pkgs
    assert stale is False


def test_fetch_data_falls_back_to_cache(monkeypatch):
    def boom(url):
        raise package_installer.InstallError("offline")
    monkeypatch.setattr(package_installer, "search_channel", boom)
    monkeypatch.setattr(package_installer, "read_cached_index",
                        lambda: [{"name": "a", "version": "1.0"}])
    model = browse_model.BrowsePluginsModel()
    data, stale = model.fetch_data()
    assert data[0]["name"] == "a"
    assert stale is True


def test_set_packages_dedupes_to_latest():
    model = browse_model.BrowsePluginsModel()
    model.set_packages(
        [{"name": "a", "version": "0.1.0"}, {"name": "a", "version": "0.2.0"}],
        False)
    assert len(model.packages) == 1
    assert model.packages[0].version == "0.2.0"
    assert model.stale is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests/test_browse_model.py -q"`
Expected: FAIL (`AttributeError: module ... has no attribute 'BrowsePluginsModel'`).

- [ ] **Step 3: Add the model classes to `browse_model.py`**

Append to `plugin_management/browse_model.py`:

```python
class AvailablePackage(HasTraits):
    """One package available in the channel: name/version + its full metadata."""
    name = Str()
    version = Str()
    raw = Dict()


class BrowsePluginsModel(HasTraits):
    """The packages available in the remote channel + fetch/install operations."""

    channel_url = Str(PLUGIN_CHANNEL_URL)
    packages = List(Instance(AvailablePackage))
    selected = Instance(AvailablePackage)
    details_text = Str()
    stale = Bool(False)

    def fetch_data(self):
        """Worker-thread safe: return (packages, stale). Does NOT touch traits.
        Tries the channel; on failure falls back to the app-data cache."""
        try:
            return package_installer.search_channel(self.channel_url), False
        except package_installer.InstallError as e:
            logger.warning(f"channel search failed, using cached list: {e}")
            return package_installer.read_cached_index(), True

    def set_packages(self, data, stale):
        """GUI thread: build one row per package (latest version) + flags."""
        self.stale = stale
        self.packages = self._rows_from(data)

    def _rows_from(self, data):
        latest = {}
        for pkg in data:
            name = pkg.get("name")
            if not name:
                continue
            current = latest.get(name)
            if current is None or _version_key(pkg.get("version", "")) >= _version_key(
                    current.get("version", "")):
                latest[name] = pkg
        return [AvailablePackage(name=p["name"], version=str(p.get("version", "")),
                                 raw=p)
                for p in sorted(latest.values(), key=lambda p: p["name"])]

    def do_install(self, name):
        """Worker-thread safe: install via package_installer (no trait mutation)."""
        return package_installer.install_from_channel(name, self.channel_url)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests/test_browse_model.py -q"`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add plugin_management/browse_model.py plugin_management/tests/test_browse_model.py
git commit -m "Add BrowsePluginsModel with cache-fallback fetch

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Browse view + controller, shared relaunch, wire into Manage Plugins

**Files:**
- Create: `plugin_management/browse_view.py`
- Create: `plugin_management/browse_controller.py`
- Modify: `plugin_management/relaunch.py`
- Modify: `plugin_management/manager_model.py`
- Modify: `plugin_management/manager_controller.py`

**Interfaces:**
- Consumes: `BrowsePluginsModel`, `format_details` (Tasks 2/4); `SafeCancelTableHandler`, `ObjectColumn` (`microdrop_utils.traitsui_qt_helpers`); `run_with_wait` (`microdrop_utils.threaded_progress`); `confirm`/`information`/`error`/`YES`/`escape_html_multiline` (`pyface_wrapper`); `relaunch_app` (existing).
- Produces:
  - `browse_view.browse_view: View`
  - `browse_controller.BrowsePluginsHandler` (actions: `show_details`, `install_selected`, `do_close`)
  - `relaunch.confirm_and_relaunch(task, msg_html) -> None`

This task is UI + wiring — verified manually (no unit test). It ends with the full flow working from the menu.

- [ ] **Step 1: Add the shared relaunch helper**

In `plugin_management/relaunch.py`, add at module top:

```python
from microdrop_application.dialogs.pyface_wrapper import confirm, information, YES
```

and add the function:

```python
def confirm_and_relaunch(task, msg_html):
    """Offer to relaunch now (applies the change) or later. Shared by the
    Manage-Plugins and Browse-Plugins controllers."""
    if confirm(parent=None, title="Relaunch required",
               message=f"{msg_html}<br><br>Relaunch MicroDrop now to apply?",
               cancel=False) == YES:
        relaunch_app(task.window.application)
    else:
        information(parent=None, title="Relaunch later",
                    message="The change takes effect the next time you launch "
                            "MicroDrop.")
```

- [ ] **Step 2: Create the view**

Create `plugin_management/browse_view.py`:

```python
"""TraitsUI layout for the Browse Plugins window: a table of channel packages
(name/version) + a read-only details panel + action buttons. Pure presentation —
the controller (a Handler) handles the buttons; the model supplies ``packages``.
"""
from traitsui.api import Action, Item, TableEditor, View, VGroup, TextEditor

from microdrop_utils.traitsui_qt_helpers import ObjectColumn

details_action = Action(name="More details", action="show_details")
install_action = Action(name="Install", action="install_selected")
close_action = Action(name="Close", action="do_close")

_packages_table = TableEditor(
    columns=[
        ObjectColumn(name="name", label="Name", editable=False),
        ObjectColumn(name="version", label="Version", editable=False),
    ],
    selected="selected",
    selection_mode="row",
    editable=False,
    sortable=False,
)

browse_view = View(
    VGroup(
        Item("packages", show_label=False, editor=_packages_table),
        Item("details_text", show_label=False, style="custom",
             editor=TextEditor(read_only=True)),
    ),
    buttons=[details_action, install_action, close_action],
    title="Browse Plugins",
    kind="livemodal",
    resizable=True,
    width=620,
    height=480,
)
```

- [ ] **Step 3: Create the controller**

Create `plugin_management/browse_controller.py`:

```python
"""Handler for the Browse Plugins window: fetch the channel list on open,
show a selected package's details, and install the selected package. The model
holds state/logic; this holds the flow (dialogs, worker-thread progress).

Worker callables (fetch_data / do_install) must not touch model traits — they
return data and the GUI-thread callbacks apply it (model is mutated on the GUI
thread only)."""
from traits.api import Instance
from pyface.tasks.api import Task

from microdrop_application.dialogs.pyface_wrapper import (
    confirm, information, error as error_dialog, YES, escape_html_multiline)
from microdrop_utils.threaded_progress import run_with_wait
from microdrop_utils.traitsui_qt_helpers import SafeCancelTableHandler

from plugin_management.browse_model import format_details
from plugin_management.relaunch import confirm_and_relaunch
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _consent_html(pkg):
    name = escape_html_multiline(pkg.name)
    deps = ", ".join(escape_html_multiline(d) for d in pkg.raw.get("depends", [])) or "none"
    return (f"<b>{name}</b> (v{escape_html_multiline(pkg.version)})<br><br>"
            f"Dependencies pixi will install: {deps}<br><br>"
            f"<b>Warning:</b> installing runs third-party code that has not been "
            f"verified. Only install plugins you trust.<br><br>Install this plugin?")


class BrowsePluginsHandler(SafeCancelTableHandler):
    """Fetches the channel list and installs the selected package."""

    task = Instance(Task)

    def init(self, info):
        super().init(info)            # Escape deselects instead of closing
        model = info.object
        run_with_wait(
            model.fetch_data,
            title="Loading plugins", message="Fetching available plugins…",
            on_success=lambda result: self._after_fetch(model, result),
            on_error=lambda e: error_dialog(
                parent=None, title="Could not load plugins", message=str(e)))
        return True

    def _after_fetch(self, model, result):
        data, stale = result
        model.set_packages(data, stale)        # GUI thread
        if stale:
            information(parent=None, title="Offline",
                        message="Could not reach the plugin channel — showing the "
                                "last cached list.")

    def show_details(self, info):
        model = info.object
        if model.selected is None:
            information(parent=None, title="No selection",
                        message="Select a plugin first.")
            return
        model.details_text = format_details(model.selected.raw)

    def install_selected(self, info):
        model = info.object
        pkg = model.selected
        if pkg is None:
            information(parent=None, title="No selection",
                        message="Select a plugin to install.")
            return
        if confirm(parent=None, title="Install Plugin?",
                   message=_consent_html(pkg), cancel=False) != YES:
            return
        run_with_wait(
            lambda: model.do_install(pkg.name),
            title="Installing plugin", message=f"Installing {pkg.name}…",
            on_success=lambda r: confirm_and_relaunch(
                self.task, f"Installed <b>{escape_html_multiline(pkg.name)}</b>."),
            on_error=lambda e: error_dialog(
                parent=None, title="Install failed", message=str(e)))

    def do_close(self, info):
        info.ui.dispose()
```

- [ ] **Step 4: Repoint `install_plugin` and drop dead code in `manager_controller.py`**

In `plugin_management/manager_controller.py`:

Add to the top-level imports:

```python
from plugin_management.browse_model import BrowsePluginsModel
from plugin_management.browse_view import browse_view
from plugin_management.browse_controller import BrowsePluginsHandler
from plugin_management.relaunch import confirm_and_relaunch
```

Remove `file_dialog` from the `pyface_wrapper` import (it's no longer used). Replace the whole `install_plugin` method body with:

```python
    # --- Install: open the Browse Plugins dialog (lists the remote channel) ---
    def install_plugin(self, info):
        model = BrowsePluginsModel()
        model.edit_traits(view=browse_view,
                          handler=BrowsePluginsHandler(task=self.task),
                          kind="livemodal")
```

Replace `_after_change` to use the shared helper:

```python
    def _after_change(self, msg_html):
        confirm_and_relaunch(self.task, msg_html)
```

Delete the now-unused `_consent_html` method (the browse controller has its own).

- [ ] **Step 5: Remove the old install delegates from `manager_model.py`**

In `plugin_management/manager_model.py`, delete the `preview` and `do_install` methods (the local-file path) and the `from plugin_management import package_installer` import if it is now only used by `do_uninstall` — keep the import, since `do_uninstall` still calls `package_installer.uninstall_package`. (Net: remove only `preview` and `do_install`.)

- [ ] **Step 6: Verify imports + smoke-load headless**

Run:
`cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && QT_QPA_PLATFORM=offscreen python -c 'import plugin_management.browse_controller, plugin_management.browse_view, plugin_management.manager_controller, plugin_management.menus; print(\"ok\")'"`
Expected: prints `ok`, exit 0 (no ImportError, no circular-import error).

Re-run the whole test dir to confirm nothing regressed:
`cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest plugin_management/tests -q"`
Expected: PASS (all tests).

- [ ] **Step 7: Manual verification (user)**

Launch the app (`python examples/run_device_viewer_pluggable.py`), then:
1. Tools → Manage Plugins… → **Install Plugin…** → the Browse Plugins window opens and (after the modal "Fetching…" progress) lists `scipy_analysis 0.1.0`.
2. Select the row → **More details** → the panel shows the full block (Build, Size `5.36 KiB`, Timestamp, URL, MD5, SHA256, Dependencies).
3. **Install** → consent dialog → Yes → modal "Installing…" → relaunch prompt.
4. Disconnect network (or temporarily set a bad `channel_url`) → reopen → "Offline — showing the last cached list" and the table still populates from the app-data cache.

- [ ] **Step 8: Commit**

```bash
git add plugin_management/browse_view.py plugin_management/browse_controller.py plugin_management/relaunch.py plugin_management/manager_model.py plugin_management/manager_controller.py
git commit -m "Browse Plugins dialog: install from the remote channel

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Channel + `pixi search --json` listing → Task 1 (`search_channel`). ✓
- Table of name/version → Task 5 (`browse_view`). ✓
- More details button → full info panel → Task 2 (`format_details`) + Task 5 (`show_details`). ✓
- Store in app-data, read from file → Task 1 (`search_channel` writes cache; `read_cached_index`) + Task 4 (`fetch_data`). ✓
- Install selected via `pixi add` → Task 3 (`install_from_channel`) + Task 5 (`install_selected`). ✓
- Keep consent prompt → Task 5 (`_consent_html` + confirm). ✓
- Fetch fresh with cache fallback / offline note → Task 4 (`fetch_data` stale) + Task 5 (`_after_fetch`). ✓
- Dead-code removal + `uninstall` simplification → Task 3. ✓
- New modal dialog opened from Install Plugin… → Task 5 (`manager_controller.install_plugin`). ✓
- Threading rule (model mutated on GUI thread) → Task 4 split `fetch_data`/`set_packages`; Task 5 applies in `on_success`. ✓

**Placeholder scan:** none — every code/test step shows full content.

**Type consistency:** `search_channel`/`read_cached_index` return `list[dict]`; `fetch_data` returns `(list, bool)` consumed by `_after_fetch` as `(data, stale)` → `set_packages(data, stale)`; `format_details(raw: dict)` fed `AvailablePackage.raw` (a `Dict`); `install_from_channel(name, channel_url)` returns `InstallResult(name, requires_relaunch)`; `confirm_and_relaunch(task, msg_html)` used identically by both controllers. Consistent.
