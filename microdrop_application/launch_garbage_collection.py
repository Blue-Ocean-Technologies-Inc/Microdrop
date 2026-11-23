# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Keep the cyclic garbage collector's full passes out of the launch.

A full (generation 2) pass walks every tracked object with the GUI thread
stopped. With the launch heap of plugins, Traits models and widgets that is
0.3-0.5 s, and the heap grows fast enough while the window fills in to
trigger two such passes. The pause turns automatic collection off from the
application's construction until the deferred plugins have loaded, then
freezes the objects alive at that point (the long-lived launch heap) into
the permanent generation and turns collection back on, so later full passes
walk only what was created since.

Collection comes back on whatever happens: when the deferred plugins have
loaded, when the application stops, or after ``LAUNCH_GC_PAUSE_LIMIT_MS`` at
the latest.
"""

# Standard library imports.
import gc

# Enthought library imports.
from envisage.api import IApplication
from pyface.api import GUI
from traits.api import Bool, HasTraits, Instance, observe

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Collection comes back on this long after the pause began, at the latest,
#: should the deferred plugins never finish loading.
LAUNCH_GC_PAUSE_LIMIT_MS = 60_000


class LaunchGarbageCollectionPause(HasTraits):
    """Automatic garbage collection off for the launch, then back on."""

    #: The application whose launch the pause covers.
    application = Instance(IApplication)

    #: True while this pause has automatic collection off.
    paused = Bool(False)

    def pause(self):
        """Turn automatic collection off, unless it is off already."""
        if not gc.isenabled():
            return

        gc.disable()
        self.paused = True
        GUI.invoke_after(LAUNCH_GC_PAUSE_LIMIT_MS, self.resume)

    @observe("application:extra_plugins_loaded, application:stopped")
    def _resume_after_launch(self, event):
        self.resume()

    def resume(self):
        """Freeze the launch heap and turn automatic collection back on."""
        if not self.paused:
            return

        gc.freeze()
        gc.enable()
        self.paused = False

        logger.info(
            f"Garbage collection back on; {gc.get_freeze_count()} launch objects frozen"
        )
