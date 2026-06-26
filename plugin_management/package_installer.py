"""Install/uninstall a plugin distributed as a built conda package (.conda).

The .conda is copied into a local conda channel under app-data, the channel is
indexed + registered with the workspace, and ``pixi add <name>`` installs the
package — letting the conda solver resolve the plugin's run-dependencies. No
custom dependency wiring. Qt-free; snapshots pyproject.toml + pixi.lock for
rollback.
"""
import io
import json
import shutil
import subprocess
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import backports.zstd as zstd

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
        with zipfile.ZipFile(p) as z:
            info_member = next(n for n in z.namelist() if n.startswith("info-") and n.endswith(".tar.zst"))
            decompressed = zstd.decompress(z.read(info_member))
            with tarfile.open(fileobj=io.BytesIO(decompressed)) as tar:
                idx = json.loads(tar.extractfile("info/index.json").read().decode("utf-8"))
                return idx["name"]
    except Exception as e:
        raise InstallError(f"could not read package name from {p.name}: {e}") from e


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
    _run(["exec", "rattler-index", "fs", str(channel_dir)])


def _ensure_channel_registered(channel_dir, cwd):
    url = Path(channel_dir).as_uri()
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
        shutil.copy2(src, dest)
        copied = True
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
