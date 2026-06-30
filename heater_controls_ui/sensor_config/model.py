"""Qt-free model for the Configure Sensors & Heaters editor.

The message handler feeds it the board's ``dump_config`` document and scan
results (via :mod:`.parsing`); the view renders the two row lists as tables.
"""
from traits.api import Str, Bool, List, HasTraits, Instance, Dict, observe

from .parsing import parse_board_config, sensor_rows, heater_rows, thermistor_names

# Instructional copy shown at the top of the dialog (rendered word-wrapped so a
# long sentence doesn't force the pane wide).
HELP_TEXT = (
    "Scan the 1-Wire bus, name sensors, and assign them to heaters. The config "
    "is pulled live from the connected board. Edit the Name and Sensors columns, "
    "then Save to file."
)


class SensorRow(HasTraits):
    """One 1-Wire sensor: its ROM id, the name it's given, and a status derived
    from whether it's in the config and/or seen on the last bus scan."""
    rom = Str()
    name = Str()
    status = Str()


class HeaterAssignmentRow(HasTraits):
    """One heater channel and the sensors assigned to it (comma-separated)."""
    heater = Str()
    type = Str()
    sensors = Str()


class SensorConfigModel(HasTraits):
    """Holds the current board config + scan results as table rows.

    Phase 1 is read-only (display + scan/refresh). Editing, validation, and
    saving come in later phases.
    """
    # Raw board config (last dump_config), kept for re-deriving rows on scan.
    config = Dict()
    scanned_roms = List(Str)
    scan_done = Bool(False)

    sensors = List(Instance(SensorRow))
    heater_assignments = List(Instance(HeaterAssignmentRow))

    # Instructional text + where the displayed config came from (shown at top).
    help_text = Str(HELP_TEXT)
    source = Str("No config loaded yet.")

    # Reference list (shown under the Heater Assignments table): every name that
    # can be typed into a heater's Sensors cell — the current 1-Wire sensor names
    # plus the thermistor names. Updates live as sensor names are edited.
    available_sensor_names = Str("(none)")

    # Result of the last "Save & push to board" (set by the message handler from
    # the CONFIG_PUSHED signal); shown at the bottom of the dialog.
    push_status = Str("")

    def load_config_text(self, config_text):
        """Replace the config from a ``dump_config`` JSON document, then rebuild
        the rows. Returns True if the text parsed."""
        config = parse_board_config(config_text)
        if config is None:
            return False
        self.config = config
        self.source = "Live from board (dump_config)."
        self._rebuild_rows()
        return True

    def set_scanned_roms(self, roms):
        """Record the ROMs found by the last bus scan and rebuild the rows."""
        self.scanned_roms = [str(r) for r in (roms or [])]
        self.scan_done = True
        self._rebuild_rows()

    # ------------------------------------------------------------------ #
    @observe("config")
    def _on_config_changed(self, event):
        self._rebuild_rows()

    @observe("sensors:items:name, sensors, config")
    def _update_available_names(self, event=None):
        names = [r.name.strip() for r in self.sensors if r.name.strip()]
        names += thermistor_names(self.config)
        self.available_sensor_names = ", ".join(names) if names else "(none)"

    def _rebuild_rows(self):
        self.sensors = [SensorRow(**r) for r in
                        sensor_rows(self.config, self.scanned_roms, self.scan_done)]
        self.heater_assignments = [HeaterAssignmentRow(**r) for r in
                                   heater_rows(self.config)]
