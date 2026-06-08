from traitsui.api import View, Item, UItem, HGroup, VGroup, Group, Spring, EnumEditor
from manual_controls.MVC import ToggleEditorFactory

# Each section is an independently collapsible panel: a header checkbox
# (the `show_*` model trait) toggles the `visible_when` on its content
# group, so any combination of sections can be expanded at once.
mock_controls = VGroup(
    VGroup(
        Item("show_status", label="Status"),
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
            visible_when="show_status",
        ),
        show_border=True,
        springy=True,
    ),
    VGroup(
        Item("show_readings", label="Readings"),
        VGroup(
            Item("capacitance_display", style="readonly", label="Capacitance"),
            Item("voltage_display", style="readonly", label="Voltage"),
            Item("frequency_display_text", style="readonly", label="Frequency"),
            visible_when="show_readings",
        ),
        show_border=True,
    ),
    VGroup(
        Item("show_capacitance_sim", label="Capacitance Simulation"),
        VGroup(
            Item("base_capacitance_pf", label="Base (pF)"),
            Item("capacitance_delta_pf", label="Delta/electrode (pF)"),
            Item("capacitance_noise_pf", label="Noise (pF)"),
            Item("stream_interval_ms", label="Interval (ms)"),
            Item("stream_active", style="readonly", label="Streaming"),
            visible_when="show_capacitance_sim",
        ),
        show_border=True,
        springy=True,

    ),
    VGroup(
        Item("show_event_sim", label="Event Simulation"),
        VGroup(
            HGroup(
                UItem("simulate_connect_button"),
                UItem("simulate_disconnect_button"),
            ),
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
            visible_when="show_event_sim",
        ),
        show_border=True,
        springy=True,
    ),
    springy=True,
    scrollable=True,
)

MockDropbotView = View(
    mock_controls,
)

if __name__ == "__main__":
    from mock_dropbot_status.model import MockDropbotStatusModel
    from mock_dropbot_status.controller import MockDropbotDockPaneController

    model = MockDropbotStatusModel()
    view = MockDropbotView
    controller = MockDropbotDockPaneController(model)
    view.handler = controller

    model.configure_traits(view=view)



