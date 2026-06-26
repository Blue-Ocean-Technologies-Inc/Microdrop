from traitsui.api import View, Item, UItem, HGroup, VGroup, VGrid, Spring, EnumEditor

from manual_controls.MVC import ToggleEditorFactory

# Left column: status readouts + realtime-style toggle buttons + momentary
# buttons. No device picture (unlike the DropBot pane).
left = VGroup(
    VGroup(
        Item("connection_status_text", style="readonly", label="Connection"),
        Item("board_id_text", style="readonly", label="Board"),
    ),
    Spring("12"),
    VGroup(
        UItem(
            "pid_active", style="custom",
            editor=ToggleEditorFactory(on_label="PID On", off_label="PID Off"),
            enabled_when="connected and not halted",
        ),
        UItem(
            "stream_active", style="custom",
            editor=ToggleEditorFactory(on_label="Stream On", off_label="Stream Off"),
            enabled_when="connected",
        ),
        UItem(
            "fan_active", style="custom",
            editor=ToggleEditorFactory(on_label="Fan On", off_label="Fan Off"),
            enabled_when="connected",
        ),
        Spring("8"),
        HGroup(
            UItem("pid_stop", enabled_when="connected"),
            UItem("all_off", enabled_when="connected"),
        ),
    ),
    id="status_controls",
)

# Right column: heater selector + setpoint spinboxes paired with their readback
# display labels (same shape as the DropBot voltage/frequency grid).
grid = VGrid(
    Item("selected_heater", label="Heater",
         editor=EnumEditor(name="object.available_heaters")),
    UItem(""),
    Item("temperature_display", style="readonly", label="Temperature"),
    UItem("temperature", enabled_when="connected and not halted"),
    Item("pwm_display", style="readonly", label="PWM"),
    UItem("pwm", enabled_when="connected and not halted"),
    id="data_grid",
)

UnifiedView = View(
    HGroup(left, "15", grid),
    resizable=True,
)
