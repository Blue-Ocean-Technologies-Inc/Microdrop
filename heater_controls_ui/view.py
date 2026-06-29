from traitsui.api import View, Item, UItem, HGroup, VGroup, VGrid, EnumEditor

from manual_controls.MVC import ToggleEditorFactory

# Status readouts.
status_group = VGroup(
    Item("connection_status_text", style="readonly", label="Connection"),
    Item("board_id_text", style="readonly", label="Board"),
    show_border=True,
    label="Status",
)

# Channel selector + setpoint spinboxes paired with their readback labels.
# A 2-column grid keeps the labels / values aligned in tidy rows.
control_group = VGroup(
    VGrid(
        Item("selected_heater", label="Heater",
             editor=EnumEditor(name="object.available_heaters")),
        UItem(""),
        Item("temperature_display", style="readonly", label="Temperature"),
        UItem("temperature", enabled_when="connected and not halted and mode == 'Temp'"),
        Item("pwm_display", style="readonly", label="PWM"),
        UItem("pwm", enabled_when="connected and not halted and mode == 'PWM'"),
        columns=2,
    ),
    HGroup(
        # Radio: PWM (open-loop duty) vs Temp (closed-loop PID). Replaces the
        # old PID on/off toggle — the backend enables PID iff Temp is selected.
        Item(
            "mode", style="custom", label="Mode",
            editor=EnumEditor(cols=2),
            enabled_when="connected and not halted",
        ),
        UItem(
            "stream_active", style="custom",
            editor=ToggleEditorFactory(on_label="Stream On", off_label="Stream Off"),
            enabled_when="connected",
        ),
    ),
    show_border=True,
    label="Control",
)

# Per-sensor temperature snapshot — hidden until the checkbox is ticked.
all_temps_group = VGroup(
    Item("show_all_temps", label="Show all temperatures"),
    Item("all_temps_display", style="readonly", show_label=False,
         visible_when="show_all_temps"),
    show_border=True,
)

UnifiedView = View(
    VGroup(status_group, control_group, all_temps_group),
    resizable=True,
)
