import argparse
import subprocess
import platform
import re
from PySide6.QtMultimedia import QCamera, QMediaDevices, QCameraDevice

os_name = platform.system()


def get_v4l2_fps(device_path: str, width: int, height: int, pixel_format: str = "JPEG") -> list[float]:
    """
    Finds the supported FPS for a V4L2 device node at a given resolution and pixel format.

    Args:
        device_path: Device node path (e.g. ``"/dev/video0"``).
        width: Resolution width (e.g. 1920).
        height: Resolution height (e.g. 1080).
        pixel_format: Pixel format to match (default ``"JPEG"``).
                      Common values: ``"JPEG"``, ``"MJPG"``, ``"YUYV"``, ``"NV12"``, ``"H264"``.
                      Use ``"*"`` to match all formats.
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


def get_v4l2_all_fps(device_path: str, pixel_format: str = "JPEG") -> dict[tuple[int, int], list[float]]:
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
            capture_output=True, text=True, check=True,
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


def get_real_linux_nodes() -> list[int]:
    """Query V4L2 for the primary video capture nodes, bypassing Qt.

    On Raspberry Pi, Qt's ``QMediaDevices.videoInputs()`` returns abstract
    camera objects without reliable device paths.  This function calls
    ``v4l2-ctl --list-devices`` directly to discover the real ``/dev/videoN``
    nodes and returns them as ``[0, 2, ...]``.

    Internal Pi ISP/codec devices (``pispbe``, ``hevc``) are filtered out so
    only actual cameras appear.

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
                # Skip Pi-internal ISP and codec devices.
                if "pispbe" not in current_cam.lower() and "hevc" not in current_cam.lower():
                    node_num = line.strip().split("video")[-1]
                    real_nodes.append(int(node_num))

                # Only take the first node per camera; ignore metadata nodes.
                current_cam = None

    except FileNotFoundError:
        print("v4l2-ctl not found — install v4l-utils: sudo apt install v4l-utils")
    except Exception as e:
        print(f"Failed to fetch Linux video nodes: {e}")

    return real_nodes


class LinuxCamera(QCamera):
    """QCamera subclass that carries the real V4L2 node ID and fps data on Linux.

    On init, queries V4L2 for the real fps values at every supported
    resolution.  Use ``get_fps(width, height)`` to look up the max fps
    for a specific resolution.

    On non-Linux platforms ``linux_node_id`` is ``None``, ``fps_map`` is
    empty, and the camera behaves identically to a regular ``QCamera``.
    """

    def __init__(self, camera_device, linux_node_id=None):
        super().__init__(camera_device)
        self.linux_node_id = linux_node_id

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
        fps_list = self.fps_map.get((width, height), [])
        return max(fps_list) if fps_list else 0.0

def get_linux_video_inputs() -> list[LinuxCamera]:
    """Discover cameras and return them as ``LinuxCamera`` instances.

    On Linux, queries V4L2 for the real ``/dev/videoN`` node IDs and
    attaches them to each camera.  On other platforms, ``linux_node_id``
    is set to ``None``.
    """
    qt_cameras = QMediaDevices.videoInputs()
    node_ids = get_real_linux_nodes()

    cameras = []
    for i, cam_device in enumerate(qt_cameras):
        node_id = node_ids[i] if i < len(node_ids) else None
        cameras.append(LinuxCamera(cam_device, linux_node_id=node_id))

    return cameras

def get_video_inputs() -> list[QCameraDevice | LinuxCamera]:
    """Discover cameras and return them as ``QCamera`` instances."""

    if os_name == "Linux":
        cameras = get_linux_video_inputs()

    else:
        cameras = QMediaDevices.videoInputs()

    return cameras


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Query supported FPS for a V4L2 camera at a given resolution and pixel format."
    )
    parser.add_argument("device", help="Device node path (e.g. /dev/video0)")
    parser.add_argument("width", type=int, help="Resolution width (e.g. 1920)")
    parser.add_argument("height", type=int, help="Resolution height (e.g. 1080)")
    parser.add_argument(
        "-f", "--format", default="JPEG",
        help="Pixel format to match (default: JPEG). Use '*' for all formats."
    )
    args = parser.parse_args()

    fps_list = get_v4l2_fps(args.device, args.width, args.height, args.format)

    fmt_label = "all formats" if args.format == "*" else args.format
    if fps_list:
        print(f"\nSupported FPS for {args.device} at {args.width}x{args.height} ({fmt_label}):")
        for fps in fps_list:
            print(f" - {fps} FPS")
        print(f"\nMax FPS: {max(fps_list)}")
    else:
        print(
            f"\nNo FPS data found. {args.device} might not support "
            f"{args.width}x{args.height} in {fmt_label} format."
        )
