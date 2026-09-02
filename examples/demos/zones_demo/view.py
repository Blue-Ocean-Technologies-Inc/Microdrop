# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI view for the electrode zones demo: the device canvas (the one
custom-Qt widget, embedded via CustomEditor) beside an all-TraitsUI sidebar."""

from pyface.qt.QtGui import QColor
from traitsui.api import (
    CustomEditor,
    EnumEditor,
    Group,
    HGroup,
    Item,
    TableEditor,
    UItem,
    VGroup,
    View,
)
from traitsui.qt.color_editor import ToolkitEditorFactory as QtColorEditorFactory

from microdrop_style.icons.icons import ICON_DELETE

from microdrop_utils.traitsui_qt_helpers import (
    ColorColumn,
    GlyphActionColumn,
    ObjectColumn,
    SafeCancelTableHandler,
    VisibleColumn,
)

from .canvas import zones_canvas_factory
from .consts import (
    EDIT_MODE,
    PAN_MODE,
    SELECT_MODE,
    SIDEBAR_WIDTH,
    ZONE_DRAW_MODE,
)


class HexColorEditorFactory(QtColorEditorFactory):
    """ColorEditor over a plain hex-string trait (e.g. Str("#f5e050")):
    the picker round-trips QColor <-> '#rrggbb' so Qt-free models can keep
    serializable hex strings instead of a toolkit Color trait."""

    def to_qt_color(self, editor):
        return QColor(getattr(editor.object, editor.name))

    def from_qt_color(self, color):
        return color.name()


zone_types_table_editor = TableEditor(
    columns=[
        ObjectColumn(name="id", label="Id", editable=False),
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

sidebar = VGroup(
    UItem("load_svg_button"),
    UItem(
        "mode",
        style="custom",
        editor=EnumEditor(
            values={
                PAN_MODE: "Pan",
                ZONE_DRAW_MODE: "Draw zones",
                SELECT_MODE: "Select",
                EDIT_MODE: "Edit",
            },
            cols=4,
        ),
    ),
    # Sidebar twins of the canvas overlays, gated to their modes; the
    # checkbox restores overlays dismissed via their canvas ⊗ button.
    HGroup(
        UItem(
            "commit_button",
            enabled_when=f"mode in ('{ZONE_DRAW_MODE}', '{EDIT_MODE}')",
        ),
        UItem(
            "clear_pending_button",
            enabled_when=f"mode in ('{ZONE_DRAW_MODE}', '{EDIT_MODE}')",
        ),
        UItem("undo_button", enabled_when="can_undo"),
        UItem("redo_button", enabled_when="can_redo"),
        Item("show_canvas_overlays", label="Canvas buttons"),
    ),
    UItem("zone_types", editor=zone_types_table_editor, width=SIDEBAR_WIDTH),
    HGroup(
        UItem("new_zone_type_name", springy=True),
        UItem("add_zone_type_button"),
    ),
    UItem("remove_zone_type_button"),
    Group(
        UItem("regions", editor=zone_regions_table_editor, width=SIDEBAR_WIDTH),
        HGroup(
            UItem("edit_region_button", enabled_when=f"mode == '{SELECT_MODE}'"),
            UItem("delete_region_button", enabled_when=f"mode == '{SELECT_MODE}'"),
            UItem("hide_region_button", enabled_when=f"mode == '{SELECT_MODE}'"),
            UItem(
                "merge_regions_button",
                tooltip="Merge the ctrl+click-selected regions",
                enabled_when=f"mode == '{SELECT_MODE}' and len(selected_regions) >= 2",
            ),
        ),
        label="Regions",
        show_border=True,
    ),
)

ZonesDemoView = View(
    HGroup(
        UItem("manager", editor=CustomEditor(zones_canvas_factory), springy=True),
        sidebar,
    ),
    title="Electrode Zones Demo",
    width=1100,
    height=650,
    resizable=True,
    handler=SafeCancelTableHandler(),
)
