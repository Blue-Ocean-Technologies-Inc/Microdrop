"""Filesystem location of the local conda channel that holds installed plugin
packages (built .conda files), under the app-data dir."""

from pathlib import Path

from traits.etsconfig.api import ETSConfig


def plugin_channel_dir() -> Path:
    """The local conda channel dir (under ETSConfig.application_home) into which
    installed plugin .conda files are copied + indexed. Created if missing, with
    a noarch/ subdir (conda channels are organised by subdir)."""
    path = Path(ETSConfig.application_home) / "plugin_channel"
    (path / "noarch").mkdir(parents=True, exist_ok=True)
    return path
