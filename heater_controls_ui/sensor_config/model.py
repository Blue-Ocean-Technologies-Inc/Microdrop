"""Qt-free model for the Configure Sensors & Heaters editor.

The message handler feeds it the board's ``dump_config`` document and scan
results (via :mod:`.parsing`); the view renders the two row lists as tables.
"""
from traits.api import Str, Bool, List, HasTraits, Instance, Dict, observe

from .parsing import parse_board_config, sensor_rows, heater_rows


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

    # Where the displayed config came from, shown under the help text.
    source = Str("No config loaded yet.")

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

    def _rebuild_rows(self):
        self.sensors = [SensorRow(**r) for r in
                        sensor_rows(self.config, self.scanned_roms, self.scan_done)]
        self.heater_assignments = [HeaterAssignmentRow(**r) for r in
                                   heater_rows(self.config)]
