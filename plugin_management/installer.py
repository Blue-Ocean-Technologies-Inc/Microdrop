"""Install a .microdrop_plugin archive (a zip) into the app-data
installed_plugins dir and register its groups with the live PluginGroupManager.

Security hardening (no signing): the archive uses the .microdrop_plugin
extension (enforced by the file dialog), every entry is validated against
zip-slip and an allowlist of the manifest's declared packages BEFORE anything
is extracted, and an injected ``confirm`` callback gates the install on
informed user consent.
"""

import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from plugin_management import paths, pixi_env
from plugin_management.manifest import load_manifest, ManifestError
from plugin_management.plugin_deps import read_plugin_dependencies, unsatisfied
from logger.logger_service import get_logger

logger = get_logger(__name__)

_S_IFLNK = 0xA000     # unix symlink mode bits, stored in zip external_attr


class InstallError(Exception):
    """The archive is malformed, unsafe, or could not be installed."""


class InstallCancelled(Exception):
    """The user declined the install at the consent prompt."""


@dataclass
class InstallResult:
    manifest: object              # PluginManifest
    requires_relaunch: bool       # True if deps were added that need a relaunch


def _purge_package_modules(packages):
    """Drop already-imported modules for the given top-level packages from
    sys.modules, so a reinstall's freshly-extracted source is imported on the
    next enable rather than a cached older copy (e.g. a plugin enabled then
    disabled earlier this session)."""
    for pkg in packages:
        for name in [m for m in sys.modules
                     if m == pkg or m.startswith(pkg + ".")]:
            del sys.modules[name]


def _read_manifest_from_zip(zf):
    try:
        raw = zf.read(paths.MANIFEST_FILENAME)
    except KeyError:
        raise InstallError(f"archive has no {paths.MANIFEST_FILENAME} at its root")
    try:
        return load_manifest(raw)
    except ManifestError as e:
        raise InstallError(str(e)) from e


def _validate_entries(zf, manifest):
    """Return the safe member names to extract. Rejects zip-slip (absolute /
    '..' / symlink) and any entry whose top-level component isn't the manifest
    or a declared package."""
    allowed_tops = set(manifest.packages) | {paths.MANIFEST_FILENAME, "pyproject.toml"}
    members = []
    for info in zf.infolist():
        name = info.filename
        pure = PurePosixPath(name)
        # Zip-slip checks apply to EVERY entry (including directory entries),
        # so a crafted '../' or absolute entry is rejected loudly, not skipped.
        if pure.is_absolute() or ".." in pure.parts:
            raise InstallError(f"unsafe path in archive: {name!r}")
        if name.endswith("/"):
            continue                                  # dir entry; created implicitly
        if ((info.external_attr >> 16) & 0xF000) == _S_IFLNK:
            raise InstallError(f"symlink entries are not allowed: {name!r}")
        top = pure.parts[0] if pure.parts else ""
        if top not in allowed_tops:
            raise InstallError(
                f"archive entry {name!r} is outside the declared packages "
                f"{sorted(manifest.packages)}"
            )
        members.append(name)
    return members


def install_from_zip(zip_path, manager, *, confirm=None, dest_root=None):
    """Validate, consent-gate, extract, and register a .microdrop_plugin archive.

    ``confirm(manifest) -> bool`` is the informed-consent callback (the action
    passes a dialog). ``dest_root`` overrides the install dir (tests). Returns
    an InstallResult (manifest + requires_relaunch). Nothing is extracted unless
    the manifest + all entries validate and consent is given. Raises InstallError /
    InstallCancelled."""
    zip_path = Path(zip_path)
    if not zipfile.is_zipfile(zip_path):
        raise InstallError(f"{zip_path.name} is not a valid archive")

    with zipfile.ZipFile(zip_path) as zf:
        manifest = _read_manifest_from_zip(zf)
        members = _validate_entries(zf, manifest)

        if confirm is not None and not confirm(manifest):
            raise InstallCancelled(f"install of '{manifest.name}' declined")

        # Refuse to clobber a currently-enabled install.
        for spec in manifest.groups:
            if manager.is_loaded(spec.name):
                raise InstallError(
                    f"group '{spec.name}' is enabled; disable it before reinstalling"
                )

        root = Path(dest_root) if dest_root is not None else paths.installed_plugins_dir()
        root.mkdir(parents=True, exist_ok=True)
        target = root / manifest.name
        # Extract to a staging dir first so a mid-extract failure can't destroy a
        # previously-installed copy; only swap it in once extraction succeeds.
        staging = Path(tempfile.mkdtemp(dir=root, prefix=f".{manifest.name}.tmp-"))
        backup = None
        try:
            zf.extractall(staging, members=members)
            # Rename any prior install aside (not rmtree) so a failed swap can
            # restore it — on Windows replace() can fail on a locked file, and
            # rmtree-then-replace would otherwise leave no install at all.
            if target.exists():
                backup = target.with_name(f".{manifest.name}.bak-{os.getpid()}")
                if backup.exists():
                    shutil.rmtree(backup)
                target.replace(backup)
            staging.replace(target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            if backup is not None and not target.exists():
                backup.replace(target)          # restore the prior install
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)

    _purge_package_modules(manifest.packages)
    paths.ensure_on_sys_path()
    manager.register_manifest(manifest, dist_name="")  # installer.py is removed in the conda-package migration teardown
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


def uninstall_plugin(task, manager, manifest_name):
    """Remove a user-installed plugin: auto-disable any of its loaded groups,
    purge its modules, deregister its groups (clearing their enabled flags),
    and delete its installed_plugins/<name>/ directory.

    Raises InstallError if ``manifest_name`` isn't a user-installed plugin
    (bundled or unknown)."""
    info = manager.installed_plugin(manifest_name)
    if info is None:
        raise InstallError(f"'{manifest_name}' is not an installed plugin")
    _name, _label, source_dir, group_names = info

    # Read the declared packages (for the sys.modules purge) before removal.
    try:
        manifest = load_manifest(Path(source_dir) / paths.MANIFEST_FILENAME)
        packages = manifest.packages
    except Exception:
        packages = []

    # Auto-disable any loaded group (full hot-unload) before deleting files.
    for group_name in group_names:
        if manager.is_loaded(group_name):
            manager.disable(task, group_name)

    # Purge first so module/.pyd handles are released before rmtree (Windows).
    _purge_package_modules(packages)
    manager.deregister_plugin(manifest_name)

    # Drop the plugin's pixi feature from the microdrop-plugins env (best-effort).
    try:
        pixi_env.remove_plugin_dependencies(manifest_name)
    except Exception:
        logger.exception(f"uninstall: pixi cleanup for '{manifest_name}' failed")

    source = Path(source_dir)
    if source.exists():
        shutil.rmtree(source)
    logger.info(f"uninstalled plugin '{manifest_name}' from {source_dir}")
