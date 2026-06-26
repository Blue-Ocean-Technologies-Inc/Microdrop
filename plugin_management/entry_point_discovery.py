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
