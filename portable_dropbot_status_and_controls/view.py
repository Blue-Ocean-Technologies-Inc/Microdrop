from manual_controls.MVC import ToggleEditorFactory

from traitsui.api import View, Item, UItem, HGroup, VGroup, VGrid, Spring

from .view_helpers import ClickableStatusIconEditorFactory

# Left panel: clickable status icon + connection info + realtime toggle
left = HGroup(
    Item(
        "icon_path",
        editor=ClickableStatusIconEditorFactory(),
        show_label=False,
        # enabled_when="connected",
    ),
    Spring("8"),
    VGroup(
        Spring("12"),
        VGroup(
            Item("connection_status_text", style="readonly", label="Connection"),
            Item("chip_status_text", style="readonly", label="Chip Status"),
        ),
        Spring("22"),
        UItem(
            "realtime_mode",
            style="custom",
            editor=ToggleEditorFactory(),
            # enabled_when="connected",
        ),
        Spring("10"),
    ),
    id="status_controls",
)

# Right panel: readonly sensor readings grid
grid = VGrid(
    Item("voltage_readback_display", style="readonly", label="Voltage"),
    UItem("voltage", label="Voltage", enabled_when="free_mode and not protocol_running"),
    Item("frequency_display", label="Frequency", style="readonly"),
    UItem("frequency", label="Frequency", enabled_when="free_mode and not protocol_running"),
    Item("zstage_position_display", style="readonly", label="Magnet Height"),
    UItem(""),
    Item("device_temp_display", style="readonly", label="Device Temp"),
    UItem(""),
    Item("device_humidity_display", style="readonly", label="Device Humidity"),
    UItem(""),
    Item("chip_temp_display", style="readonly", label="Chip Temp"),
    UItem(""),
    id="data_grid",
)

UnifiedView = View(
    HGroup(left, "15", grid),
    resizable=True,
)
