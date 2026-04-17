from dropbot_status_and_controls.consts import DIELECTRIC_MATERIALS
from microdrop_utils.traitsui_qt_helpers import StatusIconEditorFactory, HoverScrollEnumEditor
from manual_controls.MVC import ToggleEditorFactory

from traitsui.api import View, Item, UItem, HGroup, VGroup, Spring, VGrid

# 1. Add label, id, and dock='tab' to the left group
left = HGroup(
    Item(
        "icon_path",
        editor=StatusIconEditorFactory(),
        show_label=False,
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
            enabled_when="connected and not halted and not protocol_running",
        ),
        Spring("10"),
    ),
    id="status_controls",  # Unique identifier for layout saving
)

# 2. Add label, id, and dock='tab' to the grid group
grid = VGrid(
    Item("voltage_readback_display", style="readonly", label="Voltage"),
    UItem("voltage", enabled_when="free_mode and not protocol_running and not halted"),
    Item("frequency_display", label="Frequency", style="readonly"),
    UItem("frequency", enabled_when="free_mode and not protocol_running and not halted"),
    Item("capacitance_display", style="readonly", label="Capacitance"),
    UItem(""),
    Item("c_device_display", style="readonly", label="c_device"),
    UItem(""),
    Item("force_display", style="readonly", label="Force"),
    UItem(""),
    Item("dielectric_thickness_display", style="readonly", label="Dielectric", visible_when="show_dielectric_info"),
    UItem(
        "dielectric_material",
        editor=HoverScrollEnumEditor(
            values=list(DIELECTRIC_MATERIALS.keys()),
        ),
        visible_when="show_dielectric_info",
    ),
    id="data_grid",  # Unique identifier for layout saving
)

# 3. Wrap in a split layout and set a View ID
UnifiedView = View(
    HGroup(left, "15", grid,),
    resizable=True,
)