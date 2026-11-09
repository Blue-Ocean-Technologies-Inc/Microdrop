# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Frame rates of a Raspberry Pi CSI camera, from its sensor modes.

Qt's GStreamer backend reports a frame rate of 0 for every libcamera camera
format, and a libcamera camera has no ``/dev/videoN`` node for ``v4l2-ctl``
to query. libcamera serves each output size from one of the sensor's modes,
so the output runs at that mode's frame rate. The modes come from
``rpicam-hello --list-cameras``, else from KNOWN_SENSOR_MODES.
"""

# Standard library imports.
import re
import subprocess
from typing import NamedTuple

# Microdrop utils imports.
from microdrop_utils.libcamera_tuning import v4l2_subdevice_names

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class SensorMode(NamedTuple):
    """One sensor mode: its size in pixels and its maximum frame rate."""

    width: int
    height: int
    fps: float


#: The camera-listing binary, newest name first (``libcamera-hello`` is its
#: name before Raspberry Pi OS Bookworm).
LIST_CAMERAS_COMMANDS = (
    ("rpicam-hello", "--list-cameras"),
    ("libcamera-hello", "--list-cameras"),
)

#: Seconds to wait for a camera listing; it takes well under one.
LIST_CAMERAS_TIMEOUT_S = 5

#: A camera header: ``0 : imx708_noir [4608x2592 10-bit RGGB] (/base/...)``.
CAMERA_HEADER_RE = re.compile(r"^\s*\d+\s*:\s*(\S+)\s.*\((/[^)]*)\)\s*$")

#: A mode: ``1536x864 [120.13 fps - (768, 432)/3072x1728 crop]``.
SENSOR_MODE_RE = re.compile(
    r"(\d+)x(\d+)\s*\[\s*(\d+(?:\.\d+)?)\s*fps\s*-\s*"
    r"\((\d+),\s*(\d+)\)/(\d+)x(\d+)\s*crop\]"
)

#: A crop dimension libcamera only reports for a camera another process is
#: using; every mode then also claims the same placeholder frame rate.
BUSY_CAMERA_CROP_SIZE = 65535

#: Sensor modes by sensor name without its variant suffix (``imx708_noir``
#: and ``imx708_wide`` are ``imx708``). imx708: ``rpicam-hello
#: --list-cameras`` on a Pi 5 (libcamera 0.7.2); imx477 and imx219: the
#: listings in Raspberry Pi's camera software documentation.
KNOWN_SENSOR_MODES = {
    "imx708": [
        SensorMode(1536, 864, 120.13),
        SensorMode(2304, 1296, 56.03),
        SensorMode(4608, 2592, 14.35),
    ],
    "imx477": [
        SensorMode(1332, 990, 120.05),
        SensorMode(2028, 1080, 50.03),
        SensorMode(2028, 1520, 40.01),
        SensorMode(4056, 3040, 10.00),
    ],
    "imx219": [
        SensorMode(640, 480, 103.33),
        SensorMode(1640, 1232, 41.85),
        SensorMode(1920, 1080, 47.57),
        SensorMode(3280, 2464, 21.19),
    ],
}

#: The first usable listing this process read: modes are only reported
#: while the camera is free, and MicroDrop itself may hold it later on.
_cached_sensor_modes: dict[str, list[SensorMode]] = {}


def _mode_area(mode: SensorMode) -> tuple[int, int]:
    """Sort key ordering sensor modes from smallest to largest."""
    return mode.width * mode.height, mode.width


def parse_list_cameras(text: str) -> dict[str, list[SensorMode]]:
    """Each camera's sensor modes from ``rpicam-hello --list-cameras``
    output, keyed by libcamera camera id (its device-tree path) and sorted
    by area; a size listed for several bit depths keeps its fastest rate.

    Returns {} for unparseable output, and for the placeholder listing of a
    camera another process is using (a 65535 crop, or one frame rate across
    all modes).
    """
    modes_by_camera: dict[str, dict[tuple[int, int], float]] = {}
    camera_id = None

    for line in text.splitlines():
        header_match = CAMERA_HEADER_RE.match(line)

        if header_match:
            camera_id = header_match.group(2)
            modes_by_camera[camera_id] = {}
            continue

        mode_match = SENSOR_MODE_RE.search(line)

        if camera_id is None or mode_match is None:
            continue

        width, height = int(mode_match.group(1)), int(mode_match.group(2))
        fps = float(mode_match.group(3))
        crop = [int(value) for value in mode_match.group(4, 5, 6, 7)]

        if BUSY_CAMERA_CROP_SIZE in crop:
            logger.debug(f"Camera {camera_id} is in use; its sensor modes are unknown")

            return {}

        modes = modes_by_camera[camera_id]
        modes[(width, height)] = max(fps, modes.get((width, height), 0.0))

    sensor_modes = {}

    for camera_id, modes in modes_by_camera.items():
        if len(modes) > 1 and len(set(modes.values())) == 1:
            logger.debug(f"Camera {camera_id} lists one frame rate for every mode")

            return {}

        if modes:
            sensor_modes[camera_id] = sorted(
                (
                    SensorMode(width, height, fps)
                    for (width, height), fps in modes.items()
                ),
                key=_mode_area,
            )

    return sensor_modes


def read_sensor_modes() -> dict[str, list[SensorMode]]:
    """Each libcamera camera's sensor modes (see parse_list_cameras), or {}
    when no listing binary is installed or the listing is unusable.

    The first usable listing is kept for the rest of the process.
    """
    global _cached_sensor_modes

    if _cached_sensor_modes:
        return _cached_sensor_modes

    for command in LIST_CAMERAS_COMMANDS:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=LIST_CAMERAS_TIMEOUT_S,
            )
        except FileNotFoundError:
            continue
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.warning(f"Cannot list libcamera cameras with {command[0]}: {error}")

            return {}

        _cached_sensor_modes = parse_list_cameras(result.stdout)

        return _cached_sensor_modes

    return {}


def sensor_base_name(sensor_name: str) -> str:
    """A sensor name without its variant suffix: ``imx708_wide_noir`` is
    ``imx708``."""
    return sensor_name.split("_")[0].lower()


def libcamera_fps_for(width: int, height: int, modes: list[SensorMode]) -> float:
    """The frame rate libcamera delivers an output of ``width`` x
    ``height`` at: the rate of the smallest mode covering both dimensions,
    else of the largest mode; 0.0 without modes."""

    if not modes:
        return 0.0

    by_area = sorted(modes, key=_mode_area)

    for mode in by_area:
        if mode.width >= width and mode.height >= height:
            return mode.fps

    return by_area[-1].fps


def sensor_modes_for_device(camera_id: str) -> list[SensorMode]:
    """The sensor modes of the libcamera camera ``camera_id``: from its
    ``rpicam-hello`` listing, else KNOWN_SENSOR_MODES for its sensor; []
    when neither knows it.

    The sensor is named by the id's last node (``.../imx708@1a``) or else
    by a V4L2 sub-device.
    """
    listed_modes = read_sensor_modes().get(camera_id)

    if listed_modes:
        return listed_modes

    id_sensor_name = camera_id.rstrip("/").rsplit("/", 1)[-1].split("@")[0]

    for sensor_name in [id_sensor_name, *v4l2_subdevice_names()]:
        base_name = sensor_base_name(sensor_name)
        known_modes = KNOWN_SENSOR_MODES.get(base_name)

        if known_modes:
            logger.info(f"Using the known {base_name} sensor modes for {camera_id}")

            return known_modes

    return []
