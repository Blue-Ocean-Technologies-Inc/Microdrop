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
ZoneLayerManager: the tool radio, the zone types table, the regions table,
and the commit / edit buttons. Standalone:
``manager.edit_traits(view=zones_view)``."""

# Enthought library imports.
from traitsui.api import EnumEditor, HGroup, Item, TableEditor, UItem, VGroup, View

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_DELETE

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    ColorColumn,
    GlyphActionColumn,
    HexColorEditorFactory,
    ObjectColumn,
    SafeCancelTableHandler,
    VisibleColumn,
)

# Local imports.
from ...consts import ZONE_DRAW_MODE, ZONE_SELECT_MODE

zone_tool_editor = EnumEditor(
    values={"": "Off", ZONE_DRAW_MODE: "Draw", ZONE_SELECT_MODE: "Select"},
    cols=3,
)

zone_types_table_editor = TableEditor(
    columns=[
        ObjectColumn(name="name", label="Zone"),
        ColorColumn(name="color", label="Color", editor=HexColorEditorFactory()),
        ObjectColumn(name="region_count", label="Regions", editable=False),
        GlyphActionColumn(
            name="id", label="", glyph=ICON_DELETE, fire="delete_requested"
        ),
    ],
    selected="selected_zone_type",
    selection_mode="row",
    sortable=False,
    auto_size=True,
)

zone_regions_table_editor = TableEditor(
    columns=[
        ObjectColumn(name="id", label="Region", editable=False),
        ObjectColumn(name="zone_id", label="Zone", editable=False),
        VisibleColumn(
            name="visible",
            label="",
            editable=False,
            horizontal_alignment="center",
        ),
    ],
    selected="selected_region",
    selection_mode="row",
    sortable=False,
    auto_size=True,
)

zones_view = View(
    VGroup(
        UItem("mode", style="custom", editor=zone_tool_editor),
        UItem("zone_types", editor=zone_types_table_editor),
        HGroup(
            UItem("new_zone_type_name", springy=True),
            UItem("add_zone_type_button", enabled_when="new_zone_type_name.strip()"),
        ),
        HGroup(
            UItem(
                "commit_button",
                enabled_when=(
                    f"mode == '{ZONE_DRAW_MODE}' and len(pending_electrode_ids) > 0"
                ),
            ),
            UItem(
                "clear_pending_button",
                enabled_when=(
                    "len(pending_electrode_ids) > 0 or editing_region is not None"
                ),
            ),
        ),
        UItem("regions", editor=zone_regions_table_editor),
        HGroup(
            UItem(
                "edit_region_button",
                enabled_when=(
                    f"mode == '{ZONE_SELECT_MODE}' and selected_region is not None"
                ),
            ),
            UItem("delete_region_button", enabled_when="selected_region is not None"),
            UItem("hide_region_button", enabled_when="selected_region is not None"),
            UItem(
                "merge_regions_button",
                enabled_when=(
                    f"mode == '{ZONE_SELECT_MODE}' and len(selected_regions) >= 2"
                ),
                tooltip="Merge the ctrl+click-selected regions",
            ),
        ),
        Item("show_canvas_overlays", label="Canvas buttons"),
    ),
    handler=SafeCancelTableHandler(),
)
