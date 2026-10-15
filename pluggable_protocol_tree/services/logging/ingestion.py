# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Collects logged rows for one protocol run. No Qt, no broker — fed by
the ProtocolLoggingController. Append paths are lock-guarded because
capacitance/actuation arrive on a dramatiq worker thread while step
context updates arrive on the GUI thread."""

# Standard library imports.
import json
import threading

# Enthought library imports.
from traits.api import Any, Bool, Dict, Float, HasTraits, Int, List, Str

# Microdrop package imports.
from pluggable_protocol_tree.services.logging.consts import (
    DIELECTRIC_THICKNESS_COLUMN,
    VACUUM_PERMITTIVITY_PF_UM_PER_MM2,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class LoggingIngestion(HasTraits):
    # Accumulated rows + the column order seen so far. Public — read by
    # LoggingPersistence / LoggingReport and the test contract.
    entries = List()
    columns = List()
    metadata = Dict()
    media = Dict()

    #: Filler calibration (pF/mm^2) subtracted from C/A for the thickness
    #: column; None keeps the raw C/A. Read at flush for the report footnote.
    filler_capacitance_per_unit_area = Any()

    #: True once the filler changed after a thickness row was logged, so
    #: earlier rows used a different correction.
    filler_changed_mid_run = Bool(False)

    # Current step + phase context stamped onto each capacitance row.
    _step_id = Str("")
    _step_idx = Int(0)
    _actuated_channels = List()
    _actuated_area = Float(0.0)
    _cpa = Any()  # Optional[float]; None -> force is None
    #: Relative permittivity of the run's dielectric (float or None). None
    #: leaves the dielectric-thickness column empty.
    _dielectric_constant = Any()
    _lock = Any()  # threading.Lock, set in traits_init

    def _media_default(self):
        return {"video": [], "image": [], "other": []}

    def traits_init(self):
        # Guards the cross-thread appends (dramatiq worker vs GUI thread).
        self._lock = threading.Lock()

    # --- context setters ---
    def set_step(self, *, step_id: str, step_idx: int) -> None:
        self._step_id = step_id
        self._step_idx = step_idx

    def set_actuation(self, *, actuated_channels, actuated_area: float) -> None:
        self._actuated_channels = list(actuated_channels or [])
        self._actuated_area = float(actuated_area or 0.0)

    def update_capacitance_per_unit_area(self, value) -> None:
        self._cpa = None if value is None else float(value)

    def update_dielectric_constant(self, value):
        self._dielectric_constant = None if value is None else float(value)

    def update_filler_capacitance_per_unit_area(self, value):
        filler = None if value is None else float(value)

        if (
            DIELECTRIC_THICKNESS_COLUMN in self.columns
            and filler != self.filler_capacitance_per_unit_area
        ):
            self.filler_changed_mid_run = True

        self.filler_capacitance_per_unit_area = filler

    # --- collection ---
    def log_data(self, entry: dict) -> None:
        with self._lock:
            for k in entry:
                if k not in self.columns:
                    self.columns.append(k)
            self.entries.append(dict(entry))

    def log_metadata(self, entry: dict) -> None:
        with self._lock:
            self.metadata.update(entry)

    def log_contributed_data(self, entry: dict) -> None:
        """Append a data row contributed by an external plugin (via the
        PROTOCOL_LOGGING_DATA_CONTRIBUTION topic). The current step context
        is stamped when the payload omits it, so contributed rows group
        under the step that was running when they arrived (step_idx 0 =
        before any step started)."""
        stamped = {"step_idx": self._step_idx, "step_id": self._step_id}
        stamped.update(entry)
        self.log_data(stamped)

    def log_media(self, model) -> None:
        type_obj = getattr(model, "type", None)
        bucket = getattr(type_obj, "value", None) or type_obj or "other"
        bucket = str(bucket).lower()

        if bucket not in self.media:
            bucket = "other"

        path = str(model.path)

        with self._lock:
            # The live DEVICE_VIEWER_MEDIA_CAPTURED path and the flush-time
            # app_globals drain both deliver the same file.
            if path not in self.media[bucket]:
                self.media[bucket].append(path)

    def log_capacitance(self, message) -> bool:
        """Parse a CAPACITANCE_UPDATED payload and append one row stamped
        with the current step + current phase actuation. Returns False
        (skips) when no step is set yet or the payload is unparseable —
        matches legacy lenient behavior."""
        if not self._step_id:  # no step set yet -> skip (legacy parity)
            return False
        try:
            data = json.loads(message)
        except (ValueError, TypeError):
            return False
        cap_str = data.get("capacitance", "-")
        volt_str = data.get("voltage", "-")
        if cap_str == "-" or volt_str == "-":
            return False
        cap = _parse_number(cap_str, "pF")
        volt = _parse_number(volt_str, "V")
        if cap is None or volt is None:
            return False
        force = self._calculate_force(volt)

        # Raw C/A over the actuated electrodes, not the liquid-minus-filler
        # calibration behind the force column. The thickness subtracts the
        # filler itself.
        capacitance_over_area = (
            cap / self._actuated_area if self._actuated_area > 0 else None
        )

        self.log_data(
            {
                "step_idx": self._step_idx,
                "utc_time": int(data.get("reception_time", 0) or 0),
                "instrument_time_us": int(data.get("instrument_time_us", 0) or 0),
                "step_id": self._step_id,
                "Capacitance (pF)": cap,
                "Voltage (V)": volt,
                "Force Over Unit Area (mN/mm^2)": force,
                "Actuated Area (mm^2)": self._actuated_area,
                "Capacitance Over Area (pF/mm^2)": capacitance_over_area,
                DIELECTRIC_THICKNESS_COLUMN: self._calculate_dielectric_thickness(
                    capacitance_over_area
                ),
                "actuated_channels": list(self._actuated_channels),
            }
        )
        return True

    # --- force ---
    def _calculate_force(self, voltage: float):
        if self._cpa is None or voltage <= 0:
            return None
        try:
            return round(0.5 * self._cpa * (voltage**2), 6)
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"force calc failed: {e}")
            return None

    # --- dielectric ---
    def _calculate_dielectric_thickness(self, capacitance_over_area):
        """Parallel-plate estimate d = eps_r * eps_0 / (C/A - filler), in um,
        or over the raw C/A when no filler calibration is known. Valid when
        the actuated electrodes are fully covered by liquid."""
        if self._dielectric_constant is None or capacitance_over_area is None:
            return None

        device_capacitance_over_area = capacitance_over_area

        if self.filler_capacitance_per_unit_area is not None:
            device_capacitance_over_area -= self.filler_capacitance_per_unit_area

        if device_capacitance_over_area <= 0:
            return None

        return (
            self._dielectric_constant
            * VACUUM_PERMITTIVITY_PF_UM_PER_MM2
            / device_capacitance_over_area
        )


def _parse_number(raw, unit: str):
    """Parse '12.5pF' / '12.5 pF' / '12.5' -> 12.5. Returns None on failure.

    Units must not be substrings of one another (ok for 'pF'/'V')."""
    try:
        s = str(raw)
        if unit in s:
            s = s.replace(unit, "").strip()
        return float(s)
    except (ValueError, TypeError):
        return None
