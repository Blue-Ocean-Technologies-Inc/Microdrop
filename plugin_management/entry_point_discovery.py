"""Discover installed plugin packages via Python entry points.

A plugin advertises a ``microdrop.plugins`` entry point and ships a
``microdrop_plugin.toml``. The manifest does not have to live *inside* the
entry-point's package — discovery looks for it in three places, in order:

1. **Package data** of the entry-point's module (``peripheral_controller/
   microdrop_plugin.toml``) — how bundled plugins ship it. Back-compat default.
2. The entry-point distribution's **dist-info** metadata
   (``…dist-info/microdrop_plugin.toml``).
3. Any ``microdrop_plugin.toml`` the **distribution** installs — e.g. a
   top-level manifest shipped as a namespaced data file (``shared-data``). This
   lets a standalone plugin keep its manifest at the repo top level, next to
   ``pyproject.toml``, instead of buried in one package.

We read the TOML into the same PluginManifest the rest of PluginGroupManager
consumes, and record the entry point's distribution name so callers can tell a
bundled plugin (shipped by the app's own distribution) from an installed one.
"""
import importlib.metadata as importlib_metadata
import importlib.resources as importlib_resources
import tomllib

from plugin_management.consts import ENTRY_POINT_GROUP, MANIFEST_RESOURCE
from plugin_management.manifest import manifest_from_dict, ManifestError
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _dist_name(ep) -> str:
    dist = getattr(ep, "dist", None)
    name = getattr(dist, "name", "") if dist is not None else ""
    return (name or "").strip()


def _read_manifest_text(ep):
    """Return the ``microdrop_plugin.toml`` text for an entry point, or None.

    Tries package data (the entry-point module), then the distribution's
    dist-info, then any same-named file the distribution installed."""
    # 1. package data of the entry-point's module
    try:
        resource = importlib_resources.files(ep.module) / MANIFEST_RESOURCE
        if resource.is_file():
            return resource.read_text(encoding="utf-8")
    except (ModuleNotFoundError, OSError, TypeError):
        pass

    dist = getattr(ep, "dist", None)
    if dist is None:
        return None

    # 2. dist-info metadata file
    try:
        text = dist.read_text(MANIFEST_RESOURCE)
        if text is not None:
            return text
    except (OSError, AttributeError):
        pass

    # 3. any file named microdrop_plugin.toml installed by the distribution
    try:
        for path in dist.files or ():
            if path.name == MANIFEST_RESOURCE:
                return path.read_text(encoding="utf-8")
    except (OSError, AttributeError):
        pass

    return None


def discover_entry_point_manifests():
    """``[(PluginManifest, dist_name)]`` for every installed package advertising a
    ``microdrop.plugins`` entry point and shipping a ``microdrop_plugin.toml``.
    Best-effort: a bad package is logged and skipped, never raised."""
    found = []
    for ep in importlib_metadata.entry_points(group=ENTRY_POINT_GROUP):
        try:
            text = _read_manifest_text(ep)
            if text is None:
                raise ManifestError(
                    f"no {MANIFEST_RESOURCE} found for entry-point plugin '{ep.name}'")
            manifest = manifest_from_dict(tomllib.loads(text))
        except (ManifestError, OSError, ValueError, ModuleNotFoundError,
                tomllib.TOMLDecodeError) as e:
            logger.exception(f"skipping entry-point plugin '{ep.name}': {e}")
            continue
        found.append((manifest, _dist_name(ep)))
    return found
