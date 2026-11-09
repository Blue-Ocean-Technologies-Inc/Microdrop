# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import argparse
import glob
import platform
import re
import subprocess

# Enthought library imports.
from pyface.qt.QtMultimedia import QCameraDevice, QMediaDevices

# Microdrop utils imports.
from microdrop_utils.libcamera_sensor_modes import (
    libcamera_fps_for,
    sensor_modes_for_device,
)
from microdrop_utils.libcamera_tuning import read_lens_map

os_name = platform.system()

V4L2_FOCUS_ABSOLUTE = "focus_absolute"
V4L2_FOCUS_AUTO = "focus_automatic_continuous"
#: UVC auto-exposure menu: 1 = manual, 3 = aperture priority (auto time).
V4L2_EXPOSURE_AUTO = "auto_exposure"
V4L2_EXPOSURE_AUTO_MANUAL = 1
V4L2_EXPOSURE_AUTO_ON = 3

#: Raspberry Pi ISP, CSI-receiver and codec nodes. V4L2 lists them as video
#: devices (and Qt's GStreamer backend as cameras), but they yield no usable
#: image — a Pi CSI camera is reached through libcamera instead.
PI_INTERNAL_VIDEO_NODE_NAMES = (
    "rp1-cfe",
    "unicam",
    "pispbe",
    "bcm2835-isp",
    "bcm2835-codec",
    "rpivid",
    "hevc",
)

#: libcamera camera ids, which Qt also reports as their description, are
#: device-tree paths (e.g. "/base/axi/pcie@1000120000/rp1/i2c@80000/imx708@1a").
LIBCAMERA_ID_PREFIX = "/base/"

#: V4L2 sub-device nodes; a Pi CSI camera's lens (VCM) is one of these.
V4L2_SUBDEVICE_GLOB = "/dev/v4l-subdev*"


