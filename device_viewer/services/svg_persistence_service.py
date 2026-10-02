# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free reading and writing of the device SVG (#640 step 4).

The service parses a device file into the model, writes the model back out
(channels, connections, metadata and the Zones layer), and tracks whether the
loaded device has unsaved edits. The dock pane keeps the file dialogs and the
scene, and reacts to ``loaded_path`` and ``modified`` for its title.
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import Bool, File, HasTraits, Instance, List, observe

# Local imports.
from ..interfaces.i_main_model import IDeviceViewMainModel
from ..interfaces.i_svg_layer_codec import ISvgLayerCodec
from ..preferences import DeviceViewerPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class SvgPersistenceService(HasTraits):
    """Load the device SVG into the model and save the model back to it."""

    #: Device view model the SVG is loaded into and saved from.
    model = Instance(IDeviceViewMainModel)

    #: Source of ``DEFAULT_SVG_FILE``, the device loaded when none is given.
    preferences = Instance(DeviceViewerPreferences)

    #: Codecs for the top-level layer groups sibling plugins own (#650).
    #: Reserved for #784; the Zones layer is still written by the SVG model.
    codecs = List(Instance(ISvgLayerCodec))

    #: The device file last loaded successfully; empty until the first load.
    loaded_path = File()

    #: True while the loaded device has edits not yet written to a file.
    modified = Bool(False)

    def traits_init(self):
        if self.preferences is None:
            return

        if not Path(self.preferences.DEFAULT_SVG_FILE).exists():
            self.preferences.reset_traits(["DEFAULT_SVG_FILE"])

    # ------------------------------------------------------------- load
    def load(self, svg_file=None):
        """Parse ``svg_file`` (default: the preferred device) into the model.

        Raises whatever the parse raises; the model is reset first either way.

        Returns
        -------
        int
            Number of zone records dropped or trimmed for referencing
            electrodes missing from the device.
        """

        if svg_file is None:
            svg_file = self.preferences.DEFAULT_SVG_FILE

        logger.info(f"Selected SVG file: {svg_file}")

        self.model.reset()

        # FIXME: Slow! Calculating centers via np.mean
        self.model.electrodes.set_electrodes_from_svg_file(svg_file)
        logger.debug(
            f"Created electrodes from SVG file: "
            f"{self.model.electrodes.svg_model.filename}"
        )

        unloaded = self.model.load_zones_from_device()

        self.modified = self.model.electrodes.svg_model.connections_modified
        self.loaded_path = str(svg_file)

        return unloaded

    # ------------------------------------------------------------- save
    def save(self):
        """Write the model back to the loaded device file."""
        self.model.electrodes.svg_save()
        self.modified = False

    def save_as(self, new_filename):
        """Write the model to ``new_filename``, adding ``.svg`` if missing."""

        if not new_filename.endswith(".svg"):
            new_filename = f"{new_filename}.svg"

        self.model.electrodes.svg_save_as(new_filename)
        self.modified = False

    # ------------------------------------------------------- observers
    @observe("model:electrodes:svg_model:area_scale", post_init=True)
    @observe("model:electrodes:svg_model:connections_modified")
    @observe("model.electrodes.electrodes.items.channel", post_init=True)
    def _svg_data_changed(self, event):
        logger.debug(f"Svg data changed event: {event}")

        if not self.modified:
            logger.info("Svg data changed")
            self.modified = True
