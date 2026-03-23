"""Demo: Discover Linux cameras and their real V4L2 fps values.

Requires: v4l-utils (sudo apt install v4l-utils), PySide6, Linux.
"""
from microdrop_utils.v4l2_fps_getter import get_video_inputs

cameras = get_video_inputs()
print(f"Found {len(cameras)} camera(s)\n")

for cam in cameras:
    desc = cam.cameraDevice().description()
    print(f"  {desc}")
    print(f"    Node ID:     {cam.linux_node_id}")
    print(f"    Device path: {cam.device_path}")

    if cam.fps_map:
        print(f"    Resolutions: {len(cam.fps_map)}")
        for (w, h), fps_list in sorted(cam.fps_map.items(), reverse=True):
            max_fps = max(fps_list)
            print(f"      {w}x{h}: {fps_list} (max {max_fps})")
    else:
        print("    No V4L2 fps data (non-Linux or query failed)")

    print()
