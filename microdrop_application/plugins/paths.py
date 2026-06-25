"""Filesystem locations + sys.path wiring for bundled and installed plugins."""

import sys
from pathlib import Path
from typing import Iterator

from traits.etsconfig.api import ETSConfig

# src/ — the dir microdrop_runner_setup puts on sys.path. Bundled default
# plugin manifests live under default_plugins/ beside the source packages.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

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
    """Put the installed-plugins dir on sys.path so extracted packages import."""
    path = str(installed_plugins_dir())
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
