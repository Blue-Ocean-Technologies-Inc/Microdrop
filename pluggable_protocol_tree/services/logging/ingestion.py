"""Collects logged rows for one protocol run. No Qt, no broker — fed by
the ProtocolLoggingController. Append paths are lock-guarded because
capacitance/actuation arrive on a dramatiq worker thread while step
context updates arrive on the GUI thread."""

import json
import threading

from traits.api import Any, Dict, Float, HasTraits, Int, List, Str

from logger.logger_service import get_logger

logger = get_logger(__name__)


class LoggingIngestion(HasTraits):
    # Accumulated rows + the column order seen so far. Public — read by
    # LoggingPersistence / LoggingReport and the test contract.
    entries = List()
    columns = List()
    metadata = Dict()
    media = Dict()
    # Current step + phase context stamped onto each capacitance row.
    _step_id = Str("")
    _step_idx = Int(0)
    _actuated_channels = List()
    _actuated_area = Float(0.0)
    _cpa = Any()                     # Optional[float]; None -> force is None
    _lock = Any()                    # threading.Lock, set in traits_init

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

    def log_media(self, model) -> None:
        type_obj = getattr(model, "type", None)
        bucket = getattr(type_obj, "value", None) or type_obj or "other"
        bucket = str(bucket).lower()
        if bucket not in self.media:
            bucket = "other"
        with self._lock:
            self.media[bucket].append(str(model.path))

    def log_capacitance(self, message) -> bool:
        """Parse a CAPACITANCE_UPDATED payload and append one row stamped
        with the current step + current phase actuation. Returns False
        (skips) when no step is set yet or the payload is unparseable —
        matches legacy lenient behavior."""
        if not self._step_id:           # no step set yet -> skip (legacy parity)
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
        self.log_data({
            "step_idx": self._step_idx,
            "utc_time": int(data.get("reception_time", 0) or 0),
            "instrument_time_us": int(data.get("instrument_time_us", 0) or 0),
            "step_id": self._step_id,
            "Capacitance (pF)": cap,
            "Voltage (V)": volt,
            "Force Over Unit Area (mN/mm^2)": force,
            "Actuated Area (mm^2)": self._actuated_area,
            "actuated_channels": list(self._actuated_channels),
        })
        return True

    # --- force ---
    def _calculate_force(self, voltage: float):
        if self._cpa is None or voltage <= 0:
            return None
        try:
            return round(0.5 * self._cpa * (voltage ** 2), 6)
        except Exception as e:        # pragma: no cover - defensive
            logger.error(f"force calc failed: {e}")
            return None


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
