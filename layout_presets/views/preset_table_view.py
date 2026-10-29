# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Manage Layout Presets dialog: every saved preset in a table, its
shortcut editable in place and any collision shown beside it. Deleting a
row only stages it; nothing changes on disk until OK."""

# Enthought library imports.
from traitsui.api import HGroup, TableEditor, UItem, VGroup, View, spring

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import KeySequenceEditor, ObjectColumn

# Local imports.
from ..consts import MANAGE_LAYOUT_PRESETS_DIALOG_TITLE

presets_table = TableEditor(
    columns=[
        ObjectColumn(name="name", label="Preset", editable=False),
        ObjectColumn(
            name="shortcut",
            label="Shortcut",
            editor=KeySequenceEditor(),
            tooltip="Double-click and press the keys; clear for none",
        ),
        ObjectColumn(name="warning", label="Warning", editable=False),
    ],
    selected="selected",
    sortable=False,
    deletable=False,
)

preset_table_view = View(
    VGroup(
        UItem("rows", editor=presets_table),
        HGroup(
            spring,
            UItem("delete_button", enabled_when="selected is not None"),
        ),
    ),
    title=MANAGE_LAYOUT_PRESETS_DIALOG_TITLE,
    buttons=["OK", "Cancel"],
    kind="livemodal",
    resizable=True,
    width=560,
    height=320,
)


if __name__ == "__main__":
    # Standalone prototyping: the view against nothing but its model.
    from layout_presets.models.preset_table_model import PresetRow, PresetTable

    PresetTable(
        rows=[
            PresetRow(name="wide", shortcut="Alt+1", saved_shortcut="Alt+1"),
            PresetRow(name="tall", shortcut="Ctrl+R"),
        ],
        used_shortcuts={"Ctrl+R": "Reset Layout"},
    ).configure_traits(view=preset_table_view)
