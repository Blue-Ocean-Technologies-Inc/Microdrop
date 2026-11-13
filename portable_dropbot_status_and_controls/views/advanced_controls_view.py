# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Advanced Controls pane, unlocked only in Advanced Mode (Edit
menu): the power-system buzzer, and per-motor mechanical tuning.
Params workflow: Read → edit → Write (RAM only) → Preset to Flash →
Reboot Motor Board to make flashed params take effect (then Home All
from the motor panel)."""

# Enthought library imports.
from traitsui.api import HGroup, Item, Label, UItem, VGrid, VGroup, View

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import InPlaceToggleEditor

locked_hint = VGroup(
    Label("Enable Advanced Mode (Edit menu) to use the advanced controls."),
    visible_when="not advanced_mode",
)

buzzer = HGroup(
    UItem(
        "buzzer_state",
        editor=InPlaceToggleEditor(on_label="Buzzer On", off_label="Buzzer Off"),
    ),
    label="Buzzer",
    show_border=True,
)

#: Plain text fields on purpose: these are expert tuning values with
#: motor-specific magnitudes, so spinner steps would be arbitrary.
fields = VGrid(
    Item("nl_pos"),
    Item("pl_pos"),
    Item("round_len"),
    Item("origin_offset"),
    Item("origin_area"),
    Item("step_len"),
    Item("motor_polarity"),
    Item("I_hold"),
    Item("I_run"),
    Item("subdiv"),
    Item("run_sgt"),
    Item("rst_sgt"),
    Item("bspd"),
    Item("rspd"),
    Item("acc_run", visible_when="'acc_run' in loaded_fields"),
    Item("acc_rst", visible_when="'acc_rst' in loaded_fields"),
    enabled_when="params_loaded",
)

motor_params = VGroup(
    HGroup(
        Item("selected_motor", label="Motor"),
        UItem("read_button", tooltip="Read the selected motor's params from the board"),
        UItem(
            "write_button",
            enabled_when="params_loaded",
            tooltip="Send the edited params to the board's RAM; "
            "lost on reboot unless preset to flash",
        ),
        UItem(
            "preset_button",
            enabled_when="params_loaded",
            tooltip="Save the motor's current on-board params to "
            "flash so they survive a reboot",
        ),
        UItem(
            "reboot_button",
            tooltip="Reboot the motor board so flashed params take "
            "effect; run Home All afterwards",
        ),
    ),
    fields,
    Item("params_status", style="readonly", label="Status"),
    Label(
        "Write is RAM-only; Preset persists to flash; the board "
        "runs flashed params after a reboot. The pads lose homing "
        "across a reboot — Home All from the motor panel after."
    ),
    label="Motor Params",
    show_border=True,
)

controls = VGroup(
    buzzer,
    motor_params,
    visible_when="advanced_mode",
    enabled_when="connected",
)

AdvancedControlsView = View(
    VGroup(locked_hint, controls),
    resizable=True,
    scrollable=True,
)
