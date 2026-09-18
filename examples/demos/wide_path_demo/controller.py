# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free controller: the model's Button traits become calls, and a device
SVG becomes the model's polygons and neighbours. Nothing here computes —
the models react to what the controller sets."""

# Enthought library imports.
from pyface.api import OK, FileDialog
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.models.electrodes import Electrodes

# Local imports.
from .consts import DEVICE_SVG_RESOURCES_DIR
from .models import WidePathDemoModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class WidePathDemoController(HasTraits):
    model = Instance(WidePathDemoModel)

    # ---------------------------------------------------------------- device
    def load_device_svg(self, svg_path):
        """Replace the device (and every path on it) with the given SVG."""
        electrodes = Electrodes()
        electrodes.set_electrodes_from_svg_file(str(svg_path))
        self.model.paths = []
        self.model.selected_index = -1
        self.model.electrode_neighbours = dict(electrodes.svg_model.neighbours)
        self.model.electrode_polygons = dict(electrodes.svg_model.polygons)
        logger.info(f"Loaded device SVG {svg_path}")

    @observe("model:load_svg_button")
    def _on_load_svg(self, event):
        dialog = FileDialog(
            action="open",
            default_directory=str(DEVICE_SVG_RESOURCES_DIR),
            wildcard="SVG Files (*.svg)|*.svg|All Files (*)|*",
        )
        if dialog.open() == OK:
            self.load_device_svg(dialog.path)

    # ----------------------------------------------------------------- paths
    @observe("model:new_path_button")
    def _on_new_path(self, event):
        self.model.add_path(f"path {len(self.model.paths) + 1}")

    @observe("model:delete_path_button")
    def _on_delete_path(self, event):
        index = self.model.selected_index
        if self.model.selected is None:
            return
        self.model.paths = self.model.paths[:index] + self.model.paths[index + 1 :]
        self.model.selected_index = min(index, len(self.model.paths) - 1)

    @observe("model:undo_button")
    def _on_undo(self, event):
        if self.model.selected is not None:
            self.model.selected.undo()

    @observe("[model:clear_path_button, model:escape_pressed]")
    def _on_clear_path(self, event):
        if self.model.selected is not None:
            self.model.selected.clear()

    @observe("model:invert_button")
    def _on_invert(self, event):
        if self.model.selected is not None:
            self.model.selected.invert()

    @observe("model:merge_button")
    def _on_merge(self, event):
        self.model.merge_selected_with_next()

    # ---------------------------------------------------------------- phases
    @observe("model:prev_phase_button")
    def _on_prev_phase(self, event):
        self.model.step = max(self.model.step - 1, 0)

    @observe("model:next_phase_button")
    def _on_next_phase(self, event):
        self.model.step = min(self.model.step + 1, self.model.max_step)
