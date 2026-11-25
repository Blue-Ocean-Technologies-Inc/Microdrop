# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fake plugins loaded after the window paints, through the real deferred
loader, so the Plugins section fills in live: one loads, one fails the way a
heater board that is not plugged in would.
"""

# Standard library imports.
import time

# Enthought library imports.
from envisage.api import Plugin

#: Seconds this module takes to import, standing in for heavy imports, so
#: the plugins show as loading for a moment.
IMPORT_SECONDS = 1.2

time.sleep(IMPORT_SECONDS)


class FakeImageViewerPlugin(Plugin):
    """Loads fine and does nothing."""

    id = "notifications_ux_demo.image_viewer"
    name = "Image Viewer Plugin (demo)"


class FakeHeaterControlsPlugin(Plugin):
    """Fails to start, as without its heater board."""

    id = "notifications_ux_demo.heater_controls"
    name = "Heater Controls Plugin (demo)"

    def start(self):
        raise ConnectionError(
            "could not open port 'COM7': FileNotFoundError(2, 'The system "
            "cannot find the file specified.')"
        )
