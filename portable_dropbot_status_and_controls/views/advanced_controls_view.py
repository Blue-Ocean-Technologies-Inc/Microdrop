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
menu): the power-system buzzer, and per-motor mechanical tuning laid
out like the vendor UI's Motor Params tab. Params workflow: Read →
edit → Write (RAM; live on the motor's next idle moment, lost on
reboot) → Preset to Flash. A motor-board reboot is only needed for
boot-only settings: the board re-runs its boot homing after it."""

# Enthought library imports.
from traitsui.api import HGroup, Item, Label, TextEditor, UItem, VGrid, VGroup, View

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import InPlaceToggleEditor

locked_hint = VGroup(
    Label("Enable Advanced Mode (Edit menu) to use the advanced controls."),
    visible_when="not advanced_mode",
)

#: The home direction / polarity pairing confirm fires once per finished
#: edit (Enter or focus out), not per keystroke.
_home_pair_editor = TextEditor(auto_set=False, enter_set=True, evaluate=int)

buzzer = HGroup(
    UItem(
        "buzzer_state",
        editor=InPlaceToggleEditor(on_label="Buzzer On", off_label="Buzzer Off"),
    ),
    label="Buzzer",
    show_border=True,
)


#: Plain text fields on purpose: these are expert tuning values with
#: motor-specific magnitudes, so spinner steps would be arbitrary. Row
#: labels are the vendor UI's; the full description is each tooltip. The
#: fields older firmware does not serve are hidden.
fields = VGrid(
    Item("nl_pos", label="Neg. limit (µm)"),
    Item("pl_pos", label="Pos. limit (µm)"),
    Item("round_len", label="Lead / rev (µm)"),
    Item("origin_offset", label="Home offset (µm)"),
    Item("origin_area", label="Home flag (µm)"),
    Item("step_len", label="Step (µm/µstep)"),
    Item("motor_polarity", label="Direction (1=wired)", editor=_home_pair_editor),
    Item("I_hold", label="Hold current (0-31)"),
    Item("I_run", label="Run current (0-31)"),
    Item("subdiv", label="Microsteps"),
    Item("run_sgt", label="StallGuard, run"),
    Item("rst_sgt", label="StallGuard, home"),
    Item("bspd", label="Home speed (real µm/s)"),
    Item("rspd", label="Run speed (real µm/s)"),
    Item("acc_run", label="Accel, run", visible_when="'acc_run' in loaded_fields"),
    Item("acc_rst", label="Accel, home", visible_when="'acc_rst' in loaded_fields"),
    Item(
        "stealthchop",
        label="StealthChop (0/1)",
        visible_when="'stealthchop' in loaded_fields",
    ),
    Item(
        "home_dir",
        label="Home direction (0/1)",
        visible_when="'home_dir' in loaded_fields",
        editor=_home_pair_editor,
    ),
    enabled_when="params_loaded",
)

motor_params = VGroup(
    HGroup(
        Item("selected_motor", label="Motor"),
        UItem("read_button", tooltip="Read the selected motor's params from the board"),
        UItem(
            "write_button",
            enabled_when="params_loaded",
            tooltip="Send the edited params to the board's RAM: they apply "
            "on the motor's next idle moment and are lost on reboot unless "
            "preset to flash",
        ),
        UItem(
            "preset_button",
            enabled_when="params_loaded",
            tooltip="Save the motor's current on-board params to "
            "flash so they survive a reboot",
        ),
        UItem(
            "reboot_button",
            tooltip="Soft-reset the motor board, only needed for boot-only "
            "settings; it re-runs boot homing (all axes move)",
        ),
    ),
    fields,
    Item("params_layout", style="readonly", label="Board"),
    Item("params_status", style="readonly", label="Status"),
    Label(
        "Write is RAM-only and applies live; Preset persists to flash. "
        "Home direction and polarity change together, and a new home "
        "direction un-homes the axis — re-home it after the write."
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
