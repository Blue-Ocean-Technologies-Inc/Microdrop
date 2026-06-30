"""Topic/key factory helpers shared by all peripheral-device backends.

Every concrete device backend (the z-stage magnet, the heater, ...) follows the
same MQTT-style topic scheme keyed off a human-readable ``device_name``
(e.g. ``"ZStage"``, ``"Heater"``). These helpers build the canonical strings so
the base classes and the per-device ``consts.py`` modules stay in sync.
"""

# Subtopics whose requests are processed even while the device is disconnected.
# Everything else under ``<device>/requests/`` is gated on an active connection.
DEFAULT_ALWAYS_ALLOWED_SUBTOPICS = ["start_device_monitoring", "retry_connection"]


def connected_topic(device_name: str) -> str:
    return f"{device_name}/signals/connected"


def disconnected_topic(device_name: str) -> str:
    return f"{device_name}/signals/disconnected"


def searching_topic(device_name: str) -> str:
    """Signal carrying this device's connection-search state (JSON bool): True
    while the monitor thread is actively scanning for the device, False once it
    connects or stops."""
    return f"{device_name}/signals/searching"


def connection_state_key(device_name: str) -> str:
    """app_globals key mirroring this device's connection state, keyed by device
    name so distinct peripherals don't collide."""
    return f"{device_name}.connection_active"
