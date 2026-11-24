# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The heater auto-tune group, embedded in the More Controls pane's heater
controls (it tunes and verifies the selected channel); standalone-
instantiable as ``HeaterTuneModel().edit_traits(view=HeaterTuneView)``."""

# Enthought library imports.
from traitsui.api import HGroup, InstanceEditor, Item, UItem, VGroup, View

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    HEATER_TUNE_MAX_TEMP_C_BOUNDS,
    HEATER_TUNE_VERIFY_DEFAULT_BAND_C,
    HEATER_TUNE_VERIFY_DEFAULT_HOLD_S,
    HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS,
)

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import DoubleSpinBoxEditor

# Local imports.
from .heater_tune_plot_view import HeaterTunePlotView

HeaterTuneView = View(
    VGroup(
        VGroup(
            Item("duty_pct", label="Step duty (%)"),
            Item(
                "max_temp_c",
                label="Max temp (°C)",
                editor=DoubleSpinBoxEditor(
                    low=HEATER_TUNE_MAX_TEMP_C_BOUNDS[0],
                    high=HEATER_TUNE_MAX_TEMP_C_BOUNDS[1],
                    decimals=1,
                    step=1.0,
                ),
            ),
            Item("max_duration_s", label="Time limit (s)"),
            enabled_when="not running",
        ),
        HGroup(
            UItem(
                "start_button",
                enabled_when="not running",
                tooltip="Step capture on the selected channel: 10 s baseline, "
                "the duty step, then the heater off for 30 s. Both heaters must "
                "be off",
            ),
            UItem(
                "cancel_button",
                enabled_when="running",
                tooltip="Stop the capture or verify run; the heater is switched off",
            ),
        ),
        Item("status", style="readonly", label="Status"),
        UItem("plot", style="custom", editor=InstanceEditor(view=HeaterTunePlotView)),
        Item("fit_display", style="readonly", label="Fit"),
        Item("style", label="Style"),
        Item("proposal_display", style="readonly", label="Proposed"),
        Item("notes_display", style="readonly", label="Notes"),
        HGroup(
            Item("persist", label="Persist to flash"),
            UItem(
                "apply_button",
                enabled_when="can_apply",
                tooltip="Write the proposed gains and Smith model to the "
                "fitted channel (asks first)",
            ),
        ),
        HGroup(
            Item(
                "verify_setpoint_c",
                label="Verify set point (°C)",
                editor=DoubleSpinBoxEditor(
                    low=HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS[0],
                    high=HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS[1],
                    decimals=1,
                    step=0.5,
                ),
                enabled_when="not running",
            ),
            UItem(
                "verify_button",
                enabled_when="not running",
                tooltip="Regulate the selected channel to the set point with the "
                "gains on the board, under the maximum temperature and time "
                "limit above, until it holds the set point "
                f"±{HEATER_TUNE_VERIFY_DEFAULT_BAND_C:g} °C for "
                f"{HEATER_TUNE_VERIFY_DEFAULT_HOLD_S} s. Both heaters must be off",
            ),
        ),
        Item("verify_display", style="readonly", label="Verify"),
    ),
)
