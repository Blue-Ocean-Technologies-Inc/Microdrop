# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Fill Pattern dialog: pick a column, Ramp or Alternate, and the
pattern's values; the summary line previews what OK will do, and OK stays
disabled while the inputs are invalid. The electrodes column alternates
channel entries, typed or picked on a picture of the device."""

# Enthought library imports.
from traitsui.api import Action, Handler, Item, VGroup, View

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import error, information
from pluggable_protocol_tree.models.channel_picker_model import ChannelPickerModel
from pluggable_protocol_tree.services.device_electrodes import (
    active_device_svg_path,
    load_device_electrodes,
)
from pluggable_protocol_tree.services.step_pattern import (
    format_channel_entries,
    parse_channel_entries,
)

# Local imports.
from .channel_picker_view import channel_picker_view

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class StepPatternHandler(Handler):
    """Opens the channel picker for the model's Pick on device… button."""

    def object_pick_channels_changed(self, info):
        model = info.object
        parent = info.ui.control
        svg_path = active_device_svg_path()

        if not svg_path:
            information(
                parent=parent,
                title="Pick channels",
                message="No device SVG is loaded.",
                cancel=False,
            )

            return

        try:
            electrodes = load_device_electrodes(svg_path)
        except Exception as exc:
            logger.error(f"Could not read device SVG {svg_path}: {exc}")
            error(
                parent=parent,
                title="Pick channels",
                message=f"Could not read the device SVG: {exc}",
            )

            return

        # The protocol's channel map wins over the SVG's own, so the picture
        # agrees with how typed channels resolve.
        electrode_channels = {
            electrode_id: model.electrode_channels.get(electrode_id, electrode.channel)
            for electrode_id, electrode in electrodes.items()
        }

        try:
            entries = parse_channel_entries(model.alternate_text)
        except ValueError:
            entries = []

        picker = ChannelPickerModel(
            entries=entries,
            electrode_channels=electrode_channels,
            electrode_paths={
                electrode_id: electrode.path
                for electrode_id, electrode in electrodes.items()
            },
        )
        ui = picker.edit_traits(view=channel_picker_view, parent=parent)

        if ui.result:
            model.alternate_text = format_channel_entries(picker.entries)


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
        visible_when="not is_channels",
    ),
    Item(
        "alternate_text",
        label="Channels",
        tooltip=(
            "Channel entries to cycle across the steps, one per step, separated "
            "by ';' — e.g. 1 2 3; 4 5 6. An empty entry actuates nothing."
        ),
        visible_when="is_channels",
    ),
    Item("pick_channels", show_label=False, visible_when="is_channels"),
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
        Item("mode", label="Pattern", style="custom", visible_when="len(modes) > 1"),
        ramp,
        alternate,
        grouping,
        Item("_"),
        Item("summary", style="readonly", show_label=False),
    ),
    title="Fill Pattern",
    handler=StepPatternHandler(),
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
            PatternField(
                col_id="electrodes", label="Electrodes (channels)", is_channels=True
            ),
        ],
        current_values={
            "target_temperature_c": [50.0],
            "voltage": [100],
            "electrodes": [["e1", "e2"]],
        },
        electrode_channels={"e1": 1, "e2": 1, "e3": 2, "e4": 3},
        fit_count=1,
    ).configure_traits(view=step_pattern_view)
