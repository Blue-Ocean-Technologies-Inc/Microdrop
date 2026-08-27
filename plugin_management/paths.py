# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

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
