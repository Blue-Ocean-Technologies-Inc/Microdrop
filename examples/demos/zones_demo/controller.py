# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free controller: mirrors the demo's pan/zone tool onto the shipped
manager's own ``mode`` trait and turns its button traits into calls,
mirroring device_viewer.controllers.zones_controller.ZonesController for the
button flows; the leave-zone-tools cancellation on switching to pan matches
the app's interaction service instead (ZonesController itself has no such
call)."""

# Enthought library imports.
from pyface.api import OK, FileDialog
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.consts import ZONE_DRAW_MODE, ZONE_SELECT_MODE
from device_viewer.models.electrodes import Electrodes
from microdrop_application.dialogs.pyface_wrapper import YES, confirm

# Local imports.
from .consts import DEVICE_SVG_RESOURCES_DIR, PAN_MODE
from .models import ZonesDemoModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class ZonesDemoController(HasTraits):
    model = Instance(ZonesDemoModel)

    # ---------------------------------------------------------------- device
    def load_device_svg(self, svg_path):
        electrodes_model = Electrodes()
        electrodes_model.set_electrodes_from_svg_file(str(svg_path))
        self.model.manager.set_device(
            electrodes_model.svg_model.polygons,
            electrodes_model.electrode_ids_channels_map,
            electrodes_model.svg_model.neighbours,
        )
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

    # ------------------------------------------------------------------ mode
    @observe("model:mode")
    def _mirror_mode_to_manager(self, event):
        if event.new == PAN_MODE:
            # The app's interaction service does the same when leaving the
            # zone tools entirely; a pending selection survives zone <->
            # zone-select switches (e.g. draw -> select), only pan drops it.
            self.model.manager.cancel_current_interaction()
            self.model.manager.selected_regions = []
        self.model.manager.mode = "" if event.new == PAN_MODE else event.new

    @observe("model:manager:mode")
    def _mirror_manager_mode(self, event):
        self.model.mode = event.new or PAN_MODE

    # ----------------------------------------------------------------- zones
    @observe("model:manager:commit_button")
    def _on_commit(self, event):
        manager = self.model.manager
        was_editing = manager.editing_region is not None
        if manager.commit_pending_region() is not None and was_editing:
            self.model.mode = ZONE_SELECT_MODE

    @observe("model:manager:clear_pending_button")
    def _on_clear_pending(self, event):
        manager = self.model.manager
        was_editing = manager.editing_region is not None
        manager.clear_pending()
        if was_editing:
            self.model.mode = ZONE_SELECT_MODE

    @observe("model:escape_pressed")
    def _on_escape(self, event):
        manager = self.model.manager
        was_editing = manager.editing_region is not None
        if manager.cancel_current_interaction() and was_editing:
            self.model.mode = ZONE_SELECT_MODE

    @observe("model:manager:add_zone_type_button")
    def _on_add_zone_type(self, event):
        manager = self.model.manager
        manager.selected_zone_type = manager.add_zone_type()

    @observe("model:manager:zone_types:items:delete_requested")
    def _on_zone_type_delete_requested(self, event):
        zone_type = event.object
        message = (
            f"Delete zone '{zone_type.name}' and its "
            f"{zone_type.region_count} region(s)?"
        )
        if zone_type.region_count == 0 or confirm(None, message) == YES:
            self.model.manager.remove_zone_type(zone_type.id)

    # --------------------------------------------------------------- regions
    @observe("model:manager:edit_region_button")
    def _on_edit_region(self, event):
        manager = self.model.manager
        if manager.selected_region is not None:
            manager.begin_edit_region(manager.selected_region)
            self.model.mode = ZONE_DRAW_MODE

    @observe("model:manager:delete_region_button")
    def _on_delete_region(self, event):
        self.model.manager.remove_region(self.model.manager.selected_region)

    @observe("model:manager:regions:items:delete_requested")
    def _on_region_delete_requested(self, event):
        self.model.manager.remove_region(event.object)

    @observe("model:manager:hide_region_button")
    def _on_hide_region(self, event):
        if self.model.manager.selected_region is not None:
            self.model.manager.selected_region.visible = False

    @observe("model:manager:merge_regions_button")
    def _on_merge_regions(self, event):
        self.model.manager.merge_selected_regions()

    @observe("model:undo_button")
    def _on_undo(self, event):
        self.model.manager.undo()

    @observe("model:redo_button")
    def _on_redo(self, event):
        self.model.manager.redo()
