"""TraitsUI view for the Configure Sensors & Heaters dialog.

Scan the bus / refresh from board, edit sensor names + heater assignments, then
Save to file or Save & push to board.
"""
from traitsui.api import (
    View, UItem, VGroup, Tabbed, TableEditor, Action, OKButton,
)

from microdrop_utils.traitsui_qt_helpers import ObjectColumn, HtmlLabelEditor

# All three top labels render as word-wrapped rich text (HtmlLabelEditor), so a
# long help line wraps instead of forcing the pane wide.
help_label = HtmlLabelEditor()  # plain, word-wrapped
# Muted, italic styling for the secondary/reference labels. ``{}`` is the value.
_MUTED = "color:#888; font-style:italic;"
source_label = HtmlLabelEditor(
    template=f'<span style="{_MUTED}">Config source: {{}}</span>')
available_label = HtmlLabelEditor(
    template=f'<span style="{_MUTED}">Available sensors: {{}}</span>')
push_status_label = HtmlLabelEditor(template=f'<span style="{_MUTED}">{{}}</span>')

# The Name (sensors) and Sensors (heater assignments) columns are editable; the
# ROM / Status / Heater / Type columns are read-only.
sensors_table = TableEditor(
    columns=[
        ObjectColumn(name="rom", label="ROM (hex)", editable=False),
        ObjectColumn(name="name", label="Name", editable=True),
        ObjectColumn(name="status", label="Status", editable=False),
    ],
    editable=True,
    sortable=False,
    auto_size=False,
)

heaters_table = TableEditor(
    columns=[
        ObjectColumn(name="heater", label="Heater", editable=False),
        ObjectColumn(name="type", label="Type", editable=False),
        ObjectColumn(name="sensors", label="Sensors (comma-separated)", editable=True),
    ],
    editable=True,
    sortable=False,
    auto_size=False,
)

scan_action = Action(name="Scan for sensors", action="scan_sensors")
refresh_action = Action(name="Refresh from board", action="refresh_from_board")
save_action = Action(name="Save to file", action="save_to_file")
push_action = Action(name="Save && push to board", action="save_and_push")

SensorConfigView = View(
    VGroup(
        UItem("help_text", editor=help_label),
        UItem("source", editor=source_label),
        Tabbed(
            UItem("sensors", editor=sensors_table, label="Sensors"),
            VGroup(
                UItem("heater_assignments", editor=heaters_table),
                UItem("available_sensor_names", editor=available_label),
                label="Heater Assignments",
            ),
        ),
        UItem("push_status", editor=push_status_label,
              visible_when="push_status"),
    ),
    title="Configure Sensors && Heaters",
    width=640,
    height=480,
    resizable=True,
    buttons=[scan_action, refresh_action, save_action, push_action, OKButton],
    kind="live",
)
