"""Parse and validate a plugin manifest.

Declares the plugin GROUP(s) a package forms so PluginGroupManager can
register and hot load/unload them. Pure inert data — no Traits, no Qt.
"""

from dataclasses import dataclass
from typing import List

SCHEMA_VERSION = 1


class ManifestError(ValueError):
    """A plugin manifest is missing, malformed, or fails validation."""


@dataclass
class PluginGroupSpec:
    name: str
    label: str
    plugins: List[str]                       # dotted "module:Class" specs
    enabled_key: str
    post_enable_publish_topic: str = ""
    optional: bool = False
    toggle_label: str = ""


@dataclass
class PluginManifest:
    schema_version: int
    name: str
    label: str
    version: str
    packages: List[str]
    groups: List[PluginGroupSpec]


def manifest_from_dict(data) -> PluginManifest:
    """Validate an already-parsed manifest mapping (from JSON or TOML) into a
    PluginManifest. Raises ManifestError on any problem."""
    if not isinstance(data, dict):
        raise ManifestError("manifest must be a mapping")

    schema = data.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported schema_version {schema!r} (expected {SCHEMA_VERSION})"
        )

    name = data.get("name")
    if not name or not isinstance(name, str):
        raise ManifestError("manifest 'name' is required and must be a string")

    packages = data.get("packages")
    if (not isinstance(packages, list) or not packages
            or not all(isinstance(p, str) and p for p in packages)):
        raise ManifestError("manifest 'packages' must be a non-empty list of strings")

    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        raise ManifestError("manifest 'groups' must be a non-empty list")

    groups = []
    for i, g in enumerate(raw_groups):
        if not isinstance(g, dict):
            raise ManifestError(f"group #{i} must be a mapping")
        gname = g.get("name")
        if not gname or not isinstance(gname, str):
            raise ManifestError(f"group #{i} 'name' is required")
        plugins = g.get("plugins")
        if (not isinstance(plugins, list) or not plugins
                or not all(isinstance(p, str) and ":" in p for p in plugins)):
            raise ManifestError(
                f"group '{gname}' 'plugins' must be a non-empty list of "
                f"'module:Class' strings"
            )
        enabled_key = g.get("enabled_key")
        if not enabled_key or not isinstance(enabled_key, str):
            raise ManifestError(f"group '{gname}' 'enabled_key' is required")
        groups.append(PluginGroupSpec(
            name=gname,
            label=g.get("label") or gname,
            plugins=list(plugins),
            enabled_key=enabled_key,
            post_enable_publish_topic=g.get("post_enable_publish_topic", "") or "",
            optional=bool(g.get("optional", False)),
            toggle_label=str(g.get("toggle_label", "") or ""),
        ))

    return PluginManifest(
        schema_version=schema,
        name=name,
        label=data.get("label") or name,
        version=str(data.get("version", "")),
        packages=list(packages),
        groups=groups,
    )
