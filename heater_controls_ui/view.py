from traitsui.api import View, Item, VGroup, HGroup, EnumEditor

# TraitsUI view for HeaterControlModel. The heater dropdown is dynamic: its
# values come from the ``available_heaters`` trait (updated live by the listener),
# the same EnumEditor(name=...) pattern the motor-control pane uses.
heater_view = View(
    VGroup(
        # 1. Heater channel selector
        VGroup(
            Item(
                "selected_heater",
                label="Heater",
                editor=EnumEditor(name="object.available_heaters"),
            ),
            show_border=True,
            label="Channel",
            enabled_when="connected",
        ),
        # 2. Set values
        VGroup(
            HGroup(
                Item("temperature", label="Temp (°C)"),
                Item("apply_temperature", show_label=False, springy=False),
            ),
            HGroup(
                Item("pwm", label="PWM (%)"),
                Item("apply_pwm", show_label=False, springy=False),
            ),
            show_border=True,
            label="Set Values",
            enabled_when="connected",
        ),
        # 3. Controls
        VGroup(
            HGroup(
                Item("pid_enable", show_label=False, springy=False),
                Item("pid_disable", show_label=False, springy=False),
                Item("pid_stop", show_label=False, springy=False),
            ),
            HGroup(
                Item("stream_start", show_label=False, springy=False),
                Item("stream_stop", show_label=False, springy=False),
            ),
            HGroup(
                Item("fan_on", show_label=False, springy=False),
                Item("fan_off", show_label=False, springy=False),
                Item("all_off", show_label=False, springy=False),
            ),
            show_border=True,
            label="Controls",
            enabled_when="connected",
        ),
        # 4. Status readouts
        VGroup(
            Item("status_text", style="readonly", show_label=False),
            Item("board_id_text", style="readonly", show_label=False),
            Item("pid_temp_text", style="readonly", show_label=False),
            Item("pwm_text", style="readonly", show_label=False),
            Item("temps_text", style="readonly", show_label=False),
            HGroup(
                Item("connect", show_label=False, springy=False,
                     enabled_when="not connected"),
            ),
            show_border=True,
            label="Status",
        ),
    ),
    resizable=True,
)