def get_v4l2_fps(
    device_path: str, width: int, height: int, pixel_format: str = "JPEG"
) -> list[float]:
    """
    Finds the supported FPS for a V4L2 device node at a given resolution and
    pixel format.

    Args:
        device_path: Device node path (e.g. ``"/dev/video0"``).
        width: Resolution width (e.g. 1920).
        height: Resolution height (e.g. 1080).
        pixel_format: Pixel format to match (default ``"JPEG"``).
                      Common values: ``"JPEG"``, ``"MJPG"``, ``"YUYV"``,
                      ``"NV12"``, ``"H264"``. Use ``"*"`` to match all formats.
    """
    print(f"Querying formats for {device_path}...")

    # Query the device's supported formats and frame sizes
    try:
        format_process = subprocess.run(
            ["v4l2-ctl", f"--device={device_path}", "--list-formats-ext"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        print("Error: v4l2-utils is not installed. Run: sudo apt install v4l-utils")
        return []
    except subprocess.CalledProcessError as e:
        print(f"Failed to query device {device_path}: {e}")
        return []

    # State machine to parse v4l2-ctl output
    in_format_section = False
    in_target_resolution = False
    supported_fps = []
    match_all = pixel_format == "*"

    target_res_string = f"{width}x{height}"

    for line in format_process.stdout.splitlines():
        # Check if we are entering a new format block
        if line.strip().startswith("["):
            in_format_section = match_all or pixel_format.upper() in line.upper()
            in_target_resolution = False  # Reset resolution state on new format
            continue

        if in_format_section:
            # Check if we hit our target resolution
            if "Size: Discrete" in line:
                in_target_resolution = target_res_string in line

            # If we are in the right format AND right resolution, extract the FPS
            elif in_target_resolution and "Interval:" in line:
                # Regex to extract the FPS number from "(30.000 fps)"
                match = re.search(r"\((\d+\.\d+)\s*fps\)", line)
                if match:
                    fps_val = float(match.group(1))
                    supported_fps.append(fps_val)

    return supported_fps


def get_v4l2_all_fps(
    device_path: str, pixel_format: str = "JPEG"
) -> dict[tuple[int, int], list[float]]:
    """Query all supported resolutions and their fps values for a V4L2 device.

    Args:
        device_path: Device node path (e.g. ``"/dev/video0"``).
        pixel_format: Pixel format to filter by (default ``"JPEG"``).
                      Use ``"*"`` to match all formats.

    Returns:
        Dict mapping ``(width, height)`` to a list of supported fps values,
        e.g. ``{(1920, 1080): [30.0, 15.0], (3840, 2160): [5.0]}``.
    """
    try:
        result = subprocess.run(
            ["v4l2-ctl", f"--device={device_path}", "--list-formats-ext"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}

    fps_map: dict[tuple[int, int], list[float]] = {}
    in_format_section = False
    current_res = None
    match_all = pixel_format == "*"

    size_re = re.compile(r"Size:\s+\w+\s+(\d+)x(\d+)")
    fps_re = re.compile(r"\((\d+(?:\.\d+)?)\s*fps\)")

    for line in result.stdout.splitlines():
        if line.strip().startswith("["):
            in_format_section = match_all or pixel_format.upper() in line.upper()
            current_res = None
            continue

        if not in_format_section:
            continue

        size_match = size_re.search(line)
        if size_match:
            current_res = (int(size_match.group(1)), int(size_match.group(2)))
            if current_res not in fps_map:
                fps_map[current_res] = []
            continue

        if current_res is not None:
            fps_match = fps_re.search(line)
            if fps_match:
                fps_map[current_res].append(float(fps_match.group(1)))

    return fps_map


def parse_v4l2_control_range(
    list_ctrls_output: str, name: str
) -> tuple[int, int] | None:
    """Extract a control's (min, max) from ``v4l2-ctl --list-ctrls`` text.

    Args:
        list_ctrls_output: Full stdout of ``v4l2-ctl --list-ctrls``.
        name: Control name to find (e.g. ``"focus_absolute"``).

    Returns:
        ``(min, max)`` for the matching control line, or ``None`` if the
        control is not present.
    """
    for line in list_ctrls_output.splitlines():
        stripped = line.strip()
        if not stripped.startswith(f"{name} "):
            continue

        min_match = re.search(r"\bmin=(-?\d+)", stripped)
        max_match = re.search(r"\bmax=(-?\d+)", stripped)
        if min_match and max_match:
            return int(min_match.group(1)), int(max_match.group(1))

    return None


def parse_v4l2_control_value(list_ctrls_output: str, name: str) -> int | None:
    """Extract a control's current value from ``v4l2-ctl --list-ctrls`` text.

    Returns ``None`` if the control is not present, so this doubles as a
    presence check for controls without a range (e.g. ``(bool)`` ones).
    """
    for line in list_ctrls_output.splitlines():
        stripped = line.strip()

        if not stripped.startswith(f"{name} "):
            continue

        value_match = re.search(r"\bvalue=(-?\d+)", stripped)

        return int(value_match.group(1)) if value_match else None

    return None


def parse_v4l2_control_fields(list_ctrls_output: str, name: str) -> dict | None:
    """Extract a control's ``key=value`` integer fields (min, max, step,
    default, value, ...) from ``v4l2-ctl --list-ctrls`` text, or None if the
    control is not present."""
    for line in list_ctrls_output.splitlines():
        stripped = line.strip()

        if not stripped.startswith(f"{name} "):
            continue

        return {
            key: int(value) for key, value in re.findall(r"\b(\w+)=(-?\d+)", stripped)
        }

    return None


def list_v4l2_controls(device_path: str) -> str:
    """A device's ``v4l2-ctl --list-ctrls`` text, or "" if the query fails.

    Args:
        device_path: Device node path (e.g. ``"/dev/video0"``).
    """
    try:
        result = subprocess.run(
            ["v4l2-ctl", f"--device={device_path}", "--list-ctrls"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        print("Error: v4l2-utils is not installed. Run: sudo apt install v4l-utils")

        return ""
    except subprocess.CalledProcessError as e:
        print(f"Failed to query controls for {device_path}: {e}")

        return ""

    return result.stdout


def get_v4l2_control_range(device_path: str, name: str) -> tuple[int, int] | None:
    """Query a device's (min, max) for one v4l2 control via ``v4l2-ctl``.

    Args:
        device_path: Device node path (e.g. ``"/dev/video0"``).
        name: Control name to find (e.g. ``"focus_absolute"``).
    """
    return parse_v4l2_control_range(list_v4l2_controls(device_path), name)


def find_v4l2_focus_subdevice() -> str | None:
    """The ``/dev/v4l-subdevN`` node with a ``focus_absolute`` control, or None.

    A Raspberry Pi CSI camera has no ``/dev/videoN`` node of its own; its
    lens (VCM, e.g. ``dw9807``) is a separate V4L2 sub-device. Linux only:
    elsewhere no sub-device nodes exist and this returns None.
    """
    # Natural order, so v4l-subdev10 comes after v4l-subdev2. With several
    # CSI cameras the first lens wins: pairing a lens with its sensor needs
    # the media graph's ancillary links, which v4l2-ctl does not report.
    subdevices = sorted(
        glob.glob(V4L2_SUBDEVICE_GLOB), key=lambda path: (len(path), path)
    )

    for path in subdevices:
        if get_v4l2_control_range(path, V4L2_FOCUS_ABSOLUTE) is not None:
            return path

    return None


def set_v4l2_controls(device_path: str, **controls) -> bool:
    """Set one or more v4l2 controls on a device via ``v4l2-ctl``.

    Args:
        device_path: Device node path (e.g. ``"/dev/video0"``).
        **controls: Control name -> value, applied in the given order
                    (e.g. ``focus_automatic_continuous=0, focus_absolute=450``).

    Returns:
        True on success, False if ``v4l2-ctl`` is missing or the call fails.
    """

    args = ["v4l2-ctl", f"--device={device_path}"]

    for control_name, value in controls.items():
        args.append(f"--set-ctrl={control_name}={value}")

    try:
        subprocess.run(args, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        print("Error: v4l2-utils is not installed. Run: sudo apt install v4l-utils")

        return False
    except subprocess.CalledProcessError as e:
        print(f"Failed to set controls on {device_path}: {e}")

        return False

    return True


def get_v4l2_control(device_path: str, name: str) -> int | None:
    """Read a v4l2 control's current integer value via ``v4l2-ctl``.

    Args:
        device_path: Device node path (e.g. ``"/dev/video0"``).
        name: Control name to read (e.g. ``"focus_absolute"``).
    """

    try:
        result = subprocess.run(
            ["v4l2-ctl", f"--device={device_path}", f"--get-ctrl={name}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        print("Error: v4l2-utils is not installed. Run: sudo apt install v4l-utils")

        return None
    except subprocess.CalledProcessError as e:
        print(f"Failed to read control {name} on {device_path}: {e}")

        return None

    match = re.search(r":\s*(-?\d+)", result.stdout)

    return int(match.group(1)) if match else None


def is_pi_internal_video_node(name: str) -> bool:
    """Whether a V4L2 device header or Qt camera description names one of
    the PI_INTERNAL_VIDEO_NODE_NAMES."""
    name = name.lower()

    return any(node_name in name for node_name in PI_INTERNAL_VIDEO_NODE_NAMES)


def libcamera_camera_id(camera_device) -> str:
    """A libcamera QCameraDevice's libcamera camera id: whichever of its id
    and description is the device-tree path, else its id."""
    camera_id = bytes(camera_device.id()).decode(errors="replace")

    for name in (camera_id, camera_device.description()):
        if name.startswith(LIBCAMERA_ID_PREFIX):
            return name

    return camera_id


def is_libcamera_device(camera_device) -> bool:
    """Whether a QCameraDevice is served by libcamera (a Raspberry Pi CSI
    camera), which has no ``/dev/videoN`` node of its own."""
    return libcamera_camera_id(camera_device).startswith(LIBCAMERA_ID_PREFIX)


def get_real_linux_nodes() -> list[int]:
    """Query V4L2 for the primary video capture nodes, bypassing Qt.

    On Raspberry Pi, Qt's ``QMediaDevices.videoInputs()`` returns abstract
    camera objects without reliable device paths.  This function calls
    ``v4l2-ctl --list-devices`` directly to discover the real ``/dev/videoN``
    nodes and returns them as ``[0, 2, ...]``.

    Pi-internal ISP/CSI/codec devices (PI_INTERNAL_VIDEO_NODE_NAMES) are
    filtered out so only actual cameras appear.

    Returns:
        Ordered list of primary node numbers, e.g. ``[0, 2]``.
        Empty list if ``v4l2-ctl`` is unavailable or fails.
    """
    real_nodes = []
    try:
        out = subprocess.check_output(["v4l2-ctl", "--list-devices"], text=True)
        current_cam = None

        for line in out.splitlines():
            if not line.strip():
                continue

            if not line.startswith("\t"):
                # Non-indented line = new camera header (e.g. "4K USB Camera (usb-...)")
                current_cam = line.strip()
            elif current_cam:
                # First indented line under a header = primary /dev/videoN node.
                if not is_pi_internal_video_node(current_cam):
                    node_num = line.strip().split("video")[-1]
                    real_nodes.append(int(node_num))

                # Only take the first node per camera; ignore metadata nodes.
                current_cam = None

    except FileNotFoundError:
        print("v4l2-ctl not found — install v4l-utils: sudo apt install v4l-utils")
    except Exception as e:
        print(f"Failed to fetch Linux video nodes: {e}")

    return real_nodes


class LinuxCameraDeviceContainer:
    """QCamera subclass that carries the real V4L2 node ID and fps data on Linux.

    On init, queries V4L2 for the real fps values at every supported
    resolution.  Use ``get_fps(width, height)`` to look up the max fps
    for a specific resolution. A libcamera device has no node to query;
    its fps come from its sensor modes instead (see libcamera_sensor_modes).

    On non-Linux platforms ``linux_node_id`` is ``None``, ``fps_map`` is
    empty, and the camera behaves identically to a regular ``QCamera``.
    """

    def __init__(
        self,
        camera_device,
        linux_node_id=None,
        focus_device_path=None,
        focus_lens_map=(),
        sensor_modes=(),
    ):
        self.camera_device = camera_device
        self.linux_node_id = linux_node_id

        # Node the v4l2 focus fallback drives: a libcamera camera's lens
        # sub-device, else the camera's own /dev/videoN node.
        self.focus_device_path = focus_device_path or self.device_path

        # A libcamera lens's calibration from the sensor's tuning file
        # (see libcamera_tuning.lens_map_from_tuning); () when unknown.
        self.focus_lens_map = focus_lens_map

        # A libcamera camera's sensor modes, which answer get_fps for any
        # output size; () for a V4L2 camera.
        self.sensor_modes = sensor_modes

        # {(width, height): [fps, ...]} — populated from V4L2 on Linux
        if self.device_path:
            self.fps_map = get_v4l2_all_fps(self.device_path)
        else:
            self.fps_map = {}

    @property
    def device_path(self):
        """Return ``/dev/videoN`` path, or ``None`` if node ID is unknown."""
        if self.linux_node_id is not None:
            return f"/dev/video{self.linux_node_id}"
        return None

    def get_fps(self, width: int, height: int) -> float:
        """Return the max fps for a resolution, or 0.0 if unknown."""
        if self.sensor_modes and not self.fps_map:
            return libcamera_fps_for(width, height, self.sensor_modes)

        fps_list = self.fps_map.get((width, height), [])

        return max(fps_list) if fps_list else 0.0


def get_linux_video_inputs() -> list[LinuxCameraDeviceContainer]:
    """Discover cameras and return them as ``LinuxCamera`` instances.

    On Linux, queries V4L2 for the real ``/dev/videoN`` node IDs and
    attaches them to each camera.  On other platforms, ``linux_node_id``
    is set to ``None``.

    Pi-internal nodes are dropped. libcamera devices get no node, so the
    real nodes pair by index with the remaining (V4L2) cameras only; their
    focus is driven through the lens sub-device instead (see
    find_v4l2_focus_subdevice), calibrated by the sensor's tuning file
    (see libcamera_tuning.read_lens_map), and their fps come from the
    sensor's modes (see libcamera_sensor_modes.sensor_modes_for_device).
    """
    qt_cameras = [
        cam_device
        for cam_device in QMediaDevices.videoInputs()
        if not is_pi_internal_video_node(cam_device.description())
    ]
    node_ids = iter(get_real_linux_nodes())

    cameras = []

    for cam_device in qt_cameras:
        focus_lens_map = ()
        sensor_modes = ()

        if is_libcamera_device(cam_device):
            node_id = None
            focus_device_path = find_v4l2_focus_subdevice()
            sensor_modes = sensor_modes_for_device(libcamera_camera_id(cam_device))

            if focus_device_path is not None:
                focus_lens_map = read_lens_map()
        else:
            node_id = next(node_ids, None)
            focus_device_path = None

        cameras.append(
            LinuxCameraDeviceContainer(
                cam_device, node_id, focus_device_path, focus_lens_map, sensor_modes
            )
        )

    return cameras


def get_video_inputs() -> list[QCameraDevice | LinuxCameraDeviceContainer]:
    """Discover cameras and return them as ``QCamera`` instances."""

    if os_name == "Linux":
        cameras = get_linux_video_inputs()

    else:
        cameras = QMediaDevices.videoInputs()

    return cameras


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Query supported FPS for a V4L2 camera at a given resolution "
            "and pixel format."
        )
    )
    parser.add_argument("device", help="Device node path (e.g. /dev/video0)")
    parser.add_argument("width", type=int, help="Resolution width (e.g. 1920)")
    parser.add_argument("height", type=int, help="Resolution height (e.g. 1080)")
    parser.add_argument(
        "-f",
        "--format",
        default="JPEG",
        help="Pixel format to match (default: JPEG). Use '*' for all formats.",
    )
    args = parser.parse_args()

    fps_list = get_v4l2_fps(args.device, args.width, args.height, args.format)

    fmt_label = "all formats" if args.format == "*" else args.format
    if fps_list:
        print(
            f"\nSupported FPS for {args.device} at "
            f"{args.width}x{args.height} ({fmt_label}):"
        )
        for fps in fps_list:
            print(f" - {fps} FPS")
        print(f"\nMax FPS: {max(fps_list)}")
    else:
        print(
            f"\nNo FPS data found. {args.device} might not support "
            f"{args.width}x{args.height} in {fmt_label} format."
        )
