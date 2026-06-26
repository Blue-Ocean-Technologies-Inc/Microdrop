"""Discover installed plugin packages via Python entry points — an additive,
flag-gated alternative to directory-based manifest discovery.

A plugin package advertises itself with a ``microdrop.plugins`` entry point and
ships a ``microdrop_plugin.toml`` (same shape as microdrop_plugin.json) as
package data. We read that TOML and build the same PluginManifest the JSON path
produces, so the rest of PluginGroupManager is unchanged.
"""
import importlib.metadata as importlib_metadata
import importlib.resources as importlib_resources
import os
import tomllib

from plugin_management.manifest import manifest_from_dict, ManifestError
from logger.logger_service import get_logger

logger = get_logger(__name__)

ENTRY_POINT_GROUP = "microdrop.plugins"
MANIFEST_RESOURCE = "microdrop_plugin.toml"
_FLAG_ENV = "MICRODROP_ENTRYPOINT_PLUGINS"


def enabled() -> bool:
    """Entry-point discovery is opt-in for the spike, so the existing
    directory-based discovery is undisturbed when the flag is unset."""
    return os.environ.get(_FLAG_ENV) == "1"


def discover_entry_point_manifests():
    """Return ``[(PluginManifest, source_label)]`` for every installed package
    that advertises a ``microdrop.plugins`` entry point and ships a
    ``microdrop_plugin.toml``. Best-effort: a bad package is logged and skipped,
    never raised."""
    found = []
    for ep in importlib_metadata.entry_points(group=ENTRY_POINT_GROUP):
        pkg = ep.value
        try:
            resource = importlib_resources.files(pkg) / MANIFEST_RESOURCE
            data = tomllib.loads(resource.read_text(encoding="utf-8"))
            manifest = manifest_from_dict(data)
        except (ManifestError, OSError, ValueError, ModuleNotFoundError,
                tomllib.TOMLDecodeError) as e:
            logger.exception(f"skipping entry-point plugin '{pkg}': {e}")
            continue
        found.append((manifest, f"entry-point:{pkg}"))
    return found
