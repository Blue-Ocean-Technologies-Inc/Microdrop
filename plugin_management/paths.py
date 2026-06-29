"""Filesystem locations for plugin management.

Provides helpers for the app-data cache that stores the last-fetched channel
package index."""

from pathlib import Path

from traits.etsconfig.api import ETSConfig


def plugin_index_file() -> Path:
    """App-data file caching the last fetched channel package list (JSON).
    Lives under ETSConfig.application_home; the dir is created if missing."""
    home = Path(ETSConfig.application_home)
    home.mkdir(parents=True, exist_ok=True)
    return home / "plugin_index.json"
