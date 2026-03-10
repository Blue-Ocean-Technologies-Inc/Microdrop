from traitsui.api import View, Item, UItem, HGroup, VGroup, Group, Spring, EnumEditor
from manual_controls.MVC import ToggleEditorFactory


mock_controls = VGroup(
    VGroup(
        Item("connection_status_text", style="readonly", label="Connection"),
        Item("chip_status_text", style="readonly", label="Chip"),
        Item("actuated_channels_text", style="readonly", label="Actuated"),
        UItem(
            "realtime_mode",
            style="custom",
            editor=ToggleEditorFactory(),
            enabled_when="connected",
        ),
        label="Status",
        show_border=True,
    ),
    VGroup(
        Item("capacitance_display", style="readonly", label="Capacitance"),
        Item("voltage_display", style="readonly", label="Voltage"),
        Item("frequency_display_text", style="readonly", label="Frequency"),
        label="Readings",
        show_border=True,
    ),
    VGroup(
        Item("base_capacitance_pf", label="Base (pF)"),
        Item("capacitance_delta_pf", label="Delta/electrode (pF)"),
        Item("capacitance_noise_pf", label="Noise (pF)"),
        Item("stream_interval_ms", label="Interval (ms)"),
        Item("stream_active", style="readonly", label="Streaming"),
        label="Capacitance Simulation",
        show_border=True,
    ),
    VGroup(
        UItem("simulate_chip_toggle"),
        HGroup(
            Item("shorts_channels_text", label="Channels"),
            UItem("simulate_shorts_button"),
        ),
        HGroup(
            Item("halt_error_type", label="Error Type",
                 editor=EnumEditor(values=["output-current-exceeded", "chip-load-saturated"])),
            UItem("simulate_halt_button"),
        ),
        label="Event Simulation",
        show_border=True,
    ),
)

MockDropbotView = View(
    mock_controls,
    resizable=True,
    width=350,
)
