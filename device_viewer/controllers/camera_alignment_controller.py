# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Controller for the Device Viewer's camera-alignment endpoint workflow.

One combined Camera Alignment dialog: the endpoint pane (just the
device SVG) on the left, where the per-device ground truth is
viewed and placed (orange frame, conspicuous corner dots —
distinct from the regular aligner's red rect) and Save persists it
per device; the outline pane (a captured camera frame, with a
recapture glyph) on the right, where the start points are marked.
Go To Endpoint then automates the four precise drags, animated.
Nothing endpoint-related is drawn on the device view itself, and
only Go To Endpoint moves the red frame — the two are fully
decoupled.

The pane composes this controller and hands it the few collaborators it
cannot reach through the model: the camera feed's video item, the current
electrode layer, the offscreen device render, the dialog parent, and the
status bar.
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from pyface.qt.QtCore import QPointF, Qt, QTimer
from traits.api import Any, Callable, HasTraits, Instance, Int, observe
from traitsui.api import UI

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import error, warning

# Local imports.
from ..models.main_model import DeviceViewMainModel
from ..preferences import DeviceViewerPreferences
from ..utils.camera_endpoints import CameraEndpointStore
from ..views.camera_alignment_view.alignment_dialog import (
    CameraAlignmentController,
    CameraAlignmentModel,
    camera_alignment_dialog_view,
)
from ..views.camera_alignment_view.alignment_panes import EndpointPane, OutlinePane
from ..views.camera_alignment_view.alignment_settings import (
    SETTING_TRAITS,
    AlignmentSettingsModel,
)


class CameraAlignmentWorkflowController(HasTraits):
    """Own the per-device endpoint store, the Camera Alignment dialog,
    and the animated Go To Endpoint drag."""

    #: Device view model whose camera perspective and mode are driven here.
    model = Instance(DeviceViewMainModel)

    #: Source of the persisted 'alignment_' overlay settings.
    preferences = Instance(DeviceViewerPreferences)

    #: Per-device saved endpoints.
    endpoint_store = Instance(CameraEndpointStore, ())

    #: Returns the camera feed's QGraphicsVideoItem.
    get_video_item = Callable()

    #: Returns the current ElectrodeLayer, or None before a device loads.
    get_electrode_layer = Callable()

    #: Returns (QImage, scene rect) of the device rendered offscreen, or
    #: (None, None) when it has no drawable geometry.
    render_device_image = Callable()

    #: Returns the widget the alignment dialog is parented to.
    get_dialog_parent = Callable()

    #: Shows a message in the application status bar.
    statusbar_message = Callable()

    # The open Camera Alignment dialog's model; None while closed. The
    # @observe handlers below re-hook automatically on every assignment.
    _alignment_model = Instance(CameraAlignmentModel)

    #: The open Camera Alignment dialog; None while closed.
    _alignment_ui = Instance(UI)

    #: Drives the Go To Endpoint animation; built on first use.
    _align_timer = Instance(QTimer)

    #: (start points, targets, steps) of the running animation.
    _align_animation = Any()

    #: Ticks elapsed in the running animation.
    _align_animation_step = Int()

    def current_device_key(self):
        """The per-device cache key: the loaded device SVG's stem."""
        svg_model = self.model.electrodes.svg_model
        filename = getattr(svg_model, "filename", None)
        if not filename:
            return None
        return Path(str(filename)).stem

    def _camera_to_item_mapping(self):
        """The affine RAW-camera-pixel -> video-item-local mapping as
        (scale_x, scale_y, offset_x, offset_y) — the item is
        scene-sized and letterboxes the frame under the default
        KeepAspectRatio."""
        video_item = self.get_video_item()
        native = video_item.nativeSize()
        if native.isEmpty():
            raise RuntimeError("no camera frames yet — cannot map camera pixels")
        item_size = video_item.size()
        if video_item.aspectRatioMode() == Qt.AspectRatioMode.IgnoreAspectRatio:
            scale_x = item_size.width() / native.width()
            scale_y = item_size.height() / native.height()
            offset_x = offset_y = 0.0
        else:
            scale_x = scale_y = min(
                item_size.width() / native.width(), item_size.height() / native.height()
            )
            offset_x = (item_size.width() - native.width() * scale_x) / 2
            offset_y = (item_size.height() - native.height() * scale_y) / 2
        return scale_x, scale_y, offset_x, offset_y

    def _camera_pixels_to_video_item(self, point: QPointF) -> QPointF:
        scale_x, scale_y, offset_x, offset_y = self._camera_to_item_mapping()
        return QPointF(offset_x + point.x() * scale_x, offset_y + point.y() * scale_y)

    def _current_camera_quad(self):
        """The active reference rect back in RAW camera pixels (the
        picker's starting quad), or None."""
        perspective = self.model.camera_perspective
        if len(perspective.reference_rect) != 4:
            return None
        try:
            scale_x, scale_y, offset_x, offset_y = self._camera_to_item_mapping()
        except RuntimeError:
            return None
        return [
            [(point.x() - offset_x) / scale_x, (point.y() - offset_y) / scale_y]
            for point in perspective.reference_rect
        ]

    def _capture_camera_frame(self):
        """ONE raw camera frame (just the device image — none of the
        viewer's overlays in the way) as a QImage copy, or None when
        the camera has no frame yet. The outline pane calls this at
        open and again on every recapture click."""
        frame = self.get_video_item().videoSink().videoFrame()
        image = frame.toImage()
        return None if image.isNull() else image.copy()

    @observe("_alignment_model:outline_pane:quad_accepted")
    def _stage_alignment_start_points(self, event):
        """The outline pane's accepted quad (``event.new``, camera
        pixels): pin the four marked spots
        where they CURRENTLY show on the feed (no visual jump) and
        enter camera-edit so the user can fine-tune, then Go To
        Endpoint."""
        try:
            item_points = [
                self._camera_pixels_to_video_item(QPointF(float(x), float(y)))
                for x, y in event.new
            ]
        except RuntimeError as exc:
            error(None, str(exc), title="Select Device Outline")
            return
        perspective = self.model.camera_perspective
        current = perspective.transformation
        perspective.reference_rect = item_points
        perspective.transformed_reference_rect = [
            current.map(point) for point in item_points
        ]
        self.model.mode = "camera-edit"

    def go_to_endpoint(self):
        """Automate the drags: glide the marked points onto this
        device's saved endpoint."""
        device_key = self.current_device_key()
        endpoint = self.endpoint_store.load(device_key) if device_key else None
        if endpoint is None:
            warning(
                None,
                "No saved endpoint for this device — set "
                "one in View/Edit Endpoint first.",
                title="Go To Endpoint",
            )
            return
        perspective = self.model.camera_perspective
        if len(perspective.transformed_reference_rect) != 4:
            warning(
                None,
                "No start points are marked on the feed — Select Device Outline first.",
                title="Go To Endpoint",
            )
            return
        if self.model.mode != "camera-edit":
            self.model.mode = "camera-edit"
        self._start_align_animation([QPointF(float(x), float(y)) for x, y in endpoint])

    def _start_align_animation(self, targets, steps=40, interval_ms=40):
        """Glide the transformed reference points onto their targets
        so the user watches the feed warp into place; restores the
        previous mode when done."""
        perspective = self.model.camera_perspective
        self._align_animation = (
            [QPointF(point) for point in perspective.transformed_reference_rect],
            [QPointF(point) for point in targets],
            steps,
        )
        self._align_animation_step = 0
        if self._align_timer is None:
            self._align_timer = QTimer()
            self._align_timer.timeout.connect(self._on_align_animation_tick)
        self._align_timer.start(interval_ms)

    def _on_align_animation_tick(self):
        start_points, targets, steps = self._align_animation
        self._align_animation_step += 1
        progress = min(self._align_animation_step / steps, 1.0)
        eased = progress * progress * (3 - 2 * progress)
        self.model.camera_perspective.transformed_reference_rect = [
            QPointF(
                start.x() + (target.x() - start.x()) * eased,
                start.y() + (target.y() - start.y()) * eased,
            )
            for start, target in zip(start_points, targets)
        ]
        if progress >= 1.0:
            self._align_timer.stop()
            self.model.goto_last_mode()

    def open_camera_alignment(self):
        """Open the combined Camera Alignment dialog: the endpoint
        pane (device SVG alone, with this device's saved endpoint to
        view and adjust — or a starter quad when none is saved) next
        to the outline pane (a captured camera frame, with a
        recapture glyph), plus the collapsible tuning sidebar."""
        device_key = self.current_device_key()
        electrode_layer = self.get_electrode_layer()
        if device_key is None or electrode_layer is None:
            warning(
                None,
                "No device is loaded — load a device SVG first.",
                title="Camera Alignment",
            )
            return

        image, scene_rect = self.render_device_image()
        if image is None:
            error(
                None,
                "The loaded device has no drawable geometry.",
                title="Camera Alignment",
            )
            return

        self.close_alignment_dialog()

        # Every electrode path vertex is a corner (only straight-line
        # SVG commands exist), scaled by the layer's path_scale since
        # the scene (and the endpoint quad) uses scaled coordinates.
        scale = electrode_layer.path_scale
        corner_points = [
            scaled_point
            for electrode in self.model.electrodes
            for scaled_point in (scale * electrode.path).tolist()
        ]

        # The QuadOverlay kwargs mirror the persisted 'alignment_'
        # preferences one-for-one (see SETTING_TRAITS).
        preferences = self.preferences
        overlay_options = {
            name: getattr(preferences, f"alignment_{name}") for name in SETTING_TRAITS
        }

        endpoint_pane = EndpointPane(
            device_image=image,
            scene_rect=scene_rect,
            initial_scene_quad=self.endpoint_store.load(device_key),
            device_name=device_key,
            snap_scene_points=corner_points,
            overlay_options=overlay_options,
        )
        outline_pane = OutlinePane(
            capture_frame=self._capture_camera_frame,
            initial_quad=self._current_camera_quad(),
            overlay_options=overlay_options,
        )

        # Assigning the model trait hooks the @observe handlers below.
        # Confirm Alignment fires alignment_confirmed AFTER the two
        # pane events have saved the endpoint and staged the points,
        # so Go To Endpoint finds both in place.
        self._alignment_model = CameraAlignmentModel(
            endpoint_pane=endpoint_pane,
            outline_pane=outline_pane,
            settings=AlignmentSettingsModel(preferences=preferences),
        )
        self._alignment_ui = CameraAlignmentController(
            model=self._alignment_model,
        ).edit_traits(
            view=camera_alignment_dialog_view, parent=self.get_dialog_parent()
        )

    @observe("_alignment_model:endpoint_pane:endpoint_saved")
    def _on_endpoint_editor_saved(self, event):
        """The endpoint pane's saved quad (``event.new``, device-scene
        coordinates): persist it as this device's endpoint."""
        device_key = self.current_device_key()
        if device_key is None:
            return

        self.endpoint_store.save(device_key, event.new)
        self.statusbar_message(f"Saved camera-alignment endpoint for {device_key}")

    @observe("_alignment_model:alignment_confirmed")
    def _on_alignment_confirmed(self, event):
        self.go_to_endpoint()

    def close_alignment_dialog(self):
        if self._alignment_ui is not None:
            if self._alignment_ui.control is not None:
                self._alignment_ui.dispose()
            self._alignment_ui = None
        self._alignment_model = None
