"""Install a .microdrop_plugin archive (a zip) into the app-data
installed_plugins dir and register its groups with the live PluginGroupManager.

Security hardening (no signing): the archive uses the .microdrop_plugin
extension (enforced by the file dialog), every entry is validated against
zip-slip and an allowlist of the manifest's declared packages BEFORE anything
is extracted, and an injected ``confirm`` callback gates the install on
informed user consent.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from microdrop_application.plugins import paths
from microdrop_application.plugins.manifest import load_manifest, ManifestError
from logger.logger_service import get_logger

logger = get_logger(__name__)

_S_IFLNK = 0xA000     # unix symlink mode bits, stored in zip external_attr


class InstallError(Exception):
    """The archive is malformed, unsafe, or could not be installed."""


class InstallCancelled(Exception):
    """The user declined the install at the consent prompt."""


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
    allowed_tops = set(manifest.packages) | {paths.MANIFEST_FILENAME}
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
    the PluginManifest. Nothing is extracted unless the manifest + all entries
    validate and consent is given. Raises InstallError / InstallCancelled."""
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
        try:
            zf.extractall(staging, members=members)
            if target.exists():
                shutil.rmtree(target)
            staging.replace(target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    paths.ensure_on_sys_path()
    manager.register_manifest(manifest)
    logger.info(f"installed plugin '{manifest.name}' to {target}")
    return manifest
