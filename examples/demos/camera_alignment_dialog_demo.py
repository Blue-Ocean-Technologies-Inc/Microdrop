"""Standalone demo of the Camera Alignment window over dummy images
(no camera, no device, no Redis). Run from the repo root:

    python examples/demos/camera_alignment_dialog_demo.py

A drawn electrode grid stands in for the device render (its rect
corners feed the endpoint pane's snap targets) and a shifted
grayscale copy of the same grid stands in for the camera frame, so
zooming, snapping, recapture, the settings sidebar, and Confirm
Alignment can all be exercised. Preferences are in-memory, so the
sidebar never writes to the real preference files."""

import sys

from apptools.preferences.api import Preferences
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from device_viewer.preferences import DeviceViewerPreferences
from device_viewer.views.camera_alignment_view.alignment_dialog import (
    CameraAlignmentController,
    CameraAlignmentModel,
    camera_alignment_dialog_view,
)
from device_viewer.views.camera_alignment_view.alignment_panes import (
    EndpointPane,
    OutlinePane,
)
from device_viewer.views.camera_alignment_view.alignment_settings import (
    SETTING_TRAITS,
    AlignmentSettingsModel,
)
from microdrop_style.helpers import style_app

WIDTH_PX, HEIGHT_PX = 800, 600
GRID_RECTS = [
    (60 + col * 120, 80 + row * 120, 90, 90) for row in range(4) for col in range(6)
]


def _grid_image(background, pen, brush, offset=(0, 0)) -> QImage:
    """A fake electrode grid — the stand-in for both the device
    render and the camera frame (drawn offset so the two panes
    visibly differ)."""
    image = QImage(WIDTH_PX, HEIGHT_PX, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor(background))

    painter = QPainter(image)
    painter.setPen(QColor(pen))
    painter.setBrush(QColor(brush))
    for x, y, w, h in GRID_RECTS:
        painter.drawRect(x + offset[0], y + offset[1], w, h)
    painter.end()

    return image


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    style_app(app)

    # In-memory preferences — nothing the demo touches is written to
    # the real preference files.
    preferences = DeviceViewerPreferences(preferences=Preferences())
    overlay_options = {
        name: getattr(preferences, f"alignment_{name}") for name in SETTING_TRAITS
    }

    endpoint_pane = EndpointPane(
        device_image=_grid_image("#101018", "#4488cc", "#224466"),
        scene_rect=QRectF(0, 0, WIDTH_PX, HEIGHT_PX),  # 1:1 pixel<->scene
        device_name="demo-device",
        snap_scene_points=[
            corner
            for x, y, w, h in GRID_RECTS
            for corner in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
        ],
        overlay_options=overlay_options,
    )
    endpoint_pane.observe(
        lambda event: print(f"endpoint saved: {event.new}"), "endpoint_saved"
    )

    outline_pane = OutlinePane(
        # The capture callable: a grayscale-ish "camera frame" of
        # the same grid, shifted so recapture visibly does something.
        capture_frame=lambda: _grid_image(
            "#303030", "#c0c0c0", "#606060", offset=(40, 25)
        ),
        overlay_options=overlay_options,
    )
    outline_pane.observe(
        lambda event: print(f"outline accepted: {event.new}"), "quad_accepted"
    )

    model = CameraAlignmentModel(
        endpoint_pane=endpoint_pane,
        outline_pane=outline_pane,
        settings=AlignmentSettingsModel(preferences=preferences),
    )
    model.observe(lambda event: print("alignment confirmed"), "alignment_confirmed")

    ui = CameraAlignmentController(model=model).edit_traits(
        view=camera_alignment_dialog_view
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
