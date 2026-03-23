# 1. Discover cameras — pairs Qt objects with real /dev/videoN paths
from microdrop_utils.v4l2_fps_getter import map_qt_cameras_to_linux_nodes, get_v4l2_fps

for idx, qt_cam in map_qt_cameras_to_linux_nodes():
    # display_name = "dev0", qt_cam = QCameraDevice object
    device_path = f"/dev/video{idx}"

    # 2. Query FPS for a specific resolution on this camera
    fps_list = get_v4l2_fps(device_path, 1920, 1080)

    print(f"{device_path} ({qt_cam.description()}) @ 1920x1080: {fps_list}")
    # e.g. "dev0 (4K USB Camera) @ 1920x1080: [30.0, 15.0, 5.0]"

    if fps_list:
        print(f"  Max FPS: {max(fps_list)}")
