# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Save Current Layout dialog: name the preset; OK stays disabled while
the name breaks the naming rule, whose reason shows below the field."""

# Enthought library imports.
from traitsui.api import Action, Item, VGroup, View

# Local imports.
from ..consts import SAVE_LAYOUT_PRESET_DIALOG_TITLE

preset_name_view = View(
    VGroup(
        Item("name", label="Preset name"),
        Item("name_error", style="readonly", show_label=False),
    ),
    title=SAVE_LAYOUT_PRESET_DIALOG_TITLE,
    buttons=[Action(name="OK", enabled_when="is_name_valid"), "Cancel"],
    kind="livemodal",
    resizable=True,
    width=360,
)


if __name__ == "__main__":
    # Standalone prototyping: the view against nothing but its model.
    from layout_presets.models.preset_name_model import PresetName

    PresetName(name="preset-1").configure_traits(view=preset_name_view)
