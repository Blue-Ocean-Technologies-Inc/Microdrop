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
ZoneLayerManager: the tool row, the zone types table, and the regions
table, all push-button editors styled by the sidebar stylesheet. Standalone:
``manager.edit_traits(view=zones_view)``."""

# Enthought library imports.
from traitsui.api import HGroup, Spring, TableEditor, UItem, VGroup, View, spring

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_CALL_TO_ACTION,
    ICON_CROP,
    ICON_DELETE,
    ICON_SELECT_All,
)

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    QT_LAYOUT_MARGIN_PX,
    QT_LAYOUT_SPACING_PX,
    ColorColumn,
    GlyphActionColumn,
    HexColorEditorFactory,
    ObjectColumn,
    SafeCancelTableHandler,
    ToggleButtonEditor,
    VisibleColumn,
)

# Local imports.
from ...consts import ZONE_DRAW_MODE, ZONE_SELECT_MODE

zone_types_table_editor = TableEditor(
    columns=[
        # Proportional widths so the columns fill the table (TraitsUI's
        # interactive default keeps them at content width, which leaves an
        # empty table's glyph columns invisible); glyph columns get small
        # shares so they stay compact.
        ObjectColumn(name="name", label="Zone", width=0.36),
        ColorColumn(
            name="color", label="Color", editor=HexColorEditorFactory(), width=0.22
        ),
        ObjectColumn(name="region_count", label="#", editable=False, width=0.14),
        # Bulk eye: shows or hides every region of the zone.
        VisibleColumn(
            name="visible",
            label="",
            editable=False,
            horizontal_alignment="center",
            width=0.14,
        ),
        GlyphActionColumn(
            name="id", label="", glyph=ICON_DELETE, fire="delete_requested", width=0.14
        ),
    ],
    selected="selected_zone_type",
    selection_mode="row",
    sortable=False,
    auto_size=True,
    show_row_labels=True,
)

zone_regions_table_editor = TableEditor(
    columns=[
        # The region id embeds its zone ("heating-1"), so no zone column;
        # content width, the glyph columns take small shares of the rest.
        ObjectColumn(name="id", label="Region", editable=False),
        VisibleColumn(
            name="visible",
            label="",
            editable=False,
            horizontal_alignment="center",
            width=0.14,
        ),
        GlyphActionColumn(
            name="id", label="", glyph=ICON_DELETE, fire="delete_requested", width=0.14
        ),
    ],
    selected="selected_region",
    selection_mode="row",
    sortable=False,
    auto_size=True,
    show_row_labels=True,
)


def row_inset():
    """Leading spacer giving a button row the same left margin as the Qt
    button rows elsewhere in the sidebar (the Paths picker)."""
    return Spring(width=QT_LAYOUT_MARGIN_PX - QT_LAYOUT_SPACING_PX, springy=False)


class ZonesSidebarHandler(SafeCancelTableHandler):
    def handle_escape(self, info):
        """Escape deselects in both tables (a click on empty table space
        already does, through the editors' selection sync)."""
        info.object.selected_region = None
        info.object.selected_zone_type = None
        super().handle_escape(info)


zones_view = View(
    VGroup(
        HGroup(
            row_inset(),
            UItem(
                "draw_tool_active",
                editor=ToggleButtonEditor(glyph=ICON_CROP, tooltip="Draw zones"),
            ),
            UItem(
                "select_tool_active",
                editor=ToggleButtonEditor(
                    glyph=ICON_SELECT_All, tooltip="Select zones"
                ),
            ),
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
            spring,
        ),
        UItem("zone_types", editor=zone_types_table_editor),
        # Spans the table above like an extra row, following its width.
        UItem("add_zone_type_button", springy=True, tooltip="Add zone type"),
        UItem("regions", editor=zone_regions_table_editor),
        HGroup(
            row_inset(),
            UItem(
                "edit_region_button",
                tooltip="Edit region",
                enabled_when=(
                    f"mode == '{ZONE_SELECT_MODE}' and selected_region is not None"
                ),
            ),
            UItem(
                "hide_region_button",
                tooltip="Hide region",
                enabled_when="selected_region is not None",
            ),
            UItem(
                "merge_regions_button",
                tooltip="Merge the ctrl+click-selected regions",
                enabled_when=(
                    f"mode == '{ZONE_SELECT_MODE}' and len(selected_regions) >= 2"
                ),
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
    ),
    handler=ZonesSidebarHandler(),
    resizable=True,
)
