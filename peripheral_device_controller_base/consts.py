"""Topic/key factory helpers shared by all peripheral-device backends.

Every concrete device backend (the z-stage magnet, the heater, ...) follows the
same MQTT-style topic scheme keyed off a human-readable ``device_name``
(e.g. ``"ZStage"``, ``"Heater"``). These helpers build the canonical strings so
the base classes and the per-device ``consts.py`` modules stay in sync.
"""

# Subtopics whose requests are processed even while the device is disconnected.
# Everything else under ``<device>/requests/`` is gated on an active connection.
DEFAULT_ALWAYS_ALLOWED_SUBTOPICS = ["start_device_monitoring", "retry_connection"]

# Firmware upload/cancel are always-allowed too, on the devices that offer
# them: flashing IS the recovery path for a board whose firmware can't
# connect, and the upload service releases the proxy (disconnecting) before it
# flashes. An upload-capable controller extends its _always_allowed_subtopics
# with these (see PeripheralFirmwareUploadService).
FIRMWARE_UPLOAD_ALWAYS_ALLOWED_SUBTOPICS = [
    "upload_firmware", "cancel_firmware_upload",
]


def upload_firmware_topic(device_name: str) -> str:
    """Request: flash the board's firmware (UploadFirmwareData payload)."""
    return f"{device_name}/requests/upload_firmware"


def cancel_firmware_upload_topic(device_name: str) -> str:
    """Request: abort the running firmware upload."""
    return f"{device_name}/requests/cancel_firmware_upload"


def firmware_upload_started_topic(device_name: str) -> str:
    """Signal: an upload was accepted and started (drives the dialog's
    uploading state); the message is a human-readable run description."""
    return f"{device_name}/signals/firmware_upload_started"


def firmware_upload_log_topic(device_name: str) -> str:
    """Signal: one uploader progress line per message."""
    return f"{device_name}/signals/firmware_upload_log"


def firmware_upload_finished_topic(device_name: str) -> str:
    """Signal: upload outcome — JSON {"success": bool}, or {"error": str} on
    an uploader crash."""
    return f"{device_name}/signals/firmware_upload_finished"


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
