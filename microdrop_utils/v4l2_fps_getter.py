import argparse
import subprocess
import re


def get_v4l2_fps(camera_name: str, width: int, height: int, pixel_format: str = "JPEG") -> list[float]:
    """
    Finds the supported FPS for a specific camera, resolution, and pixel format using v4l2-ctl.

    Args:
        camera_name: Camera name as shown by ``v4l2-ctl --list-devices``.
        width: Resolution width (e.g. 1920).
        height: Resolution height (e.g. 1080).
        pixel_format: Pixel format to match (default ``"JPEG"``).
                      Common values: ``"JPEG"``, ``"MJPG"``, ``"YUYV"``, ``"NV12"``, ``"H264"``.
                      Use ``"*"`` to match all formats.
    """
    print(f"Searching for '{camera_name}'...")

    # --- STEP 1: Find the /dev/video path ---
    try:
        # Run v4l2-ctl --list-devices
        list_process = subprocess.run(
            ["v4l2-ctl", "--list-devices"], capture_output=True, text=True, check=True
        )
    except FileNotFoundError:
        print("Error: v4l2-utils is not installed. Run: sudo apt install v4l-utils")
        return []

    device_path = None
    lines = list_process.stdout.splitlines()

    for i, line in enumerate(lines):
        # If we find the camera name in the header line
        if camera_name.lower() in line.lower() and not line.startswith("\t"):
            # The next line containing a tab is the primary video node
            if i + 1 < len(lines) and lines[i + 1].startswith("\t"):
                device_path = lines[i + 1].strip()
                break

    if not device_path:
        print(f"Could not find a device node for '{camera_name}'.")
        return []

    print(f"Found '{camera_name}' at {device_path}. Querying formats...")

    # --- STEP 2: Query Formats & Parse ---
    try:
        format_process = subprocess.run(
            ["v4l2-ctl", f"--device={device_path}", "--list-formats-ext"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to query device {device_path}: {e}")
        return []

    # State machine variables for parsing the output
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Query supported FPS for a V4L2 camera at a given resolution and pixel format."
    )
    parser.add_argument("camera", help="Camera name (as shown by v4l2-ctl --list-devices)")
    parser.add_argument("width", type=int, help="Resolution width (e.g. 1920)")
    parser.add_argument("height", type=int, help="Resolution height (e.g. 1080)")
    parser.add_argument(
        "-f", "--format", default="JPEG",
        help="Pixel format to match (default: JPEG). Use '*' for all formats."
    )
    args = parser.parse_args()

    fps_list = get_v4l2_fps(args.camera, args.width, args.height, args.format)

    fmt_label = "all formats" if args.format == "*" else args.format
    if fps_list:
        print(f"\nSupported FPS for {args.width}x{args.height} ({fmt_label}):")
        for fps in fps_list:
            print(f" - {fps} FPS")
        print(f"\nMax FPS: {max(fps_list)}")
    else:
        print(
            f"\nNo FPS data found. The camera might not support "
            f"{args.width}x{args.height} in {fmt_label} format."
        )
