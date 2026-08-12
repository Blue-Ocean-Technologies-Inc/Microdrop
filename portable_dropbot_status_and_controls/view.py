from traitsui.api import (
    HGroup, Item, Readonly, Spring, UItem, VGroup, View,
)

from microdrop_utils.traitsui_qt_helpers import (
    InPlaceToggleEditor, StatusIconEditorFactory,
)

left = HGroup(
    Item("icon_path", editor=StatusIconEditorFactory(),
         show_label=False),
    Spring("8"),
    VGroup(
        Spring("12"),
        VGroup(Readonly("connection_status_text", label="Connection"),
               Readonly("chip_status_text", label="Chip")),
        Spring("8"),
        UItem(
            "realtime_mode",
            style="custom",
            editor=InPlaceToggleEditor(on_label="Realtime On",
                                       off_label="Realtime Off"),
            enabled_when="connected and not protocol_running",
        ),
        Spring("10"),
    ),
    id="status_controls",
)

middle = VGroup(
    Spring("12"),
    Item("voltage", label="Voltage (V)",
         enabled_when="connected and free_mode and not protocol_running"),
    Item("frequency", label="Frequency (Hz)",
         enabled_when="connected and free_mode and not protocol_running"),
    Readonly("hv_readback_display", label="HV readback"),
    Readonly("capacitance_display", label="Capacitance"),
    id="data_grid",
)

right = VGroup(
    Spring("12"),
    Readonly("temperature_display", label="Temperature"),
    Readonly("mechanisms_display", label="Mechanisms"),
    Readonly("last_alarm", label="Last alarm"),
)

UnifiedView = View(
    HGroup(left, "15", middle, "15", right),
    resizable=True,
)
