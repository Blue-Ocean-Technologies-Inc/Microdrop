# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free controller: sidebar button clicks and mode transitions."""

from pyface.api import OK, FileDialog
from traits.api import HasTraits, Instance, observe

from device_viewer.models.electrodes import Electrodes

from .consts import (
    DEVICE_SVG_RESOURCES_DIR,
    EDIT_MODE,
    SELECT_MODE,
    ZONE_COLOR_CYCLE,
)
from .models import ZonesDemoModel

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
    def _on_mode_changed(self, event):
        manager = self.model.manager
        if event.new == EDIT_MODE:
            if manager.selected_region is None:
                # Nothing to edit; bounce back to where the user was.
                self.model.mode = event.old
            else:
                manager.begin_edit_region(manager.selected_region)
        elif event.old == EDIT_MODE and manager.editing_region is not None:
            # Leaving edit mode without committing cancels the edit (the
            # region reappears unchanged); after a commit or clear the
            # editing_region is already gone and this no-ops.
            manager.clear_pending()

    # ----------------------------------------------------------------- zones
    @observe("model:commit_button")
    def _on_commit(self, event):
        manager = self.model.manager
        was_editing = manager.editing_region is not None
        region = manager.commit_pending_region()
        # An edit is a detour from select mode; land back there so the
        # committed region stays selected and re-editable.
        if was_editing and region is not None:
            self.model.mode = SELECT_MODE

    @observe("model:clear_pending_button")
    def _on_clear_pending(self, event):
        self._clear_pending()

    def _clear_pending(self):
        manager = self.model.manager
        was_editing = manager.editing_region is not None
        manager.clear_pending()
        if was_editing:
            self.model.mode = SELECT_MODE

    @observe("model:escape_pressed")
    def _on_escape(self, event):
        # Cancel the innermost thing first: an in-progress selection/edit,
        # then the region selection; a bare Escape is a no-op.
        manager = self.model.manager
        if manager.pending_electrode_ids or manager.editing_region is not None:
            self._clear_pending()
        elif manager.selected_regions:
            manager.selected_regions = []

    @observe("model:add_zone_type_button")
    def _on_add_zone_type(self, event):
        manager = self.model.manager
        name = self.model.new_zone_type_name.strip()
        if not name:
            return
        color = ZONE_COLOR_CYCLE[len(manager.zone_types) % len(ZONE_COLOR_CYCLE)]
        manager.selected_zone_type = manager.add_zone_type(name, color)
        self.model.new_zone_type_name = ""

    @observe("model:remove_zone_type_button")
    def _on_remove_zone_type(self, event):
        manager = self.model.manager
        if manager.selected_zone_type is not None:
            manager.remove_zone_type(manager.selected_zone_type.id)

    @observe("model:manager:zone_types:items:delete_requested")
    def _on_zone_type_delete_requested(self, event):
        # Per-row trash glyph; the manager cascades the type's regions away.
        self.model.manager.remove_zone_type(event.object.id)

    # --------------------------------------------------------------- regions
    @observe("model:edit_region_button")
    def _on_edit_region(self, event):
        # The mode observer does the actual begin_edit_region.
        if self.model.manager.selected_region is not None:
            self.model.mode = EDIT_MODE

    @observe("model:delete_region_button")
    def _on_delete_region(self, event):
        self.model.manager.remove_region(self.model.manager.selected_region)

    @observe("model:hide_region_button")
    def _on_hide_region(self, event):
        if self.model.manager.selected_region is not None:
            self.model.manager.selected_region.visible = False

    @observe("model:merge_regions_button")
    def _on_merge_regions(self, event):
        # Ctrl+click regions on the canvas to multi-select; no-op below two.
        self.model.manager.merge_selected_regions()

    @observe("model:undo_button")
    def _on_undo(self, event):
        self.model.manager.undo()

    @observe("model:redo_button")
    def _on_redo(self, event):
        self.model.manager.redo()
