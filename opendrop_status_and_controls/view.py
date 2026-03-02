from dropbot_status_and_controls.view_helpers import StatusIconEditorFactory
from manual_controls.MVC import ToggleEditorFactory

from traitsui.api import View, Item, UItem, HGroup, VGroup, Spring, Label, Readonly

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
        VGroup(Readonly("connection_status_text", label="Connection"),
               Readonly("board_id")),
        VGroup(Label("Chip Status: See Instrument", enabled_when="False")),
        Spring("8"),
        UItem(
            "realtime_mode",
            style="custom",
            editor=ToggleEditorFactory(),
            enabled_when="connected",
        ),
        Spring("10"),
    ),
    id="status_controls",  # Unique identifier for layout saving
)

# 2. Add label, id, and dock='tab' to the grid group
middle = VGroup(
Spring("12"),
    Label("Voltage: On-Board", enabled_when="False"),
Label("Frequency: On-Board", enabled_when="False"),
Label("Capacitance: N/A", enabled_when="False"),
    id="data_grid",  # Unique identifier for layout saving
)

grid = VGroup(
    Readonly("temperature_1"),
    Readonly("temperature_2"),
    Readonly("temperature_3"),
    VGroup(Readonly("feedback_active_channels"),)
)

# 3. Wrap in a split layout and set a View ID
UnifiedView = View(
    HGroup(left, "15", middle, "15", grid),
    resizable=True,
)
