"""Install/uninstall plugins from the hosted conda channel.

Uses `pixi add <name>` (channel registered on demand) so the conda solver
resolves the package + its run-dependencies. Qt-free; snapshots pyproject.toml
+ pixi.lock for rollback.
"""
import importlib.metadata
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from plugin_management import paths
from plugin_management.consts import ENTRY_POINT_GROUP, PLUGIN_CHANNEL_URL
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: pixi workspace root (microdrop-py/, parent of src/).
WORKSPACE_DIR = Path(__file__).resolve().parents[2]


class InstallError(Exception):
    """A pixi command failed or a channel package could not be installed."""


@dataclass
class EnvChangeResult:
    """The outcome of an env-mutating pixi command.

    ``diff`` is None when the environment could not be snapshotted; callers
    must treat that as 'unknown' and relaunch."""

    name: str
    diff: "EnvDiff | None"
    requires_relaunch: bool


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


def _run(args, *, cwd=None):
    proc = subprocess.run(["pixi", *args], cwd=str(cwd or WORKSPACE_DIR),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise InstallError(
            f"`pixi {' '.join(args)}` failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}")
    return proc


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


#: (channel_url, workspace dir) pairs this process has already registered —
#: `pixi workspace channel add` is idempotent but costs a subprocess, and the
#: channel URL is a fixed constant, so paying it once per run is enough.
_registered_channels = set()


def _ensure_channel_registered(channel_url, cwd):
    """`pixi workspace channel add <url>`; tolerate an already-registered
    channel, and skip the subprocess entirely once this process has
    registered the pair."""
    key = (channel_url, str(cwd or WORKSPACE_DIR))
    if key in _registered_channels:
        return
    try:
        _run(["workspace", "channel", "add", channel_url], cwd=cwd)
    except InstallError as e:
        if "already" not in str(e).lower():
            raise
    _registered_channels.add(key)


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


def upgrade_package(name, channel_url=PLUGIN_CHANNEL_URL, *, cwd=None) -> EnvChangeResult:
    """Upgrade a plugin to the latest channel version — an unpinned
    `pixi add <name>` that re-resolves to the newest compatible build. Thin
    wrapper over :func:`install_from_channel`."""
    return install_from_channel(name, channel_url, cwd=cwd)


def _parse_search_json(stdout: str) -> list[dict]:
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


def search_channel(channel_url: str = PLUGIN_CHANNEL_URL, *, cwd=None) -> list[dict]:
    """Run `pixi search "*" -c <channel_url> --json`, parse + flatten the
    result, write it to the app-data cache, and return the package list.
    Raises InstallError on subprocess or parse failure."""
    proc = _run(["search", "*", "-c", channel_url, "--json"], cwd=cwd)
    packages = _parse_search_json(proc.stdout)
    paths.plugin_index_file().write_text(json.dumps(packages), encoding="utf-8")
    return packages


def read_cached_index() -> list[dict]:
    """Return the last cached channel package list, or [] if absent/unreadable."""
    fp = paths.plugin_index_file()
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(f"could not read cached plugin index: {e}")
        return []


def installed_plugin_dists() -> dict[str, str]:
    """{distribution name: version} for every installed distribution that
    exposes a ``microdrop.plugins`` entry point — i.e. every installed
    MicroDrop plugin package. Dist names match channel package names
    (e.g. heater-microdrop-plugin)."""
    dists = {}
    for dist in importlib.metadata.distributions():
        if not any(ep.group == ENTRY_POINT_GROUP for ep in dist.entry_points):
            continue
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            dists[name] = dist.version
    return dists


#: Project-URL labels we surface as a plugin's "Documentation" link, in
#: preference order: a dedicated docs site if the package declares one, else
#: its homepage (repo landing page). Matched case-insensitively against the
#: labels in the installed distribution's core metadata (PEP 621
#: `[project.urls]` -> `Project-URL: <label>, <url>`).
DOCUMENTATION_URL_LABELS = ("documentation", "homepage")


def documentation_url(dist_name) -> str:
    """The best documentation link for an installed distribution, or "" if it
    declares none. Reads the standard `Project-URL` metadata (populated from
    `[project.urls]`), preferring a Documentation URL and falling back to the
    Homepage — so no MicroDrop-specific manifest field is needed and the same
    data serves PyPI, IDEs, and other package managers."""
    try:
        metadata = importlib.metadata.metadata(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return ""
    urls = {}
    for entry in metadata.get_all("Project-URL") or ():
        label, _, url = entry.partition(",")
        urls[label.strip().lower()] = url.strip()
    for label in DOCUMENTATION_URL_LABELS:
        if urls.get(label):
            return urls[label]
    # Legacy core-metadata field, emitted by older tools for Homepage.
    return (metadata.get("Home-page") or "").strip()


def uninstall_package(name, *, cwd=None) -> EnvChangeResult:
    """`pixi remove <name>` + `pixi install`. Raises InstallError on failure —
    swallowing it made a failed removal indistinguishable from a successful
    one that merely needs a relaunch, so the UI reported "Uninstalled X."
    for a package still on disk. InstallError names the failing pixi command,
    and the controllers' on_error path surfaces it in an error dialog."""
    cwd = Path(cwd or WORKSPACE_DIR)
    before = _try_snapshot(cwd)
    _run(["remove", name], cwd=cwd)
    _run(["install"], cwd=cwd)
    diff = _diff_or_none(before, _try_snapshot(cwd))
    return EnvChangeResult(
        name=name, diff=diff,
        requires_relaunch=diff is None or not diff.is_pure_removal)
