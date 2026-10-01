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
endpoint workflow moved off the dock pane. Runs against a real
DeviceViewMainModel with stub alignment panes (no canvas, no dialog) and the
pyface_wrapper dialogs patched.
"""

# Standard library imports.
from pathlib import Path
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import QPointF
from pyface.undo.api import CommandStack, UndoManager

# Microdrop package imports.
from device_viewer.controllers.camera_alignment_controller import (
    CameraAlignmentWorkflowController,
)
from device_viewer.models.main_model import DeviceViewMainModel
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


class StubEndpointPane(EndpointPane):
    """An endpoint pane without its Qt canvas: only its events matter here."""

    def traits_init(self):
        pass


class StubOutlinePane(OutlinePane):
    """An outline pane without its Qt canvas: only its events matter here."""

    def traits_init(self):
        pass


@pytest.fixture
def model():
    undo_manager = UndoManager(active_stack=CommandStack())
    undo_manager.active_stack.undo_manager = undo_manager

    model = DeviceViewMainModel(
        undo_manager=undo_manager, preferences=DeviceViewerPreferences()
    )
    model.electrodes.set_electrodes_from_svg_file(str(BUNDLED_2X3))

    return model


@pytest.fixture
def dialogs():
    """Patch the pyface_wrapper dialogs the controller raises."""
    with (
        patch(f"{CONTROLLER_MODULE}.warning") as warning,
        patch(f"{CONTROLLER_MODULE}.error") as error,
    ):
        yield MagicMock(warning=warning, error=error)


@pytest.fixture
def controller(model, tmp_path, dialogs):
    controller = CameraAlignmentWorkflowController(
        model=model,
        endpoint_store=CameraEndpointStore(path=tmp_path / "endpoints.json"),
        statusbar_message=MagicMock(),
    )
    controller._alignment_model = CameraAlignmentModel(
        endpoint_pane=StubEndpointPane(),
        outline_pane=StubOutlinePane(),
    )

    return controller


def test_device_key_is_the_svg_stem(controller):
    assert controller.current_device_key() == "2x3device"


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
