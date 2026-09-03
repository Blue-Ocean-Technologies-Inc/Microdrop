# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI sidebar section for electrode zones, edited directly on the
ZoneLayerManager: three button rows of four over the zones tree-table (zone
types with their regions nested underneath).

The rows group by workflow — the two tools with their modifier toggles, then
what acts on the current selection, then the zone list and the view — and all
of it is push-button editors styled by the sidebar stylesheet. Standalone:
``manager.edit_traits(view=zones_view)``."""

# Enthought library imports.
from traitsui.api import (
    CustomEditor,
    HGroup,
    Spring,
    UItem,
    VGroup,
    View,
    spring,
)

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_CALL_TO_ACTION,
    ICON_CHECKLIST,
    ICON_CROP,
    ICON_REMOVE_SELECTION,
    ICON_SELECT_All,
)

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    QT_LAYOUT_MARGIN_PX,
    QT_LAYOUT_SPACING_PX,
    SafeCancelTableHandler,
    ToggleButtonEditor,
)

# Local imports.
from ...consts import ZONE_DRAW_MODE, ZONE_SELECT_MODE
from .zone_tree import zone_tree_factory


def inset(dimension):
    """Spacer giving a TraitsUI group the margin a plain Qt child layout has
    (TraitsUI keeps the item spacing but drops the margin): ``"width"`` leads
    a button row so it lines up with the Qt rows in the sidebar (the Paths
    picker), ``"height"`` separates the section from its collapsible header
    like the other sidebar groups."""
    return Spring(
        springy=False, **{dimension: QT_LAYOUT_MARGIN_PX - QT_LAYOUT_SPACING_PX}
    )


class ZonesSidebarHandler(SafeCancelTableHandler):
    def handle_escape(self, info):
        """Escape clears both selections. It stays on the handler rather than
        the tree widget: the handler's own shortcut (which keeps Escape from
        closing the view) covers the whole section, and a second Escape
        shortcut inside it would make both ambiguous to Qt."""
        info.object.selected_region = None
        info.object.selected_zone_type = None
        super().handle_escape(info)


zones_view = View(
    VGroup(
        inset("height"),
        # Row 1 — the two tools, each followed by its modifier toggle.
        HGroup(
            inset("width"),
            UItem(
                "draw_tool_active",
                editor=ToggleButtonEditor(glyph=ICON_CROP, tooltip="Draw zones"),
            ),
            UItem(
                "subtract_mode",
                editor=ToggleButtonEditor(
                    glyph=ICON_REMOVE_SELECTION,
                    tooltip=(
                        "Undraw: rubber bands remove electrodes from the selection"
                    ),
                ),
                enabled_when=f"mode == '{ZONE_DRAW_MODE}'",
            ),
            UItem(
                "select_tool_active",
                editor=ToggleButtonEditor(
                    glyph=ICON_SELECT_All, tooltip="Select zones"
                ),
            ),
            UItem(
                "multi_select",
                editor=ToggleButtonEditor(
                    glyph=ICON_CHECKLIST,
                    tooltip="Multi-select: clicks add regions to the selection",
                ),
                enabled_when=f"mode == '{ZONE_SELECT_MODE}'",
            ),
            spring,
        ),
        # Row 2 — what acts on the current selection, draw side then select
        # side, matching the tool order of row 1.
        HGroup(
            inset("width"),
            UItem(
                "commit_button",
                tooltip="Commit zone",
                enabled_when=(
                    f"mode == '{ZONE_DRAW_MODE}' and len(pending_electrode_ids) > 0"
                ),
            ),
            UItem(
                "clear_pending_button",
                tooltip="Clear selection",
                enabled_when=(
                    "len(pending_electrode_ids) > 0 or editing_region is not None"
                ),
            ),
            UItem(
                "edit_region_button",
                tooltip="Edit region",
                enabled_when=(
                    f"mode == '{ZONE_SELECT_MODE}' and selected_region is not None"
                ),
            ),
            UItem(
                "merge_regions_button",
                tooltip="Merge the ctrl+click-selected regions",
                enabled_when=(
                    f"mode == '{ZONE_SELECT_MODE}' and len(selected_regions) >= 2"
                ),
            ),
            spring,
        ),
        # Row 3 — the zone list itself, and the view.
        HGroup(
            inset("width"),
            UItem("add_zone_type_button", tooltip="Add zone type"),
            UItem(
                "move_zone_type_up_button",
                tooltip="Move the zone up a layer",
                enabled_when="selected_zone_type is not None",
            ),
            UItem(
                "move_zone_type_down_button",
                tooltip="Move the zone down a layer",
                enabled_when="selected_zone_type is not None",
            ),
            UItem(
                "show_canvas_overlays",
                editor=ToggleButtonEditor(
                    glyph=ICON_CALL_TO_ACTION,
                    tooltip="Show or hide the floating canvas buttons",
                ),
            ),
            spring,
        ),
        UItem("zone_types", editor=CustomEditor(zone_tree_factory)),
    ),
    handler=ZonesSidebarHandler(),
    resizable=True,
)
