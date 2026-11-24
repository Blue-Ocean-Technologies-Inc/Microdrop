# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free loading of a device SVG into the Device Viewer's model (#1087).

A load is state other plugins depend on — the electrodes and their channels,
the geometry published on DEVICE_VIEWER_GEOMETRY_CHANGED, the preferred
device — so it happens whether or not the pane's view is built. The pane
builds its view from the loaded model: on its first show, and again after
each load once it is built.
"""

# Standard library imports.
import traceback

# Enthought library imports.
from traits.api import Bool, HasTraits, Instance

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import error, warning

# Local imports.
from ..preferences import DeviceViewerPreferences
from ..services.svg_persistence_service import SvgPersistenceService
from .device_viewer_publish_controller import DeviceViewerPublishController

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class DeviceLoadController(HasTraits):
    """Load a device into the model, announce it, and report a failure."""

    #: Parses the device SVG into the model.
    svg_persistence = Instance(SvgPersistenceService)

    #: Publishes the loaded device's geometry.
    publish_controller = Instance(DeviceViewerPublishController)

    #: Holds the preferred device, ``DEFAULT_SVG_FILE``.
    preferences = Instance(DeviceViewerPreferences)

    #: True while the model holds a device loaded in full; a failed load,
    #: which leaves the model reset, clears it.
    device_loaded = Bool(False)

    def load(self, svg_file=None):
        """Load ``svg_file`` (default: the preferred device) into the model
        and publish its geometry; it becomes the preferred device.

        A failure is logged and shown to the user.

        Returns
        -------
        bool
            Whether the device loaded.
        """

        if svg_file is None:
            svg_file = self.preferences.DEFAULT_SVG_FILE

        try:
            unloaded = self.svg_persistence.load(svg_file)

        except Exception as e:
            self.device_loaded = False
            self._report_load_failure(svg_file, e)

            return False

        self.device_loaded = True

        if unloaded > 0:
            warning(
                None,
                f"{unloaded} zone region(s) in this device file reference "
                "electrodes that do not exist in it and were dropped or "
                "trimmed. Saving the file will write it without those "
                "electrodes.",
                title="Zones Not Loaded",
            )

        # A new device starts a new undo history.
        self.svg_persistence.model.undo_manager.active_stack.clear()

        # The channel mapping is established: tell the other plugins.
        self.publish_controller._publish_geometry_if_changed()

        self.preferences.DEFAULT_SVG_FILE = svg_file

        return True

    def _report_load_failure(self, svg_file, e):
        logger.error(
            f"Could not create electrodes from SVG file: {svg_file}. Error: {e}",
            exc_info=True,
        )
        error(
            None,
            f"Could not create electrodes from SVG file: {svg_file} "
            f"<br><br> Reason: {e}",
            detail="".join(traceback.format_exception(type(e), e, e.__traceback__)),
            title="Error: Cannot Load Device SVG",
        )
