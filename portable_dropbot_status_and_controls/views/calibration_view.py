# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The calibration pane: the vendor's validated ML calibration macro
front and center, with the ML-path toggle and the gain / cal-caps
provisioning below it."""
from traitsui.api import HGroup, Item, Label, UItem, VGroup, View

from microdrop_utils.traitsui_qt_helpers import InPlaceToggleEditor

macro = VGroup(
    Label("clear → release pogos → 100 V/10 kHz → HV bypass → "
          "re-clear → multi-slope fit (~6 s) → HV off → restore V/F "
          "→ press pogos"),
    HGroup(
        UItem("run_calibration_button"),
        Item("calibration_status", style="readonly", label="Status"),
    ),
    label="ML Calibration Macro",
    show_border=True,
    enabled_when="connected and not protocol_running",
)

ml_path = VGroup(
    UItem("ml_realtime",
          style="custom",
          editor=InPlaceToggleEditor(on_label="ML Path On",
                                     off_label="ML Path Off")),
    label="ML Measurement Path",
    show_border=True,
    enabled_when="connected",
)

gain = VGroup(
    HGroup(
        Item("electrode_gain", label="Permille"),
        UItem("read_gain_button"),
        UItem("apply_gain_button"),
    ),
    label="Electrode Gain",
    show_border=True,
    enabled_when="connected",
)

cal_caps = VGroup(
    HGroup(
        Item("cal_caps", label="Reference Caps"),
        UItem("read_cal_caps_button"),
        UItem("apply_cal_caps_button"),
    ),
    label="Reference-Cap Count",
    show_border=True,
    enabled_when="connected",
)

CalibrationView = View(
    VGroup(macro, ml_path, gain, cal_caps),
    resizable=True,
    scrollable=True,
)
