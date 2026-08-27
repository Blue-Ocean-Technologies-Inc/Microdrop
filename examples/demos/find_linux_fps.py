# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Demo: Discover Linux cameras and their real V4L2 fps values.

Requires: v4l-utils (sudo apt install v4l-utils), PySide6, Linux.
"""
from microdrop_utils.v4l2_fps_getter import get_video_inputs

cameras = get_video_inputs()
print(f"Found {len(cameras)} camera(s)\n")

for cam in cameras:
    desc = cam.camera_device.description()
    print(f"  {desc}")
    print(f"    Node ID:     {cam.linux_node_id}")
    print(f"    Device path: {cam.device_path}")

    if cam.fps_map:
        print(f"    Resolutions: {len(cam.fps_map)}")
        for (w, h), fps_list in sorted(cam.fps_map.items(), reverse=True):
            max_fps = cam.get_fps(w, h)
            print(f"      {w}x{h}: {fps_list} (max {max_fps})")
    else:
        print("    No V4L2 fps data (non-Linux or query failed)")

    print()
