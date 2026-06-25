"""Filesystem locations + sys.path wiring for bundled and installed plugins."""

import sys
from pathlib import Path
from typing import Iterator

from traits.etsconfig.api import ETSConfig

# src/ — the dir microdrop_runner_setup puts on sys.path. Bundled default
# plugin manifests live under default_plugins/ beside the source packages.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

MANIFEST_FILENAME = "microdrop_plugin.json"


def default_plugins_dir() -> Path:
    """Repo-bundled plugin manifests (code lives in src/, already importable)."""
    return _PROJECT_ROOT / "default_plugins"


def installed_plugins_dir() -> Path:
    """Per-user installed plugins, beside preferences.ini in app-data
    (ETSConfig.application_home). Created if missing."""
    path = Path(ETSConfig.application_home) / "installed_plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_on_sys_path() -> None:
    """Put each installed plugin's own directory on sys.path so its bundled
    top-level package imports.

    An archive nests its package under the install dir
    (``installed_plugins/<name>/<package>/...``), because the installer's
    allowlist requires every file to live under a declared-package dir. So the
    import root is each ``<name>/`` dir, not the shared parent. The parent must
    NOT be on sys.path: a plugin whose ``<name>`` equals its package name would
    otherwise be shadowed by its own install dir resolving as a namespace
    package (``import <name>`` finding ``installed_plugins/<name>/`` instead of
    the real package nested one level deeper)."""
    root = installed_plugins_dir()
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / MANIFEST_FILENAME).is_file():
            path = str(child)
            if path not in sys.path:
                sys.path.append(path)


def iter_manifest_dirs() -> Iterator[Path]:
    """Yield each immediate subdir of default_plugins/ then installed_plugins/
    that contains a microdrop_plugin.json. Discovery order: bundled first."""
    for root in (default_plugins_dir(), installed_plugins_dir()):
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / MANIFEST_FILENAME).is_file():
                yield child
