# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state for the PMT Capture pane: one row per configured spot
(capture tick, gain, exposure) in capture order, plus run state. Mutated
only on the GUI thread."""

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Range,
    Str,
)

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    DEFAULT_PMT_EXPOSURE_S,
    DEFAULT_PMT_GAIN,
    PMT_EXPOSURE_S_BOUNDS,
    PMT_GAIN_BOUNDS,
)
from template_status_and_controls.base_model import BaseStatusModel

# Local imports.
from ..consts import PORTABLE_DROPBOT_IMAGE


class PmtSpotRow(HasTraits):
    """One PMT motor slot as a table row."""

    #: Motor slot, 1-based — the identity of the row.
    slot = Int
    #: The slot's position on the PMT Y axis, from the board.
    position_um = Int
    #: Read-only ID column: "Spot 3 · 24.50 mm".
    label = Property(Str, observe="slot, position_um")
    capture = Bool(True)
    gain = Range(PMT_GAIN_BOUNDS[0], PMT_GAIN_BOUNDS[1], DEFAULT_PMT_GAIN)
    exposure_s = Range(
        PMT_EXPOSURE_S_BOUNDS[0], PMT_EXPOSURE_S_BOUNDS[1], DEFAULT_PMT_EXPOSURE_S
    )

    def _get_label(self):
        return f"Spot {self.slot} · {self.position_um / 1000:.2f} mm"


class PortableDropbotPmtCaptureModel(BaseStatusModel):
    """Spot rows in capture order plus the running capture's state."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    #: Table rows; list order is capture order.
    rows = List(Instance(PmtSpotRow))
    selected_row = Instance(PmtSpotRow)
    #: True between Start and the backend's done message.
    capturing = Bool(False)
    progress = Str("-", desc="Current stage / last outcome")
    results_directory = Str("", desc="Folder the last capture wrote to")

    start_button = Button("Start capture")
    abort_button = Button("Abort")
    refresh_button = Button("Refresh spots")

    def merge_spots(self, spots):
        """Adopt a fresh (slot, position_um) list without losing settings.

        Rows are keyed by slot: survivors keep their tick, gain, exposure and
        place in the order (position refreshed), new slots append in slot
        order with defaults, vanished slots drop.
        """
        incoming = dict(spots)
        kept = [row for row in self.rows if row.slot in incoming]
        for row in kept:
            row.position_um = incoming[row.slot]
        known = {row.slot for row in kept}
        new = [
            PmtSpotRow(slot=slot, position_um=position)
            for slot, position in sorted(incoming.items())
            if slot not in known
        ]
        self.rows = kept + new

    def capture_entries(self):
        """The ticked rows, in table order, as PmtCaptureEntry payloads."""
        return [
            {
                "slot": row.slot,
                "gain": int(row.gain),
                "exposure_s": float(row.exposure_s),
            }
            for row in self.rows
            if row.capture
        ]
