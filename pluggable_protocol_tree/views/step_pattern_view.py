# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Fill Pattern dialog: pick a numeric column, Ramp or Alternate, and
the pattern's values; the summary line previews what OK will do, and OK
stays disabled while the inputs are invalid."""

# Enthought library imports.
from traitsui.api import Action, Item, VGroup, View

ramp = VGroup(
    Item("start", label="From"),
    Item("stop", label="To"),
    Item("increment", label="Increment", enabled_when="not is_fit"),
    Item(
        "fitted_increment",
        label="Increment (fitted)",
        style="readonly",
        format_str="%g",
        visible_when="is_fit",
    ),
    label="Ramp",
    show_border=True,
    visible_when="mode == 'Ramp'",
)

alternate = VGroup(
    Item(
        "alternate_text",
        label="Values",
        tooltip="Values to cycle across the steps, e.g. 50, 80",
    ),
    Item("create_count", label="New steps", visible_when="not is_fit"),
    label="Alternate",
    show_border=True,
    visible_when="mode == 'Alternate'",
)

#: Create mode only — fitting edits existing steps, so there is nothing to group.
grouping = VGroup(
    Item("create_in_group", label="Create steps in a new group"),
    Item("group_name", label="Group name", enabled_when="create_in_group"),
    visible_when="not is_fit",
)

step_pattern_view = View(
    VGroup(
        Item("field_label", label="Column"),
        Item("mode", label="Pattern", style="custom"),
        ramp,
        alternate,
        grouping,
        Item("_"),
        Item("summary", style="readonly", show_label=False),
    ),
    title="Fill Pattern",
    buttons=[Action(name="OK", enabled_when="is_valid"), "Cancel"],
    kind="livemodal",
    resizable=True,
    width=420,
)


if __name__ == "__main__":
    # Standalone prototyping: the view against nothing but its model.
    from pluggable_protocol_tree.models.step_pattern_model import StepPatternModel
    from pluggable_protocol_tree.services.step_pattern import PatternField

    StepPatternModel(
        fields=[
            PatternField(col_id="target_temperature_c", label="Target Temp (°C)"),
            PatternField(col_id="voltage", label="Voltage (V)", is_int=True),
        ],
        current_values={"target_temperature_c": [50.0], "voltage": [100]},
        fit_count=1,
    ).configure_traits(view=step_pattern_view)
