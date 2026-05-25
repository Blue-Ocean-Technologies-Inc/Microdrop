"""Collects logged rows for one protocol run. No Qt, no broker — fed by
the ProtocolLoggingController. Append paths are lock-guarded because
capacitance/actuation arrive on a dramatiq worker thread while step
context updates arrive on the GUI thread."""

import threading
import time
from typing import Dict, List, Optional

from logger.logger_service import get_logger

logger = get_logger(__name__)


class LoggingIngestion:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: List[dict] = []
        self._columns: List[str] = []
        self._metadata: Dict = {}
        self._media: Dict[str, List[str]] = {"video": [], "image": [], "other": []}
        # current step + phase context stamped onto each capacitance row
        self._step_id = ""
        self._step_idx = 0
        self._actuated_channels: List[int] = []
        self._actuated_area: float = 0.0
        self._cpa: Optional[float] = None

    # --- context setters ---
    def set_step(self, *, step_id: str, step_idx: int) -> None:
        self._step_id = step_id
        self._step_idx = step_idx

    def set_actuation(self, *, actuated_channels, actuated_area: float) -> None:
        self._actuated_channels = list(actuated_channels or [])
        self._actuated_area = float(actuated_area or 0.0)

    def update_capacitance_per_unit_area(self, value: Optional[float]) -> None:
        self._cpa = None if value is None else float(value)

    # --- collection ---
    def log_data(self, entry: dict) -> None:
        with self._lock:
            for k in entry:
                if k not in self._columns:
                    self._columns.append(k)
            self._entries.append(dict(entry))

    def log_metadata(self, entry: dict) -> None:
        with self._lock:
            self._metadata.update(entry)

    def log_media(self, model) -> None:
        bucket = getattr(getattr(model, "type", None), "value", "other")
        if bucket not in self._media:
            bucket = "other"
        with self._lock:
            self._media[bucket].append(str(model.path))

    # --- force ---
    def _calculate_force(self, voltage: float) -> Optional[float]:
        if self._cpa is None or voltage <= 0:
            return None
        try:
            return round(0.5 * self._cpa * (voltage ** 2), 6)
        except Exception as e:        # pragma: no cover - defensive
            logger.error(f"force calc failed: {e}")
            return None

    # --- accessors ---
    @property
    def entries(self) -> List[dict]:
        return self._entries

    @property
    def columns(self) -> List[str]:
        return self._columns

    @property
    def metadata(self) -> Dict:
        return self._metadata

    @property
    def media(self) -> Dict[str, List[str]]:
        return self._media
