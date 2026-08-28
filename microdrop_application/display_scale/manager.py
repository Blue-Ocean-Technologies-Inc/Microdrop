# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Controller for Display Scale: builds the model from the running
process, runs the dialog, persists the choice, and offers the relaunch
that makes it real. GUI-thread only; no Redis or dramatiq involvement."""

# Enthought library imports.
from pyface.qt.QtWidgets import QApplication
from traits.api import HasTraits

# Local imports.
from ..dialogs.pyface_wrapper import YES, confirm
from ..preferences import MicrodropPreferences
from .model import DisplayScaleModel
from .startup import active_scale_percent, read_scale_percent, request_relaunch
from .view import display_scale_view

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class DisplayScaleManager(HasTraits):
    def edit_scale(self, application):
        """Run the Display Scale dialog and act on what the user picked."""
        model = DisplayScaleModel(
            scale_percent=read_scale_percent(),
            active_scale_percent=active_scale_percent(),
        )
        model.trait_set(**self._native_screen_size(model.active_scale_percent))

        if not model.edit_traits(view=display_scale_view).result:
            return

        self._persist(application, model.scale_percent)

        if model.relaunch_needed:
            self._offer_relaunch(application, model.scale_percent)

    def _persist(self, application, percent):
        """Write the scale into the app preferences, and to disk now.

        Preferences are normally flushed when the application stops, but
        the relaunch offered next races that — so this saves eagerly and
        the replacement process is guaranteed to read the new value.
        """
        MicrodropPreferences(
            preferences=application.preferences
        ).ui_scale_percent = percent
        application.preferences.save()
        logger.info(f"Interface scale preference set to {percent}%")

    @staticmethod
    def _offer_relaunch(application, percent):
        if (
            confirm(
                parent=None,
                title="Restart Microdrop?",
                message=(
                    f"The interface scale is now <b>{percent}%</b>.<br><br>"
                    "Microdrop has to restart to apply it. Restart now?"
                ),
            )
            != YES
        ):
            logger.info("Interface scale saved; user deferred the restart.")
            return

        request_relaunch()
        application.exit()

    @staticmethod
    def _native_screen_size(active_percent):
        """The screen's size in interface points at 100% scale.

        Qt reports the geometry in points already scaled by whatever
        ``QT_SCALE_FACTOR`` this process started with, so undoing that
        factor is what gives a figure the slider can be measured
        against.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            return {}

        size = screen.geometry().size()

        return {
            "screen_width": round(size.width() * active_percent / 100),
            "screen_height": round(size.height() * active_percent / 100),
        }


#: The one manager the menu action talks to.
display_scale_manager = DisplayScaleManager()
