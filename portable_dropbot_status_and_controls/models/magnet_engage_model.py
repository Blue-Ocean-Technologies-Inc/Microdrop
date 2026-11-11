# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Board-side state of the magnet engage height, behind the Portable
DropBot Settings tab's Read / Write / Preset to flash buttons."""

# Enthought library imports.
from traits.api import Event, Float, HasTraits, Str


class MagnetEngageModel(HasTraits):
    """Qt-free outcome of the last magnet engage request. The plugin keeps
    one for the session, so a reopened preferences dialog still shows the
    last result."""

    #: Last outcome, for the tab's status line.
    status = Str("Not read from the board yet")

    #: Fires with the board's engage height (mm) when a read returns; the
    #: tab fills its unapplied field from it.
    engage_read = Event(Float)

    def apply_update(self, update):
        """Show a MagnetEngageUpdated: its outcome on the status line, and a
        successful read's height through engage_read."""
        if update.error:
            self.status = f"{update.action.capitalize()} failed: {update.error}"
            return

        if update.action == "read":
            self.status = f"Board: {update.engage_mm:.3f} mm"
            self.engage_read = update.engage_mm

        elif update.action == "write":
            self.status = (
                f"Written to RAM: {update.engage_mm:.3f} mm "
                f"(lost on reboot; Preset to keep)"
            )

        else:
            self.status = "Preset to flash (survives reboots)"
