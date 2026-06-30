"""TraitsUI view for the Configure Sensors & Heaters dialog.

Phase 1: read-only display of the two tables (Sensors / Heater Assignments)
plus "Scan for sensors" and "Refresh from board" actions. Editing, validation,
saving, and push-to-board come in later phases.
"""
from traitsui.api import (
    View, UItem, VGroup, Tabbed, Label, TableEditor, Action, OKButton,
)

from microdrop_utils.traitsui_qt_helpers import ObjectColumn

HELP_TEXT = (
    "Scan the 1-Wire bus, name sensors, and assign them to heaters. The config "
    "is pulled live from the connected board. Edit the Name and Sensors columns, "
    "then Save to file."
)

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

SensorConfigView = View(
    VGroup(
        Label(HELP_TEXT),
        UItem("source", style="readonly"),
        Tabbed(
            UItem("sensors", editor=sensors_table, label="Sensors"),
            UItem("heater_assignments", editor=heaters_table, label="Heater Assignments"),
        ),
    ),
    title="Configure Sensors && Heaters",
    width=640,
    height=480,
    resizable=True,
    buttons=[scan_action, refresh_action, save_action, OKButton],
    kind="live",
)
