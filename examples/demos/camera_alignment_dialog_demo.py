# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Standalone demo of the Camera Alignment window over dummy images
(no camera, no device, no Redis). Run from the repo root:

    python -m examples.demos.camera_alignment_dialog_demo

A drawn electrode grid stands in for the device render (its rect
corners feed the endpoint pane's snap targets) and a shifted
grayscale copy of the same grid stands in for the camera frame, so
zooming, snapping, recapture, the settings sidebar, and Confirm
Alignment can all be exercised. Preferences are in-memory, so the
sidebar never writes to the real preference files, and the Presets
strip works on a throwaway store: Save as… keeps the panes' dots,
Apply puts a preset's dots back on the panes."""

# Standard library imports.
import sys
import tempfile
from pathlib import Path

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt.QtCore import QRectF
from pyface.qt.QtGui import QColor, QImage, QPainter
from pyface.qt.QtWidgets import QApplication
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.models.alignment_preset import AlignmentPreset
from device_viewer.models.alignment_preset_store import AlignmentPresetStore
from device_viewer.models.alignment_preset_table import (
    AlignmentPresetName,
    AlignmentPresetTable,
)
from device_viewer.preferences import DeviceViewerPreferences
from device_viewer.utils.camera_endpoints import CameraEndpointStore
from device_viewer.views.camera_alignment_view.alignment_dialog import (
    CameraAlignmentController,
    CameraAlignmentModel,
    camera_alignment_dialog_view,
)
from device_viewer.views.camera_alignment_view.alignment_panes import (
    EndpointPane,
    OutlinePane,
)
from device_viewer.views.camera_alignment_view.alignment_presets_view import (
    ask_alignment_preset_name,
)
from device_viewer.views.camera_alignment_view.alignment_settings import (
    SETTING_TRAITS,
    AlignmentSettingsModel,
)

# Microdrop style imports.
from microdrop_style.helpers import style_app

WIDTH_PX, HEIGHT_PX = 800, 600
GRID_RECTS = [
    (60 + col * 120, 80 + row * 120, 90, 90) for row in range(4) for col in range(6)
]
DEVICE_KEY = "demo-device"


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


class PresetsDemoController(HasTraits):
    """Stands in for the workflow controller: Save as… snapshots the
    panes' dots, Apply moves them back. Nothing touches a live feed."""

    model = Instance(CameraAlignmentModel)

    @observe("model:preset_table:save_as_button")
    def _save_panes_as_preset(self, event):
        store = self.model.preset_table.store
        endpoint = self.model.endpoint_pane.scene_quad()
        naming = AlignmentPresetName(
            name=store.next_default_name(DEVICE_KEY), device_key=DEVICE_KEY
        )
        replace = ask_alignment_preset_name(
            naming, lambda name: store.find_named(DEVICE_KEY, name)
        )

        if replace is None:
            return

        preset = store.save_named(
            naming.name,
            AlignmentPreset(
                device_key=DEVICE_KEY,
                camera_quad=self.model.outline_pane.raw_quad(),
                scene_quad=endpoint,
                endpoint_quad=endpoint,
            ),
            replace=replace,
        )

        if naming.make_default:
            store.set_default(preset.id)

    @observe("model:preset_table:apply_requested")
    def _apply_preset_to_panes(self, event):
        preset = self.model.preset_table.store.get(event.new.preset_id)
        self.model.endpoint_pane.show_scene_quad(preset.endpoint_quad)

        if preset.camera_quad is not None:
            self.model.outline_pane.show_raw_quad(preset.camera_quad)

        print(f"applied preset {preset.name!r}")


def build_demo_window(directory):
    """Open the demo window over a throwaway presets store in
    ``directory``; return its UI and the presets stand-in controller
    (keep both referenced: observers do not keep their handlers alive)."""
    # In-memory preferences — nothing the demo touches is written to
    # the real preference files.
    preferences = DeviceViewerPreferences(preferences=Preferences())
    overlay_options = {
        name: getattr(preferences, f"alignment_{name}") for name in SETTING_TRAITS
    }

    endpoint_pane = EndpointPane(
        device_image=_grid_image("#101018", "#4488cc", "#224466"),
        scene_rect=QRectF(0, 0, WIDTH_PX, HEIGHT_PX),  # 1:1 pixel<->scene
        device_name=DEVICE_KEY,
        endpoint_store=CameraEndpointStore(path=Path(directory) / "endpoints.json"),
        snap_scene_points=[
            corner
            for x, y, w, h in GRID_RECTS
            for corner in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
        ],
        overlay_options=overlay_options,
    )
    outline_pane = OutlinePane(
        # The capture callable: a grayscale-ish "camera frame" of
        # the same grid, shifted so recapture visibly does something.
        capture_frame=lambda: _grid_image(
            "#303030", "#c0c0c0", "#606060", offset=(40, 25)
        ),
        overlay_options=overlay_options,
    )

    store = AlignmentPresetStore(
        path=Path(directory) / "alignment_presets.json",
        endpoint_store=endpoint_pane.endpoint_store,
    )
    store.refresh()

    bench_quad = [[60.0, 80.0], [740.0, 80.0], [740.0, 530.0], [60.0, 530.0]]
    bench = store.save_named(
        "bench",
        AlignmentPreset(
            device_key=DEVICE_KEY,
            camera_quad=[[100, 105], [780, 105], [780, 555], [100, 555]],
            scene_quad=bench_quad,
            endpoint_quad=bench_quad,
        ),
    )
    store.set_default(bench.id)
    store.save_named(
        "bench",
        AlignmentPreset(
            device_key="other-device", scene_quad=bench_quad, endpoint_quad=bench_quad
        ),
    )

    model = CameraAlignmentModel(
        endpoint_pane=endpoint_pane,
        outline_pane=outline_pane,
        settings=AlignmentSettingsModel(preferences=preferences),
        preset_table=AlignmentPresetTable(store=store, current_device_key=DEVICE_KEY),
    )
    presets_controller = PresetsDemoController(model=model)
    ui = CameraAlignmentController(model=model).edit_traits(
        view=camera_alignment_dialog_view
    )

    return ui, presets_controller


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    style_app(app)

    with tempfile.TemporaryDirectory() as directory:
        ui, _presets_controller = build_demo_window(directory)
        app.exec()
        ui.dispose()


if __name__ == "__main__":
    main()
