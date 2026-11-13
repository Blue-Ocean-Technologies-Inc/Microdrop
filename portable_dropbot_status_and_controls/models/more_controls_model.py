# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from traits.api import Bool, Button, Float, Instance, Int, List, Range, Str, observe

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    DEFAULT_PMT_GAIN,
    PMT_GAIN_BOUNDS,
    TEMP_CHANNEL_MAX,
    TEMP_PID_GAIN_BOUNDS,
    TEMP_PID_PERIOD_MS_BOUNDS,
    TEMP_TARGET_C_BOUNDS,
)
from template_status_and_controls.base_model import BaseStatusModel

# Local imports.
from ..consts import (
    DEFAULT_GAIN_PRESETS,
    DEFAULT_TEMPERATURE_PRESETS,
    PORTABLE_DROPBOT_IMAGE,
)
from ..preferences import PortableDropbotSettingsPreferences
from .presets import parse_presets


class PortableDropbotMoreControlsModel(BaseStatusModel):
    """Qt-free state for the More Controls pane, one chevron-collapsed
    group per subsystem: per-channel heater control with PID tuning, and
    the PMT power/gain (the live stream and buffered acquire live in the
    PMT Capture pane). The everyday lighting controls live in the status
    pane. Mutated only on the GUI thread."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- Chevron-collapsed group toggles -----------------------------
    show_temperature = Bool(True)
    show_pmt = Bool(False)

    # ---- Temperature control (per channel) ---------------------------
    temp_channel = Range(0, TEMP_CHANNEL_MAX, 0, mode="spinner", desc="Heater channel")
    temp_target_c = Range(
        *TEMP_TARGET_C_BOUNDS, 37.0, desc="Heater target temperature (°C)"
    )
    set_target_button = Button("Set Target")
    #: Target quick picks (°C), from the Portable DropBot Settings
    #: preferences; a tap sets that target at once.
    temperature_presets = List(Float)
    #: Requested heater-control state for the selected channel; the
    #: board does not report a per-channel on/off, so the toggle shows
    #: what was last asked for.
    temp_control_on = Bool()
    read_info_button = Button("Read")
    temp_info_display = Str("-", desc="Last per-channel reading")

    # ---- PID tuning (chevron-collapsed) ------------------------------
    show_pid = Bool(False)
    pid_kp = Range(*TEMP_PID_GAIN_BOUNDS, 0.0, desc="Heater PID proportional gain")
    pid_ki = Range(*TEMP_PID_GAIN_BOUNDS, 0.0, desc="Heater PID integral gain")
    pid_kd = Range(*TEMP_PID_GAIN_BOUNDS, 0.0, desc="Heater PID derivative gain")
    pid_period_ms = Range(
        *TEMP_PID_PERIOD_MS_BOUNDS,
        1000,
        mode="spinner",
        desc="Heater PID control period (ms)",
    )
    read_pid_button = Button("Read PID")
    apply_pid_button = Button("Apply PID")

    # ---- PMT ---------------------------------------------------------
    #: Mirrors the actual PMT power state the backend reports; a click
    #: that contradicts it is the user's request.
    pmt_power = Bool(False)
    pmt_gain = Range(
        *PMT_GAIN_BOUNDS,
        DEFAULT_PMT_GAIN,
        mode="spinner",
        desc="PMT gain (MCP41010 wiper position)",
    )
    set_gain_button = Button("Set Gain")
    #: Gain quick picks, from the Portable DropBot Settings preferences;
    #: a tap sets that gain at once.
    gain_presets = List(Int)

    #: Settings the preset lists are parsed from; the dock pane binds it
    #: to the application's node, so applied edits reach a running pane.
    preferences = Instance(PortableDropbotSettingsPreferences)

    def _temperature_presets_default(self):
        return parse_presets(
            DEFAULT_TEMPERATURE_PRESETS, *TEMP_TARGET_C_BOUNDS, decimals=1
        )

    def _gain_presets_default(self):
        return parse_presets(DEFAULT_GAIN_PRESETS, *PMT_GAIN_BOUNDS)

    @observe("preferences, preferences:temperature_presets")
    def _parse_temperature_presets(self, event):
        if self.preferences is None:
            return

        self.temperature_presets = parse_presets(
            self.preferences.temperature_presets, *TEMP_TARGET_C_BOUNDS, decimals=1
        )

    @observe("preferences, preferences:gain_presets")
    def _parse_gain_presets(self, event):
        if self.preferences is None:
            return

        self.gain_presets = parse_presets(
            self.preferences.gain_presets, *PMT_GAIN_BOUNDS
        )
