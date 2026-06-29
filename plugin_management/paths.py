"""Filesystem locations for plugins.

Provides helpers for the app-data cache that stores the last-fetched channel
package index, and the local conda channel dir used when installing a .conda
file from disk."""

from pathlib import Path

from traits.etsconfig.api import ETSConfig


def plugin_index_file() -> Path:
    """App-data file caching the last fetched channel package list (JSON).
    Lives under ETSConfig.application_home; the dir is created if missing."""
    home = Path(ETSConfig.application_home)
    home.mkdir(parents=True, exist_ok=True)
    return home / "plugin_index.json"


def plugin_channel_dir() -> Path:
    """The local conda channel dir (under ETSConfig.application_home) into which
    installed plugin .conda files are copied + indexed. Created if missing, with
    a noarch/ subdir (conda channels are organised by subdir)."""
    path = Path(ETSConfig.application_home) / "plugin_channel"
    (path / "noarch").mkdir(parents=True, exist_ok=True)
    return path
