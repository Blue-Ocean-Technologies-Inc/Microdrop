from PySide6.QtGui import QColor
from traitsui.api import (
    View, Item, UItem, HGroup, VGroup, EnumEditor, ListEditor, InstanceEditor,
)
from traitsui.item import UReadonly

from manual_controls.MVC import ToggleEditorFactory
from microdrop_style.colors import INFO_COLOR
from microdrop_utils.traitsui_qt_helpers import ToggleEditor

# Every section is collapsible: a checkbox acts as the section header and the
# bordered group below it is shown only while its `show_*` trait is ticked, so
# an unticked section collapses to just its checkbox.

# Connection / board identity.
status_group = VGroup(
    Item("connection_status_text", style="readonly", label="Connection"),
    Item("board_id_text", style="readonly", label="Board"),
    visible_when="show_status",
    show_border=True,
)

# Control: the PWM/Temp mode switch + streaming master gate, the channel
# selector, and the setpoint spinboxes for the selected heater.
control_group = VGroup(
    HGroup(
        # Toggle: PWM (open-loop duty, off) vs Temp (closed-loop PID, on).
        # Replaces the old PID on/off toggle — the backend enables PID iff Temp.
        UReadonly("mode"),
        UItem(
            "mode",
            label="Mode",
            editor=ToggleEditor(
                on_value="Temp",
                off_value="PWM",
                bar_color=INFO_COLOR,
                handle_color=QColor(INFO_COLOR).darker(),
            ),
            enabled_when="connected and not halted",
        ),
        UItem(
            "stream_active",
            style="custom",
            editor=ToggleEditorFactory(on_label="Stream On", off_label="Stream Off"),
            enabled_when="connected"
        ),
    ),
    Item(
        "selected_heater",
        label="Heater",
        editor=EnumEditor(name="object.available_heaters"),
    ),
    Item(
        "temperature",
        label="Set temperature",
        enabled_when="connected and not halted and mode == 'Temp'",
    ),
    Item(
        "pwm",
        label="Set PWM",
        enabled_when="connected and not halted and mode == 'PWM'",
    ),
    visible_when="show_control",
    show_border=True,
)

# One status row per heater. The display strings carry their own units (°C / %),
# so the row is label-free: "<name>  <temperature>  <pwm>".
heater_readout_row = View(
    HGroup(
        UItem("name", style="readonly"),
        UItem("temperature_display", style="readonly"),
        UItem("pwm_display", style="readonly"),
    )
)

readouts_group = VGroup(
    UItem(
        "heater_readouts",
        editor=ListEditor(
            style="custom",
            editor=InstanceEditor(view=heater_readout_row),
            mutable=False,
        ),
    ),
    visible_when="show_heater_status",
    show_border=True,
)

# Per-sensor temperature snapshot.
all_temps_group = VGroup(
    Item("all_temps_display", style="readonly", show_label=False),
    visible_when="show_all_temps",
    show_border=True,
)

UnifiedView = View(
    VGroup(
        Item("show_status", label="Status"),
        status_group,
        Item("show_control", label="Control"),
        control_group,
        Item("show_heater_status", label="Heater status"),
        readouts_group,
        Item("show_all_temps", label="Show all temperatures"),
        all_temps_group,
    ),
    resizable=True,
)
