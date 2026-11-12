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
only Go To Endpoint (or applying a preset) moves the red frame.

The window's Presets strip lists named snapshots of confirmed
alignments; Save as captures the live state, Apply writes a preset's
endpoint into the working endpoint store and glides the feed onto it.

The pane composes this controller and hands it the few collaborators it
cannot reach through the model (which also carries the preferences): the
camera feed's video item, the current
electrode layer, the offscreen device render, the dialog parent, the
status bar, and the selected camera's label.
"""

# Standard library imports.
from datetime import datetime

# Enthought library imports.
from pyface.qt.QtCore import QPointF, Qt, QTimer
from traits.api import Any, Callable, HasTraits, Instance, Int, observe
from traitsui.api import UI

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import (
    YES,
    choose,
    confirm,
    error,
    warning,
)

# Local imports.
from ..consts import (
    ALIGNMENT_PRESET_SAVED_AT_FORMAT,
    APPLY_ALIGNMENT_PRESET_DIALOG_TITLE,
    BEFORE_APPLY_PRESET_NAME_TEMPLATE,
    CONFIRM_AND_SAVE_CHOICE,
    DELETE_ALIGNMENT_PRESET_DIALOG_TITLE,
    ENDPOINT_ONLY_PRESET_NOTE,
    NOTHING_CONFIRMED_MESSAGE,
    PENDING_PANE_EDITS_MESSAGE,
    PRESET_ENDPOINT_ONLY_NOTE,
    PRESET_INVALID_FRAME_SIZE_NOTE,
    PRESET_NO_CAMERA_FRAME_NOTE,
    PRESET_RESCALED_TEMPLATE,
    PRESET_SHAPE_MISMATCH_NOTE,
    PRESETS_UNAVAILABLE_TEMPLATE,
    PRESETS_UNREADABLE_TEMPLATE,
    SAVE_ALIGNMENT_PRESET_DIALOG_TITLE,
    SAVE_CONFIRMED_CHOICE,
)
from ..models.alignment_preset import AlignmentPreset
from ..models.alignment_preset_store import AlignmentPresetStore
from ..models.alignment_preset_table import AlignmentPresetName, AlignmentPresetTable
from ..models.main_model import DeviceViewMainModel
from ..utils.alignment_geometry import (
    camera_point_to_item,
    camera_quad_in_frame,
    camera_to_item_mapping,
    item_point_to_camera,
    quads_close,
    valid_frame_size,
)
from ..utils.camera_endpoints import CameraEndpointStore
from ..views.camera_alignment_view.alignment_dialog import (
    CameraAlignmentController,
    CameraAlignmentModel,
    camera_alignment_dialog_view,
)
from ..views.camera_alignment_view.alignment_panes import EndpointPane, OutlinePane
from ..views.camera_alignment_view.alignment_presets_view import (
    ask_alignment_preset_name,
)
from ..views.camera_alignment_view.alignment_settings import (
    SETTING_TRAITS,
    AlignmentSettingsModel,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class CameraAlignmentWorkflowController(HasTraits):
    """Own the per-device endpoint store, the alignment presets, the
    Camera Alignment dialog, and the animated Go To Endpoint drag."""

    #: Device view model whose camera perspective and mode are driven here.
    model = Instance(DeviceViewMainModel)

    #: Per-device saved endpoints.
    endpoint_store = Instance(CameraEndpointStore, ())

    #: The saved alignment presets (migrated from ``endpoint_store`` on
    #: first use).
    preset_store = Instance(AlignmentPresetStore)

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

    #: Returns the selected camera's label ("" with none).
    get_camera_label = Callable()

    #: The open Camera Alignment dialog's model; None while closed. The
    #: @observe handlers below re-hook automatically on every assignment.
    _alignment_model = Instance(CameraAlignmentModel)

    #: The open Camera Alignment dialog; None while closed.
    _alignment_ui = Instance(UI)

    #: Drives the Go To Endpoint animation; built on first use.
    _align_timer = Instance(QTimer)

    #: (start points, targets, steps) of the running animation.
    _align_animation = Any()

    #: Ticks elapsed in the running animation.
    _align_animation_step = Int()

    def _preset_store_default(self):
        return AlignmentPresetStore(endpoint_store=self.endpoint_store)

    def _camera_to_item_mapping(self):
        """The affine RAW-camera-pixel -> video-item-local mapping as
        (scale_x, scale_y, offset_x, offset_y) for the live frame size.
        Raises RuntimeError without frames or a sized video item."""
        frame_size = self._frame_size()

        if frame_size is None:
            raise RuntimeError("no camera frames yet — cannot map camera pixels")

        mapping = self._item_mapping_for(frame_size)

        if mapping is None:
            raise RuntimeError("the camera view has no size — cannot map camera pixels")

        return mapping

    def _camera_pixels_to_video_item(self, point):
        mapping = self._camera_to_item_mapping()

        return QPointF(*camera_point_to_item([point.x(), point.y()], mapping))

    def _current_camera_quad(self):
        """The active reference rect back in RAW camera pixels (the
        picker's starting quad), or None."""
        perspective = self.model.camera_perspective

        if len(perspective.reference_rect) != 4:
            return None

        try:
            mapping = self._camera_to_item_mapping()
        except RuntimeError:
            return None

        return [
            item_point_to_camera([point.x(), point.y()], mapping)
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
        device_key = self.model.device_key
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
        device_key = self.model.device_key
        electrode_layer = self.get_electrode_layer()

        if not device_key or electrode_layer is None:
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
        self._refresh_presets()

        # Without a saved endpoint, the device's default preset seeds both
        # panes.
        saved_endpoint = self.endpoint_store.load(device_key)
        default_preset = (
            self.preset_store.resolve_default(device_key, self._camera_label())
            if saved_endpoint is None
            else None
        )
        initial_endpoint = saved_endpoint
        initial_camera_quad = self._current_camera_quad()

        if default_preset is not None:
            initial_endpoint = default_preset.endpoint_quad
            default_camera_quad, _, _ = self._preset_camera_quad_now(default_preset)

            if default_camera_quad is not None:
                initial_camera_quad = default_camera_quad

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
        preferences = self.model.preferences
        overlay_options = {
            name: getattr(preferences, f"alignment_{name}") for name in SETTING_TRAITS
        }

        endpoint_pane = EndpointPane(
            device_image=image,
            scene_rect=scene_rect,
            initial_scene_quad=initial_endpoint,
            device_name=device_key,
            endpoint_store=self.endpoint_store,
            default_preset_name=self._default_preset_name(device_key),
            snap_scene_points=corner_points,
            overlay_options=overlay_options,
        )
        outline_pane = OutlinePane(
            capture_frame=self._capture_camera_frame,
            initial_quad=initial_camera_quad,
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
            preset_table=AlignmentPresetTable(
                store=self.preset_store,
                current_device_key=device_key,
                editable=self.model.editable,
                live_frame_size=self._frame_size(),
            ),
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
        device_key = self.model.device_key

        if not device_key:
            return

        try:
            self.endpoint_store.save(device_key, event.new)
        except OSError as exc:
            logger.error(f"Could not save the endpoint of {device_key}: {exc}")
            error(
                self._alignment_window(),
                f"The camera-alignment endpoint for {device_key} could not be "
                f"saved to {self.endpoint_store.path}.",
                title="Camera Alignment",
                detail=f"{exc}",
            )
            return

        self.statusbar_message(f"Saved camera-alignment endpoint for {device_key}")

    @observe("_alignment_model:alignment_confirmed")
    def _on_alignment_confirmed(self, event):
        self.go_to_endpoint()

    def close_alignment_dialog(self):
        """Dispose the open Camera Alignment dialog, if any."""
        if self._alignment_ui is not None:
            if self._alignment_ui.control is not None:
                self._alignment_ui.dispose()

            self._alignment_ui = None

        # The long-lived store would otherwise keep the closed window's
        # table alive through the table's observers on it.
        if self._alignment_model is not None and (
            self._alignment_model.preset_table is not None
        ):
            self._alignment_model.preset_table.store = None

        self._alignment_model = None

    # ------------------------------------------------------------------ #
    # Presets
    # ------------------------------------------------------------------ #
    def save_current_as(self):
        """Name the confirmed live alignment and save it as a preset of
        the loaded device. Unconfirmed dots in the panes are offered for
        confirmation first; refused while a protocol runs."""
        device_key = self.model.device_key
        parent = self._alignment_window()

        if not device_key:
            warning(
                parent,
                "No device is loaded — load a device SVG first.",
                title=SAVE_ALIGNMENT_PRESET_DIALOG_TITLE,
            )
            return

        if not self.model.editable:
            warning(
                parent,
                "A protocol is running — save the alignment once it stops.",
                title=SAVE_ALIGNMENT_PRESET_DIALOG_TITLE,
            )
            return

        if not self._resolve_pending_pane_edits(parent):
            return

        snapshot = self._live_alignment_snapshot()

        if snapshot is None:
            warning(
                parent,
                "There is no confirmed endpoint to save — place one in the "
                "endpoint pane and confirm it first.",
                title=SAVE_ALIGNMENT_PRESET_DIALOG_TITLE,
            )
            return

        naming = AlignmentPresetName(
            name=self.preset_store.next_default_name(device_key),
            device_key=device_key,
            note=ENDPOINT_ONLY_PRESET_NOTE if snapshot.is_endpoint_only else "",
            make_default=self.preset_store.resolve_default(device_key) is None,
        )
        replace = ask_alignment_preset_name(
            naming,
            lambda name: self.preset_store.find_named(device_key, name),
            parent=parent,
        )

        if replace is None:
            return

        try:
            preset = self.preset_store.save_named(
                naming.name, snapshot, replace=replace
            )

            if naming.make_default:
                self.preset_store.set_default(preset.id)

        except (OSError, ValueError) as exc:
            logger.error(f"Could not save alignment preset '{naming.name}': {exc}")
            error(
                parent,
                f"The alignment preset '{naming.name.strip()}' could not be saved "
                f"to {self.preset_store.path}.",
                title=SAVE_ALIGNMENT_PRESET_DIALOG_TITLE,
                detail=f"{exc}",
            )
            return

        self.statusbar_message(
            f"Saved camera-alignment preset '{preset.name}' for {device_key}"
        )

    def apply_preset(self, preset):
        """Put ``preset`` on the live alignment: its endpoint becomes the
        loaded device's, the feed glides onto its scene quad without a
        jump, and the open panes' dots follow. A working alignment no
        preset holds is first saved as one, so it is never lost. Refused
        while a protocol runs or for another device's preset."""
        device_key = self.model.device_key
        parent = self._alignment_window()

        if not self.model.editable:
            warning(
                parent,
                "A protocol is running — the alignment cannot change until it stops.",
                title=APPLY_ALIGNMENT_PRESET_DIALOG_TITLE,
            )
            return

        if preset.device_key != device_key:
            warning(
                parent,
                f"'{preset.name}' was saved for {preset.device_key} — load that "
                f"device to apply it.",
                title=APPLY_ALIGNMENT_PRESET_DIALOG_TITLE,
            )
            return

        camera_quad, frame_size, note = self._preset_camera_quad_now(preset)
        mapping = self._item_mapping_for(frame_size) if camera_quad else None

        if camera_quad is not None and mapping is None:
            camera_quad, note = None, PRESET_NO_CAMERA_FRAME_NOTE

        try:
            kept = self._keep_working_alignment(preset)
            self.endpoint_store.save(device_key, preset.endpoint_quad)
        except (OSError, ValueError) as exc:
            logger.error(f"Could not apply alignment preset '{preset.name}': {exc}")
            error(
                parent,
                f"The alignment preset '{preset.name}' was not applied: the "
                f"current alignment could not be kept in {self.preset_store.path} "
                f"or the endpoint written to {self.endpoint_store.path}.",
                title=APPLY_ALIGNMENT_PRESET_DIALOG_TITLE,
                detail=f"{exc}",
            )
            return

        if camera_quad is not None:
            self._pin_and_glide(
                [
                    QPointF(*camera_point_to_item(point, mapping))
                    for point in camera_quad
                ],
                preset.scene_quad,
            )

        if self._alignment_model is not None:
            self._alignment_model.endpoint_pane.show_scene_quad(preset.endpoint_quad)

            if camera_quad is not None:
                self._alignment_model.outline_pane.show_raw_quad(camera_quad)

            if self._alignment_model.preset_table is not None:
                self._alignment_model.preset_table.live_frame_size = self._frame_size()

        message = f"Applied camera-alignment preset '{preset.name}'"

        if note:
            message = f"{message}: {note}"

        if kept is not None:
            message = f"Saved current alignment as '{kept.name}'. {message}"

        self.statusbar_message(message)

    def _keep_working_alignment(self, applied):
        """Save the device's working alignment as a preset when none of the
        device's presets holds it, so applying ``applied`` cannot lose it;
        return that preset, or None when nothing needed keeping.

        Raises ``OSError`` or ``ValueError`` when it could not be saved.
        """
        snapshot = self._live_alignment_snapshot()

        if snapshot is None or self._held_by_a_preset(snapshot):
            return None

        name = self.preset_store.unique_name(
            snapshot.device_key,
            BEFORE_APPLY_PRESET_NAME_TEMPLATE.format(
                name=applied.name,
                when=datetime.now().strftime(ALIGNMENT_PRESET_SAVED_AT_FORMAT),
            ),
        )

        return self.preset_store.save_named(name, snapshot)

    def _held_by_a_preset(self, snapshot):
        """Whether a preset of the device holds ``snapshot``'s endpoint and,
        when it has one, its camera alignment too."""
        return any(
            quads_close(preset.endpoint_quad, snapshot.endpoint_quad)
            and (
                snapshot.camera_quad is None
                or (
                    preset.camera_quad is not None
                    and quads_close(preset.camera_quad, snapshot.camera_quad)
                    and quads_close(preset.scene_quad, snapshot.scene_quad)
                )
            )
            for preset in self.preset_store.presets
            if preset.device_key == snapshot.device_key
        )

    def _preset_camera_quad_now(self, preset):
        """Return ``(camera quad, frame size, note)``: the preset's camera
        corners in pixels of the live frame (of its saved frame without
        one) and that frame's size — both None when they cannot be placed
        — and a note saying why, or how they were rescaled."""

        if preset.camera_quad is None:
            return None, None, PRESET_ENDPOINT_ONLY_NOTE

        if preset.frame_size is not None and not valid_frame_size(preset.frame_size):
            return None, None, PRESET_INVALID_FRAME_SIZE_NOTE

        frame_size = self._frame_size() or preset.frame_size

        if not valid_frame_size(frame_size):
            return None, None, PRESET_NO_CAMERA_FRAME_NOTE

        camera_quad = camera_quad_in_frame(
            preset.camera_quad, preset.frame_size, frame_size
        )

        if camera_quad is None:
            return None, None, PRESET_SHAPE_MISMATCH_NOTE

        if preset.frame_size is None or list(preset.frame_size) == list(frame_size):
            return camera_quad, frame_size, ""

        return (
            camera_quad,
            frame_size,
            PRESET_RESCALED_TEMPLATE.format(
                saved=_size_text(preset.frame_size), live=_size_text(frame_size)
            ),
        )

    def _pin_and_glide(self, item_points, scene_quad):
        """Pin camera corners (video-item coordinates) where they show on
        the feed now, then glide them onto ``scene_quad``."""
        perspective = self.model.camera_perspective
        current = perspective.transformation
        perspective.reference_rect = item_points
        perspective.transformed_reference_rect = [
            current.map(point) for point in item_points
        ]

        if self.model.mode != "camera-edit":
            self.model.mode = "camera-edit"

        self._start_align_animation([QPointF(x, y) for x, y in scene_quad])

    def _resolve_pending_pane_edits(self, parent):
        """Offer to confirm dots moved in the panes but not confirmed (or
        never confirmed); return whether saving should go on."""

        if not self._pane_edits_pending():
            return True

        nothing_confirmed = self.endpoint_store.load(self.model.device_key) is None

        choice = choose(
            parent,
            NOTHING_CONFIRMED_MESSAGE
            if nothing_confirmed
            else PENDING_PANE_EDITS_MESSAGE,
            title=SAVE_ALIGNMENT_PRESET_DIALOG_TITLE,
            choices=(
                [CONFIRM_AND_SAVE_CHOICE]
                if nothing_confirmed
                else [CONFIRM_AND_SAVE_CHOICE, SAVE_CONFIRMED_CHOICE]
            ),
        )

        if choice != CONFIRM_AND_SAVE_CHOICE:
            return choice == SAVE_CONFIRMED_CHOICE

        self._confirm_panes()

        # Still pending: the confirmation was cancelled or failed.
        return not self._pane_edits_pending()

    def _confirm_panes(self):
        """Confirm the panes' dots: the window's own macro (save the
        endpoint, stage the outline, Go To Endpoint) once the outline pane
        has a frame, else the endpoint alone."""
        alignment = self._alignment_model

        if alignment.outline_ready:
            alignment.confirm = True
        else:
            alignment.endpoint_pane.save = True

    def _pane_edits_pending(self):
        """Whether the open panes' dots differ from the confirmed state —
        or nothing is confirmed while the endpoint pane shows dots."""

        if self._alignment_model is None:
            return False

        outline_quad = self._alignment_model.outline_pane.raw_quad()
        live_camera_quad = self._current_camera_quad()
        endpoint_quad = self._alignment_model.endpoint_pane.scene_quad()
        saved_endpoint = self.endpoint_store.load(self.model.device_key)

        outline_moved = (
            outline_quad is not None
            and live_camera_quad is not None
            and not quads_close(outline_quad, live_camera_quad)
        )
        endpoint_moved = endpoint_quad is not None and (
            saved_endpoint is None or not quads_close(endpoint_quad, saved_endpoint)
        )

        return outline_moved or endpoint_moved

    def _live_alignment_snapshot(self):
        """The confirmed working alignment as an unsaved preset — endpoint
        only without a live camera quad — or None with no saved endpoint."""
        device_key = self.model.device_key
        endpoint = self.endpoint_store.load(device_key)

        if endpoint is None:
            return None

        camera_quad = self._current_camera_quad()
        scene_quad = self._live_scene_quad()

        if camera_quad is None or scene_quad is None:
            camera_quad, scene_quad = None, endpoint

        return AlignmentPreset(
            device_key=device_key,
            device_scene_rect=self._device_scene_rect(),
            camera_label=self._camera_label(),
            frame_size=self._frame_size() if camera_quad is not None else None,
            camera_quad=camera_quad,
            scene_quad=scene_quad,
            endpoint_quad=endpoint,
        )

    def _live_scene_quad(self):
        """Where the camera corners land in the scene ([[x, y] * 4]) —
        a running glide's targets, since that is what was confirmed — or
        None."""

        if self._align_timer is not None and self._align_timer.isActive():
            points = self._align_animation[1]
        else:
            points = self.model.camera_perspective.transformed_reference_rect

        if len(points) != 4:
            return None

        return [[point.x(), point.y()] for point in points]

    def _frame_size(self):
        """The camera's native frame size as [w, h], or None without one."""
        native = self.get_video_item().nativeSize()

        if native.isEmpty():
            return None

        return [float(native.width()), float(native.height())]

    def _item_mapping_for(self, frame_size):
        """The camera -> video-item mapping for a ``frame_size`` frame, or
        None when the frame or the video item has no size."""
        video_item = self.get_video_item()
        item_size = video_item.size()

        try:
            return camera_to_item_mapping(
                frame_size,
                (item_size.width(), item_size.height()),
                keep_aspect_ratio=video_item.aspectRatioMode()
                != Qt.AspectRatioMode.IgnoreAspectRatio,
            )
        except (TypeError, ValueError):
            return None

    def _device_scene_rect(self):
        """The device's scene rect as [x, y, w, h] while the window shows
        it, else None."""

        if self._alignment_model is None:
            return None

        rect = self._alignment_model.endpoint_pane.scene_rect

        if rect is None:
            return None

        return [rect.x(), rect.y(), rect.width(), rect.height()]

    def _camera_label(self):
        return self.get_camera_label() if self.get_camera_label is not None else ""

    def _default_preset_name(self, device_key):
        default_preset = self.preset_store.resolve_default(
            device_key, self._camera_label()
        )

        return default_preset.name if default_preset is not None else ""

    def _alignment_window(self):
        """The open alignment window's widget, to parent prompts; or None."""

        if self._alignment_ui is None:
            return None

        return self._alignment_ui.control

    def _refresh_presets(self):
        """Reread the presets. A file that cannot be read or written is
        reported and leaves them read-only this session rather than stop
        the window opening; an unreadable file set aside is reported
        once."""
        store = self.preset_store

        try:
            store.refresh()
        except OSError as exc:
            logger.error(f"Camera-alignment presets unavailable ({store.path}): {exc}")
            store.mark_unavailable(PRESETS_UNAVAILABLE_TEMPLATE.format(path=store.path))
            error(
                None,
                f"The camera-alignment presets at {store.path} could not be read "
                f"or written; they are read-only this session.",
                title="Camera Alignment",
                detail=f"{exc}",
            )
            return

        if store.unreadable_copy:
            warning(
                None,
                PRESETS_UNREADABLE_TEMPLATE.format(copy=store.unreadable_copy),
                title="Camera Alignment",
            )
            store.unreadable_copy = ""

    @observe("preset_store:presets, preset_store:defaults")
    def _show_default_preset_on_reset(self, event):
        """Keep the endpoint pane's Reset prompt naming the current
        default preset."""

        if self._alignment_model is not None:
            self._alignment_model.endpoint_pane.default_preset_name = (
                self._default_preset_name(self.model.device_key)
            )

    @observe("_alignment_model:preset_table:save_as_button")
    def _on_preset_save_as(self, event):
        self.save_current_as()

    @observe("_alignment_model:preset_table:apply_requested")
    def _on_preset_apply(self, event):
        preset = self.preset_store.get(event.new.preset_id)

        if preset is not None:
            self.apply_preset(preset)

    @observe("_alignment_model:preset_table:delete_button")
    def _on_preset_delete(self, event):
        row = self._alignment_model.preset_table.selected

        if row is None:
            return

        answer = confirm(
            self._alignment_window(),
            f"Delete the alignment preset '{row.name}' of {row.device_key}?",
            title=DELETE_ALIGNMENT_PRESET_DIALOG_TITLE,
        )

        if answer != YES:
            return

        try:
            self.preset_store.delete(row.preset_id)
        except (OSError, ValueError) as exc:
            logger.error(f"Could not delete alignment preset '{row.name}': {exc}")
            error(
                self._alignment_window(),
                f"The alignment preset '{row.name}' could not be deleted from "
                f"{self.preset_store.path}.",
                title=DELETE_ALIGNMENT_PRESET_DIALOG_TITLE,
                detail=f"{exc}",
            )

    @observe("model:editable")
    def _gate_preset_actions(self, event):
        """No preset is applied or saved while a protocol runs."""

        if self._alignment_model is not None and (
            self._alignment_model.preset_table is not None
        ):
            self._alignment_model.preset_table.editable = event.new


def _size_text(size):
    """A frame size as ``W×H``."""
    return f"{size[0]:g}×{size[1]:g}"
