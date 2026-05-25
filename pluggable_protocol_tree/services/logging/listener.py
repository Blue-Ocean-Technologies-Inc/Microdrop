"""Active-logger registry + dramatiq actor. The actor receives every
message on the logging topics and routes it to the controller that is
active for the current run (set in start_logging, cleared in
stop_logging). Mirrors execution/listener.py's active-step pattern."""

import threading

import dramatiq

from dropbot_controller.consts import CAPACITANCE_UPDATED
from device_viewer.consts import DEVICE_VIEWER_MEDIA_CAPTURED, CALIBRATION_DATA
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_CHANGE, LOGGING_LISTENER_NAME,
)
from logger.logger_service import get_logger

logger = get_logger(__name__)

_active = None
_lock = threading.Lock()


def set_active_logger(controller) -> None:
    """Register the controller that should receive logging messages for the current run."""
    global _active
    with _lock:
        _active = controller


def clear_active_logger() -> None:
    """Unregister the active logger (called when a run stops)."""
    global _active
    with _lock:
        _active = None


def get_active_logger():
    """Return the active logging controller, or None when no run is logging."""
    with _lock:
        return _active


def route_to_active_logger(topic: str, payload) -> None:
    sink = get_active_logger()
    if sink is None:
        return
    try:
        if topic == CAPACITANCE_UPDATED:
            sink.on_capacitance(payload)
        elif topic == ELECTRODES_STATE_CHANGE:
            sink.on_actuation(payload)
        elif topic == DEVICE_VIEWER_MEDIA_CAPTURED:
            sink.on_media(payload)
        elif topic == CALIBRATION_DATA:
            sink.on_calibration(payload)
    except Exception as e:                     # pragma: no cover - defensive
        logger.error(f"logging route failed for {topic}: {e}")


@dramatiq.actor(actor_name=LOGGING_LISTENER_NAME, queue_name="default")
def logging_listener(message: str, topic: str, timestamp: float = None) -> None:
    route_to_active_logger(topic, message)
