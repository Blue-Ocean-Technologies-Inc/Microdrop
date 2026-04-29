"""Process-wide calibration cache + Dramatiq listener that updates it
from CALIBRATION_DATA messages.

The cache is a module-level singleton because every Force-column cell
in every protocol step reads from the same calibration values; cloning
state per row would force every subscriber to manage its own
synchronisation. See PPT-7 design (#369) for the locked rationale.
"""

import json
from typing import Optional

import dramatiq
from traits.api import Event, Float, HasTraits

from logger.logger_service import get_logger

from ..consts import CALIBRATION_LISTENER_ACTOR_NAME
from .force_math import capacitance_per_unit_area as _c_per_a


logger = get_logger(__name__)


class CalibrationCache(HasTraits):
    liquid_capacitance_over_area = Float(0.0)
    filler_capacitance_over_area = Float(0.0)
    cache_changed = Event

    def capacitance_per_unit_area(self) -> Optional[float]:
        return _c_per_a(
            self.liquid_capacitance_over_area,
            self.filler_capacitance_over_area,
        )


cache = CalibrationCache()


def _apply_calibration(message: str) -> None:
    # Lesson from #394: legacy _on_screen_recording_triggered crashed the
    # worker on bad JSON; guard the parse + key access here.
    try:
        payload = json.loads(message)
        liquid = float(payload["liquid_capacitance_over_area"])
        filler = float(payload["filler_capacitance_over_area"])
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "calibration_data_listener: rejecting malformed message %r (%s)",
            message, exc,
        )
        return

    cache.trait_set(
        liquid_capacitance_over_area=liquid,
        filler_capacitance_over_area=filler,
    )
    cache.cache_changed = True


@dramatiq.actor(actor_name=CALIBRATION_LISTENER_ACTOR_NAME, queue_name="default")
def _on_calibration(message: str, topic: str, timestamp: float = None):
    _apply_calibration(message)
