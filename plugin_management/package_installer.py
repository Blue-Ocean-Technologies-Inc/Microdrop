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


def _ensure_channel_registered(channel_url, cwd):
    """`pixi workspace channel add <url>`; tolerate an already-registered channel."""
    try:
        _run(["workspace", "channel", "add", channel_url], cwd=cwd)
    except InstallError as e:
        if "already" not in str(e).lower():
            raise


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


def uninstall_package(name, *, cwd=None) -> None:
    """`pixi remove <name>`. Best-effort; logs on failure."""
    cwd = Path(cwd or WORKSPACE_DIR)
    try:
        _run(["remove", name], cwd=cwd)
    except InstallError as e:
        logger.warning(f"`pixi remove {name}` failed: {e}")
