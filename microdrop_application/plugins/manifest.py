"""Parse and validate a microdrop_plugin.json manifest.

The manifest (at the root of a .microdrop_plugin archive, or in a
default_plugins/<name>/ directory) declares the Python packages an archive
carries and the plugin GROUP(s) they form, so PluginGroupManager can register
and hot load/unload them. Pure inert data — no Traits, no Qt.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

SCHEMA_VERSION = 1


class ManifestError(ValueError):
    """A microdrop_plugin.json is missing, malformed, or fails validation."""


@dataclass
class PluginGroupSpec:
    name: str
    label: str
    plugins: List[str]                       # dotted "module:Class" specs
    enabled_key: str
    post_enable_publish_topic: str = ""


@dataclass
class PluginManifest:
    schema_version: int
    name: str
    label: str
    version: str
    packages: List[str]
    groups: List[PluginGroupSpec]


def load_manifest(source: Union[str, bytes, Path]) -> PluginManifest:
    """Parse + validate a manifest from a path, JSON string, or raw bytes.

    Raises ManifestError with a clear message on any problem."""
    try:
        if isinstance(source, (str, Path)) and Path(str(source)).exists():
            text = Path(source).read_text(encoding="utf-8")
        elif isinstance(source, bytes):
            text = source.decode("utf-8")
        else:
            text = str(source)
        data = json.loads(text)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        raise ManifestError(f"could not read manifest JSON: {e}") from e

    if not isinstance(data, dict):
        raise ManifestError("manifest must be a JSON object")

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
            raise ManifestError(f"group #{i} must be a JSON object")
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
        ))

    return PluginManifest(
        schema_version=schema,
        name=name,
        label=data.get("label") or name,
        version=str(data.get("version", "")),
        packages=list(packages),
        groups=groups,
    )
