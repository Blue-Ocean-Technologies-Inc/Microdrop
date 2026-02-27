from dropbot_status_and_controls.consts import PKG_name
from dropbot_status_and_controls.view_helpers import StatusIconEditorFactory
from manual_controls.MVC import ToggleEditorFactory

from traitsui.api import View, Item, UItem, HGroup, VGroup, Spring, VGrid, HSplit

# 1. Add label, id, and dock='tab' to the left group
left = HGroup(
    Item(
        "icon_path",
        editor=StatusIconEditorFactory(),
        show_label=False,
    ),
    Spring("8"),
    VGroup(
        Spring("8"),
        VGroup(
            Item("connection_status_text", style="readonly", label="Connection"),
            Item("chip_status_text", style="readonly", label="Chip Status"),
        ),
        Spring("25"),
        UItem(
            "realtime_mode",
            style="custom",
            editor=ToggleEditorFactory(),
            enabled_when="connected",
        ),
    ),
    label="Controls",    # Gives the dock pane a title
    id="left_controls",  # Unique identifier for layout saving
)

# 2. Add label, id, and dock='tab' to the grid group
grid = VGrid(
    Item("voltage_readback_display", style="readonly", label="Voltage"),
    UItem("voltage", label="Voltage"),
    Item("frequency", label="Frequency", style="readonly"),
    UItem("frequency", label="Frequency"),
    Item("capacitance_display", style="readonly", label="  Capacitance"),
    UItem(""),
    Item("pressure_display", style="readonly", label="c_device"),
    UItem(""),
    Item("force_display", style="readonly", label="Force"),
    UItem(""),
    label="Data Grid",   # Gives the dock pane a title
    id="grid_data",      # Unique identifier for layout saving
)

# 3. Wrap in a split layout and set a View ID
UnifiedView = View(
    HSplit(
        left,
        grid,),
    resizable=True,
)