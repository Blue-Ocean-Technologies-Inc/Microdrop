# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The camera panel's image controls: one slider row per control the
selected camera has (exposure, brightness, contrast, ...), with its value in
real units where the raw value does not say it (exposure), an Auto toggle
where the control has an automatic mode, and a Defaults button.

Views a CameraModel; the camera controller observes the edits and writes
them to the camera."""

# Enthought library imports.
from traitsui.api import (
    HGroup,
    InstanceEditor,
    Item,
    ListEditor,
    RangeEditor,
    UItem,
    VGroup,
    View,
    spring,
)

#: One control's row; the fixed-width name lines the sliders up.
image_setting_row_view = View(
    HGroup(
        UItem("label", style="readonly", width=-90),
        UItem(
            "value",
            editor=RangeEditor(low_name="low", high_name="high", mode="slider"),
            enabled_when="not auto",
            springy=True,
        ),
        UItem("value_text", style="readonly", visible_when="value_text"),
        Item("auto", label="Auto", visible_when="has_auto"),
    ),
)

camera_image_settings_view = View(
    VGroup(
        UItem(
            "image_settings",
            # Not scrollable: the sidebar scrolls, and a nested scroll area
            # would squeeze the rows to a sliver.
            editor=ListEditor(
                style="custom",
                mutable=False,
                scrollable=False,
                editor=InstanceEditor(view=image_setting_row_view),
            ),
        ),
        HGroup(spring, UItem("reset_image_settings")),
        visible_when="image_settings",
    ),
    # Resizable, or TraitsUI fixes the panel at its build-time size: the
    # rows come and go with the selected camera.
    resizable=True,
)
