# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for CameraAlignmentWorkflowController (#781): the camera-alignment
endpoint workflow moved off the dock pane, and the alignment presets (#963).
Runs against a real DeviceViewMainModel with stub alignment panes (no canvas,
no dialog) and the pyface_wrapper dialogs patched.
"""

# Standard library imports.
from pathlib import Path
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import QPointF, QSizeF, Qt
from pyface.undo.api import CommandStack, UndoManager

# Microdrop package imports.
from device_viewer.controllers.camera_alignment_controller import (
    CameraAlignmentWorkflowController,
)
from device_viewer.models.alignment_preset import AlignmentPreset
from device_viewer.models.alignment_preset_store import AlignmentPresetStore
from device_viewer.models.alignment_preset_table import AlignmentPresetTable
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.models.perspective import PerspectiveModel
from device_viewer.preferences import DeviceViewerPreferences
from device_viewer.utils.camera_endpoints import CameraEndpointStore
from device_viewer.views.camera_alignment_view.alignment_dialog import (
    CameraAlignmentModel,
)
from device_viewer.views.camera_alignment_view.alignment_panes import (
    EndpointPane,
    OutlinePane,
)

CONTROLLER_MODULE = "device_viewer.controllers.camera_alignment_controller"

BUNDLED_2X3 = (
    Path(__file__).resolve().parents[1] / "resources" / "devices" / "2x3device.svg"
)

ENDPOINT = [[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]]

START_POINTS = [QPointF(1, 1), QPointF(9, 1), QPointF(9, 9), QPointF(1, 9)]

CAMERA_QUAD = [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0]]
SCENE_QUAD = [[3.0, 2.0], [97.0, 1.0], [99.0, 78.0], [1.0, 79.0]]

#: (scale_x, scale_y, offset_x, offset_y) for the stubbed letterbox.
MAPPING = (2.0, 2.0, 10.0, 0.0)


class StubEndpointPane(EndpointPane):
    """An endpoint pane without its Qt canvas: only its events matter here."""

    def traits_init(self):
        pass


class StubOutlinePane(OutlinePane):
    """An outline pane without its Qt canvas: only its events matter here."""

    def traits_init(self):
        pass


class StubVideoItem:
    """A 640x480 camera letterboxed into a 1280x1080 video item: scale 2,
    60 px bars top and bottom."""

    def __init__(self, native=QSizeF(640, 480)):
        self.native = native

    def nativeSize(self):
        return self.native

    def size(self):
        return QSizeF(1280, 1080)

    def aspectRatioMode(self):
        return Qt.AspectRatioMode.KeepAspectRatio


@pytest.fixture
def model():
    undo_manager = UndoManager(active_stack=CommandStack())
    undo_manager.active_stack.undo_manager = undo_manager

    # A fresh perspective: the trait's default instance is shared by every
    # model, so rects would leak between tests.
    model = DeviceViewMainModel(
        undo_manager=undo_manager,
        preferences=DeviceViewerPreferences(),
        camera_perspective=PerspectiveModel(),
    )
    model.electrodes.set_electrodes_from_svg_file(str(BUNDLED_2X3))

    return model


@pytest.fixture
def dialogs():
    """Patch the pyface_wrapper dialogs the controller raises."""
    with (
        patch(f"{CONTROLLER_MODULE}.warning") as warning,
        patch(f"{CONTROLLER_MODULE}.error") as error,
        patch(f"{CONTROLLER_MODULE}.choose") as choose,
        patch(f"{CONTROLLER_MODULE}.confirm") as confirm,
    ):
        yield MagicMock(warning=warning, error=error, choose=choose, confirm=confirm)


@pytest.fixture
def controller(model, tmp_path, dialogs):
    endpoint_store = CameraEndpointStore(path=tmp_path / "endpoints.json")
    preset_store = AlignmentPresetStore(
        path=tmp_path / "alignment_presets.json", endpoint_store=endpoint_store
    )
    controller = CameraAlignmentWorkflowController(
        model=model,
        endpoint_store=endpoint_store,
        preset_store=preset_store,
        statusbar_message=MagicMock(),
        get_camera_label=lambda: "Cam 1",
    )
    controller._alignment_model = CameraAlignmentModel(
        endpoint_pane=StubEndpointPane(),
        outline_pane=StubOutlinePane(),
        preset_table=AlignmentPresetTable(
            store=preset_store, current_device_key=model.device_key
        ),
    )

    return controller


def _preset(device_key="2x3device", camera_quad=CAMERA_QUAD):
    return AlignmentPreset(
        name="bench",
        device_key=device_key,
        frame_size=[640.0, 480.0],
        camera_quad=camera_quad,
        scene_quad=SCENE_QUAD,
        endpoint_quad=ENDPOINT,
    )


def test_device_key_is_the_svg_stem(model):
    assert model.device_key == "2x3device"


def test_device_key_is_empty_without_a_device(model):
    model.electrodes.svg_model = None

    assert model.device_key == ""


def test_endpoint_saved_persists_for_the_current_device(controller):
    controller._alignment_model.endpoint_pane.endpoint_saved = ENDPOINT

    assert controller.endpoint_store.load("2x3device") == ENDPOINT
    controller.statusbar_message.assert_called_once_with(
        "Saved camera-alignment endpoint for 2x3device"
    )


def test_quad_accepted_stages_points_and_enters_camera_edit(controller, model):
    model.mode = "edit"

    with patch.object(
        CameraAlignmentWorkflowController,
        "_camera_to_item_mapping",
        return_value=(2.0, 2.0, 10.0, 0.0),
    ):
        controller._alignment_model.outline_pane.quad_accepted = [
            [0, 0],
            [5, 0],
            [5, 5],
            [0, 5],
        ]

    perspective = model.camera_perspective

    assert perspective.reference_rect == [
        QPointF(10, 0),
        QPointF(20, 0),
        QPointF(20, 10),
        QPointF(10, 10),
    ]
    assert len(perspective.transformed_reference_rect) == 4
    assert model.mode == "camera-edit"


def test_quad_accepted_without_camera_frames_reports_error(controller, model, dialogs):
    model.mode = "edit"

    with patch.object(
        CameraAlignmentWorkflowController,
        "_camera_to_item_mapping",
        side_effect=RuntimeError("no camera frames yet"),
    ):
        controller._alignment_model.outline_pane.quad_accepted = ENDPOINT

    dialogs.error.assert_called_once()
    assert model.mode == "edit"


def test_alignment_confirmed_glides_to_the_saved_endpoint(controller, model):
    controller.endpoint_store.save("2x3device", ENDPOINT)
    model.camera_perspective.transformed_reference_rect = START_POINTS
    model.mode = "edit"

    with patch.object(
        CameraAlignmentWorkflowController, "_start_align_animation"
    ) as animate:
        controller._alignment_model.alignment_confirmed = True

    animate.assert_called_once_with([QPointF(x, y) for x, y in ENDPOINT])
    assert model.mode == "camera-edit"


def test_go_to_endpoint_without_saved_endpoint_warns(controller, dialogs):
    with patch.object(
        CameraAlignmentWorkflowController, "_start_align_animation"
    ) as animate:
        controller.go_to_endpoint()

    dialogs.warning.assert_called_once()
    animate.assert_not_called()


def test_go_to_endpoint_without_start_points_warns(controller, model, dialogs):
    controller.endpoint_store.save("2x3device", ENDPOINT)
    model.camera_perspective.transformed_reference_rect = []

    with patch.object(
        CameraAlignmentWorkflowController, "_start_align_animation"
    ) as animate:
        controller.go_to_endpoint()

    dialogs.warning.assert_called_once()
    animate.assert_not_called()


def test_close_alignment_dialog_drops_the_dialog_model(controller):
    controller.close_alignment_dialog()

    assert controller._alignment_model is None


def test_apply_preset_writes_endpoint_and_glides_the_feed(controller, model):
    model.mode = "edit"

    with (
        patch.object(
            CameraAlignmentWorkflowController,
            "_camera_to_item_mapping",
            return_value=MAPPING,
        ),
        patch.object(
            CameraAlignmentWorkflowController, "_start_align_animation"
        ) as animate,
    ):
        controller.apply_preset(_preset())

    perspective = model.camera_perspective
    item_points = [QPointF(10, 0), QPointF(20, 0), QPointF(20, 10), QPointF(10, 10)]

    assert controller.endpoint_store.load("2x3device") == ENDPOINT
    assert perspective.reference_rect == item_points
    # Pinned where they showed (identity transform): no jump before the glide.
    assert perspective.transformed_reference_rect == item_points
    animate.assert_called_once_with([QPointF(x, y) for x, y in SCENE_QUAD])
    assert model.mode == "camera-edit"
    assert controller._alignment_model.outline_pane.initial_quad == CAMERA_QUAD


def test_apply_preset_is_refused_while_a_protocol_runs(controller, model, dialogs):
    model.camera_perspective.transformed_reference_rect = START_POINTS
    model.editable = False

    with patch.object(
        CameraAlignmentWorkflowController, "_start_align_animation"
    ) as animate:
        controller.apply_preset(_preset())

    dialogs.warning.assert_called_once()
    animate.assert_not_called()
    assert controller.endpoint_store.load("2x3device") is None
    assert model.camera_perspective.transformed_reference_rect == START_POINTS


def test_presets_table_cannot_apply_while_a_protocol_runs(controller, model):
    table = controller._alignment_model.preset_table

    model.editable = False

    assert not table.editable

    model.editable = True

    assert table.editable


def test_apply_preset_of_another_device_is_refused(controller, dialogs):
    controller.apply_preset(_preset(device_key="other-device"))

    dialogs.warning.assert_called_once()
    assert controller.endpoint_store.load("2x3device") is None


def test_apply_endpoint_only_preset_leaves_the_feed(controller, model):
    with patch.object(
        CameraAlignmentWorkflowController, "_start_align_animation"
    ) as animate:
        controller.apply_preset(_preset(camera_quad=None))

    assert controller.endpoint_store.load("2x3device") == ENDPOINT
    assert model.camera_perspective.reference_rect == []
    animate.assert_not_called()


def test_save_captures_raw_pixels_from_the_reference_rect(controller, model):
    controller.get_video_item = StubVideoItem
    controller.endpoint_store.save("2x3device", ENDPOINT)
    perspective = model.camera_perspective
    perspective.reference_rect = [
        QPointF(20, 80),
        QPointF(220, 80),
        QPointF(220, 260),
        QPointF(20, 260),
    ]
    perspective.transformed_reference_rect = [QPointF(x, y) for x, y in SCENE_QUAD]

    with patch(f"{CONTROLLER_MODULE}.ask_alignment_preset_name", return_value=False):
        controller.save_current_as()

    # The endpoint saved before any preset was migrated alongside.
    preset = controller.preset_store.find_named("2x3device", "alignment-1")

    assert preset.camera_quad == [
        [10.0, 10.0],
        [110.0, 10.0],
        [110.0, 100.0],
        [10.0, 100.0],
    ]
    assert preset.scene_quad == SCENE_QUAD
    assert preset.endpoint_quad == ENDPOINT
    assert preset.frame_size == [640.0, 480.0]
    assert preset.camera_label == "Cam 1"


def test_save_without_camera_frames_is_endpoint_only(controller, model):
    controller.get_video_item = lambda: StubVideoItem(native=QSizeF())
    controller.endpoint_store.save("2x3device", ENDPOINT)
    model.camera_perspective.reference_rect = START_POINTS
    model.camera_perspective.transformed_reference_rect = START_POINTS

    with patch(f"{CONTROLLER_MODULE}.ask_alignment_preset_name", return_value=False):
        controller.save_current_as()

    # The endpoint saved before any preset was migrated alongside.
    preset = controller.preset_store.find_named("2x3device", "alignment-1")

    assert preset.is_endpoint_only
    assert preset.scene_quad == ENDPOINT
    assert preset.frame_size is None


def test_save_cancelled_at_the_naming_dialog_saves_nothing(controller):
    controller.get_video_item = StubVideoItem
    controller.endpoint_store.save("2x3device", ENDPOINT)

    with patch(f"{CONTROLLER_MODULE}.ask_alignment_preset_name", return_value=None):
        controller.save_current_as()

    assert controller.preset_store.find_named("2x3device", "alignment-1") is None


def test_closing_the_dialog_detaches_the_table_from_the_store(controller):
    table = controller._alignment_model.preset_table

    controller.close_alignment_dialog()

    assert table.store is None
