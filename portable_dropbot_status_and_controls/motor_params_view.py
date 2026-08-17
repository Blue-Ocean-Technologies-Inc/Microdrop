"""The motor-params pane: per-motor mechanical tuning, unlocked only
in Advanced Mode (Edit menu). Workflow: Read → edit → Write (RAM
only) → Preset to Flash → Reboot Motor Board to make flashed params
take effect (then Home All from the motor panel)."""
from traitsui.api import HGroup, Item, Label, UItem, VGrid, VGroup, View

locked_hint = VGroup(
    Label("Enable Advanced Mode (Edit menu) to edit motor params."),
    visible_when="not advanced_mode",
)

#: Plain text fields on purpose: these are expert tuning values with
#: motor-specific magnitudes, so spinner steps would be arbitrary.
fields = VGrid(
    Item("nl_pos"), Item("pl_pos"),
    Item("round_len"), Item("origin_offset"),
    Item("origin_area"), Item("step_len"),
    Item("motor_polarity"), Item("I_hold"),
    Item("I_run"), Item("subdiv"),
    Item("run_sgt"), Item("rst_sgt"),
    Item("bspd"), Item("rspd"),
    Item("acc_run",
         visible_when="'acc_run' in loaded_fields"),
    Item("acc_rst",
         visible_when="'acc_rst' in loaded_fields"),
    enabled_when="params_loaded",
)

controls = VGroup(
    HGroup(
        Item("selected_motor", label="Motor"),
        UItem("read_button"),
        UItem("write_button", enabled_when="params_loaded"),
        UItem("preset_button", enabled_when="params_loaded"),
        UItem("reboot_button"),
    ),
    fields,
    Item("params_status", style="readonly", label="Status"),
    Label("Write is RAM-only; Preset persists to flash; the board "
          "runs flashed params after a reboot. The pads lose homing "
          "across a reboot — Home All from the motor panel after."),
    visible_when="advanced_mode",
    enabled_when="connected",
)

MotorParamsView = View(
    VGroup(locked_hint, controls),
    resizable=True,
    scrollable=True,
)
