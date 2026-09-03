# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free controller for electrode zones: sidebar/overlay button traits and
mode transitions become ZoneLayerManager calls."""

# Enthought library imports.
from traits.api import HasTraits, Instance, Str, observe

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import YES, confirm

# Local imports.
from ..consts import ZONE_DRAW_MODE, ZONE_MODES, ZONE_SELECT_MODE
from ..models.main_model import DeviceViewMainModel
from ..utils.commands import ZoneStateCommand

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class ZonesController(HasTraits):
    #: Device view whose mode/zones this controller keeps in sync.
    model = Instance(DeviceViewMainModel)

    #: Device-view mode in use before the zone tools were entered; Off
    #: returns to it (model.last_mode is clobbered by zone→zone switches).
    _mode_before_zone_tools = Str("draw")

    # ----------------------------------------------------------------- tool
    @observe("model:mode")
    def _mirror_mode_to_tool(self, event):
        if event.new in ZONE_MODES and event.old not in ZONE_MODES:
            self._mode_before_zone_tools = event.old
        # The sidebar radio shows Off whenever another device tool is active.
        self.model.zones.mode = event.new if event.new in ZONE_MODES else ""

    @observe("model:zones:mode")
    def _on_tool_changed(self, event):
        if event.new:
            if self.model.mode != event.new:
                self.model.mode = event.new
        elif self.model.mode in ZONE_MODES:
            # Off: return to the tool in use before the zone tools.
            self.model.mode = self._mode_before_zone_tools

    # ----------------------------------------------------------------- draw
    @observe("model:zones:commit_button")
    def _on_commit(self, event):
        manager = self.model.zones
        was_editing = manager.editing_region is not None
        region = manager.commit_pending_region()
        # An edit is a detour from select mode; land back there so the
        # committed region stays selected and re-editable.
        if was_editing and region is not None:
            self.model.mode = ZONE_SELECT_MODE

    @observe("model:zones:clear_pending_button")
    def _on_clear_pending(self, event):
        manager = self.model.zones
        was_editing = manager.editing_region is not None
        manager.clear_pending()
        if was_editing:
            self.model.mode = ZONE_SELECT_MODE

    # ---------------------------------------------------------------- types
    @observe("model:zones:add_zone_type_button")
    def _on_add_zone_type(self, event):
        manager = self.model.zones
        manager.selected_zone_type = manager.add_zone_type()

    @observe("model:zones:zone_types:items:delete_requested")
    def _on_zone_type_delete_requested(self, event):
        zone_type = event.object
        message = (
            f"Delete zone '{zone_type.name}' and its "
            f"{zone_type.region_count} region(s)?"
        )
        if zone_type.region_count == 0 or confirm(None, message) == YES:
            self.model.zones.remove_zone_type(zone_type.id)

    # -------------------------------------------------------------- regions
    @observe("model:zones:edit_region_button")
    def _on_edit_region(self, event):
        manager = self.model.zones
        if manager.selected_region is None:
            return
        manager.begin_edit_region(manager.selected_region)
        self.model.mode = ZONE_DRAW_MODE

    @observe("model:zones:delete_region_button")
    def _on_delete_region(self, event):
        self.model.zones.remove_region(self.model.zones.selected_region)

    @observe("model:zones:regions:items:delete_requested")
    def _on_region_delete_requested(self, event):
        # Per-row trash glyph in the regions table.
        self.model.zones.remove_region(event.object)

    @observe("model:zones:hide_region_button")
    def _on_hide_region(self, event):
        if self.model.zones.selected_region is not None:
            self.model.zones.selected_region.visible = False

    @observe("model:zones:merge_regions_button")
    def _on_merge_regions(self, event):
        self.model.zones.merge_selected_regions()

    # ----------------------------------------------------------------- undo
    @observe("model:zones:undo_snapshot_pushed")
    def _on_undo_snapshot_pushed(self, event):
        undo_manager = self.model.undo_manager
        if undo_manager is None:
            return
        undo_manager.active_stack.push(ZoneStateCommand(manager=self.model.zones))
