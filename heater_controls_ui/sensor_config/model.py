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


def _reconcile(existing, desired, key, factory, update):
    """Return rows for ``desired`` (list of field dicts), reusing the matching
    ``existing`` row object by ``key`` and updating its ``update`` traits in place
    (so the table cells repaint), and building missing rows via ``factory(**d)``.
    Rows for vanished keys are dropped."""
    by_key = {getattr(row, key): row for row in existing}
    rows = []
    for fields in desired:
        row = by_key.get(fields[key])
        if row is None:
            rows.append(factory(**fields))
        else:
            for trait in update:
                if getattr(row, trait) != fields[trait]:
                    setattr(row, trait, fields[trait])
            rows.append(row)
    return rows


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
        """Reload from a ``dump_config`` JSON document (a "refresh from board"):
        update the table values in place, overwriting any unsaved edits. Returns
        True if the text parsed."""
        config = parse_board_config(config_text)
        if config is None:
            return False
        self.config = config
        self.source = "Live from board (dump_config)."
        # A fresh config from the board invalidates the previous scan: like the
        # old UI, every sensor reverts to "In config" until the bus is rescanned.
        self.scanned_roms = []
        self.scan_done = False
        self._rebuild_rows(update_names=True)
        return True

    def set_scanned_roms(self, roms):
        """Record the ROMs found by the last bus scan and refresh the rows' status
        in place — sensor names being edited are preserved across a scan."""
        self.scanned_roms = [str(r) for r in (roms or [])]
        self.scan_done = True
        self._rebuild_rows(update_names=False)

    # ------------------------------------------------------------------ #
    @observe("sensors:items:name, sensors, config")
    def _update_available_names(self, event=None):
        names = [r.name.strip() for r in self.sensors if r.name.strip()]
        names += thermistor_names(self.config)
        self.available_sensor_names = ", ".join(names) if names else "(none)"

    def _rebuild_rows(self, update_names=True):
        """Reconcile the table rows against the current config/scan, reusing the
        existing row objects (keyed by ROM / heater) and updating their traits in
        place. In-place updates are what make a refresh/scan actually repaint the
        table (replacing the whole list from a background thread did not), and
        they let a scan keep in-progress name edits (``update_names=False``)."""
        self.sensors = _reconcile(
            self.sensors, sensor_rows(self.config, self.scanned_roms, self.scan_done),
            key="rom", factory=SensorRow,
            update=("name", "status") if update_names else ("status",))
        self.heater_assignments = _reconcile(
            self.heater_assignments, heater_rows(self.config),
            key="heater", factory=HeaterAssignmentRow,
            update=("type", "sensors") if update_names else ("type",))
