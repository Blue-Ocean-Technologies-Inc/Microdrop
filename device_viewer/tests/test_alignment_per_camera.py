# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The live camera alignment remembered per camera and device (#963 stage
2): start-up hand-over, restore order on a camera switch and on a device
load, last-used updates on deliberate actions only, one undo entry per
restore, no "Before" preset, and the presets table following the camera.

Runs the real CameraAlignmentWorkflowController against a real
DeviceViewMainModel, a stub video item and stores in a temporary
directory; the preferences are an in-memory apptools Preferences."""

# Standard library imports.
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt.QtCore import QPointF, QSizeF, Qt
from pyface.qt.QtWidgets import QApplication
from pyface.undo.api import CommandStack, UndoManager

# Microdrop package imports.
from device_viewer.consts import LIVE_ALIGNMENT_SETUP_PREFERENCE
from device_viewer.controllers.camera_alignment_controller import (
    CameraAlignmentWorkflowController,
)
from device_viewer.controllers.device_viewer_publish_controller import (
    DeviceViewerPublishController,
)
from device_viewer.models.alignment_preset import AlignmentPreset
from device_viewer.models.alignment_preset_store import AlignmentPresetStore
from device_viewer.models.alignment_preset_table import AlignmentPresetTable
from device_viewer.models.camera import CameraModel
from device_viewer.models.camera_identity import CameraIdentity
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

DEVICES = Path(__file__).resolve().parents[1] / "resources" / "devices"

CAM_A = CameraIdentity(camera_id="usb#a", label="USB Camera")
CAM_B = CameraIdentity(camera_id="usb#b", label="USB Camera")

ENDPOINT = [[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]]

#: Two live alignments, as video-item points (the stub maps camera pixel
#: (x, y) to item (2x, 2y + 60)).
REFERENCE_A = [QPointF(20, 80), QPointF(220, 80), QPointF(220, 260), QPointF(20, 260)]
SCENE_A = [QPointF(3, 2), QPointF(97, 1), QPointF(99, 78), QPointF(1, 79)]
REFERENCE_B = [QPointF(40, 100), QPointF(240, 100), QPointF(240, 300), QPointF(40, 300)]
SCENE_B = [QPointF(10, 10), QPointF(90, 10), QPointF(90, 70), QPointF(10, 70)]


class StubEndpointPane(EndpointPane):
    def traits_init(self):
        pass


class StubOutlinePane(OutlinePane):
    def traits_init(self):
        pass


class StubVideoItem:
    """A 640x480 camera letterboxed into a 1280x1080 video item."""

    def nativeSize(self):
        return QSizeF(640, 480)

    def size(self):
        return QSizeF(1280, 1080)

    def aspectRatioMode(self):
        return Qt.AspectRatioMode.KeepAspectRatio


@pytest.fixture
def model():
    # The Go To Endpoint glide runs on a QTimer.
    QApplication.instance() or QApplication([])

    undo_manager = UndoManager(active_stack=CommandStack())
    undo_manager.active_stack.undo_manager = undo_manager
    model = DeviceViewMainModel(
        undo_manager=undo_manager,
        preferences=DeviceViewerPreferences(preferences=Preferences()),
        camera_perspective=PerspectiveModel(),
    )
    model.electrodes.set_electrodes_from_svg_file(str(DEVICES / "2x3device.svg"))

    return model


@pytest.fixture
def controller(model, tmp_path):
    endpoint_store = CameraEndpointStore(path=tmp_path / "endpoints.json")

    with (
        patch(f"{CONTROLLER_MODULE}.warning"),
        patch(f"{CONTROLLER_MODULE}.error"),
    ):
        yield CameraAlignmentWorkflowController(
            model=model,
            endpoint_store=endpoint_store,
            preset_store=AlignmentPresetStore(
                path=tmp_path / "alignment_presets.json",
                endpoint_store=endpoint_store,
            ),
            statusbar_message=MagicMock(),
            get_video_item=StubVideoItem,
        )


@pytest.fixture
def cameras():
    return CameraModel(camera_identity=CAM_A)


def _set_live(model, reference, scene):
    model.camera_perspective.reference_rect = list(reference)
    model.camera_perspective.transformed_reference_rect = list(scene)


def _live(model):
    perspective = model.camera_perspective

    return (
        [point.toTuple() for point in perspective.reference_rect],
        [point.toTuple() for point in perspective.transformed_reference_rect],
    )


def _tuples(points):
    return [point.toTuple() for point in points]


def _status(controller):
    return controller.statusbar_message.call_args.args[0]


def _take_charge(controller, model, cameras):
    """Start-up: aligned for camera A, the pane hands the panel over."""
    _set_live(model, REFERENCE_A, SCENE_A)
    controller.camera_model = cameras


def _switch(cameras, camera):
    cameras.camera_identity = camera


def _camera_preset(camera, scope, scene=SCENE_B, reference=REFERENCE_B):
    return AlignmentPreset(
        name="bench",
        scope=scope,
        device_key="2x3device",
        camera_id=camera.camera_id,
        camera_label=camera.label,
        frame_size=[640.0, 480.0],
        camera_quad=[[(p.x()) / 2, (p.y() - 60) / 2] for p in reference],
        scene_quad=[list(point.toTuple()) for point in scene],
        endpoint_quad=ENDPOINT,
    )


# ---------------------------------------------------------------------- #
# Start-up
# ---------------------------------------------------------------------- #
def test_first_start_adopts_the_live_alignment(controller, model, cameras):
    _take_charge(controller, model, cameras)

    record = controller.preset_store.last_used_for(CAM_A, "2x3device")
    setup = json.loads(
        model.preferences.preferences.get(LIVE_ALIGNMENT_SETUP_PREFERENCE)
    )

    assert _live(model) == (_tuples(REFERENCE_A), _tuples(SCENE_A))
    assert record.camera_quad == [
        [10.0, 10.0],
        [110.0, 10.0],
        [110.0, 100.0],
        [10.0, 100.0],
    ]
    assert setup == {
        "camera_id": "usb#a",
        "camera_label": "USB Camera",
        "device_key": "2x3device",
        "owned": True,
    }


def test_start_with_the_same_setup_keeps_the_live_alignment(controller, model, cameras):
    controller.preset_store.remember_last_used(_camera_preset(CAM_A, "camera_device"))
    model.preferences.preferences.set(
        LIVE_ALIGNMENT_SETUP_PREFERENCE,
        json.dumps(
            {
                "camera_id": "usb#a",
                "camera_label": "",
                "device_key": "2x3device",
                "owned": True,
            }
        ),
    )

    _take_charge(controller, model, cameras)

    # Hand-tuned since the last record: kept, not overwritten by it.
    assert _live(model) == (_tuples(REFERENCE_A), _tuples(SCENE_A))


def test_start_with_another_camera_restores_this_cameras(controller, model, cameras):
    controller.preset_store.remember_last_used(_camera_preset(CAM_A, "camera_device"))
    model.preferences.preferences.set(
        LIVE_ALIGNMENT_SETUP_PREFERENCE,
        json.dumps(
            {
                "camera_id": "usb#b",
                "camera_label": "",
                "device_key": "2x3device",
                "owned": True,
            }
        ),
    )

    _take_charge(controller, model, cameras)

    assert _live(model) == (_tuples(REFERENCE_B), _tuples(SCENE_B))


# ---------------------------------------------------------------------- #
# Camera switch: (a) last used, (b) default, (c) nothing saved
# ---------------------------------------------------------------------- #
def test_camera_switch_with_nothing_saved_keeps_and_flags(controller, model, cameras):
    _take_charge(controller, model, cameras)

    _switch(cameras, CAM_B)

    assert _live(model) == (_tuples(REFERENCE_A), _tuples(SCENE_A))
    assert "No saved alignment for camera" in _status(controller)
    assert controller._setup_notice
    # Camera A's alignment is not stamped as camera B's on the way out.
    _switch(cameras, CAM_A)

    assert controller.preset_store.last_used_for(CAM_B, "2x3device") is None


def test_camera_switch_round_trip_restores_each_cameras_last_used(
    controller, model, cameras
):
    _take_charge(controller, model, cameras)
    _switch(cameras, CAM_B)

    # The user aligns camera B by hand.
    _set_live(model, REFERENCE_B, SCENE_B)

    _switch(cameras, CAM_A)

    assert _live(model) == (_tuples(REFERENCE_A), _tuples(SCENE_A))
    assert "last used" in _status(controller)
    assert controller._setup_notice == ""

    _switch(cameras, CAM_B)

    assert _live(model) == (_tuples(REFERENCE_B), _tuples(SCENE_B))


def test_identical_cameras_are_told_apart(controller, model, cameras):
    _take_charge(controller, model, cameras)
    _switch(cameras, CAM_B)
    _set_live(model, REFERENCE_B, SCENE_B)
    _switch(cameras, CAM_A)

    a = controller.preset_store.last_used_for(CAM_A, "2x3device")
    b = controller.preset_store.last_used_for(CAM_B, "2x3device")

    assert a.id != b.id
    assert a.scene_quad != b.scene_quad


def test_last_used_outranks_the_default(controller, model, cameras):
    preset = controller.preset_store.save_named(
        "bench", _camera_preset(CAM_B, "camera_device", scene=SCENE_A)
    )
    controller.preset_store.set_default(preset.id)
    _take_charge(controller, model, cameras)
    _switch(cameras, CAM_B)

    # (b): no last used for camera B yet — its default.
    assert _live(model)[1] == _tuples(SCENE_A)
    assert "default alignment preset 'bench'" in _status(controller)

    _set_live(model, REFERENCE_B, SCENE_B)
    _switch(cameras, CAM_A)
    _switch(cameras, CAM_B)

    # (a): now the alignment last used with camera B.
    assert _live(model) == (_tuples(REFERENCE_B), _tuples(SCENE_B))


def test_device_default_applies_to_any_camera(controller, model, cameras):
    preset = controller.preset_store.save_named(
        "bench", _camera_preset(CAM_A, "device")
    )
    controller.preset_store.set_default(preset.id)
    _take_charge(controller, model, cameras)

    _switch(cameras, CAM_B)

    assert _live(model) == (_tuples(REFERENCE_B), _tuples(SCENE_B))
    assert controller.endpoint_store.load("2x3device") == ENDPOINT


def test_restore_creates_no_before_preset(controller, model, cameras):
    controller.endpoint_store.save(
        "2x3device", [[5.0, 5.0], [95.0, 5.0], [95.0, 75.0], [5.0, 75.0]]
    )
    preset = controller.preset_store.save_named(
        "bench", _camera_preset(CAM_B, "camera_device")
    )
    controller.preset_store.set_default(preset.id)
    _take_charge(controller, model, cameras)

    _switch(cameras, CAM_B)

    names = [p.name for p in controller.preset_store.presets if p.kind == "named"]

    assert not any(name.startswith("Before") for name in names)


def test_restore_stays_off_the_undo_stack(controller, model, cameras):
    DeviceViewerPublishController(model=model)
    _take_charge(controller, model, cameras)
    _switch(cameras, CAM_B)
    _set_live(model, REFERENCE_B, SCENE_B)
    stack = model.undo_manager.active_stack
    entries_before = len(stack._stack)
    undo_name_before = stack.undo_name

    _switch(cameras, CAM_A)

    assert _live(model) == (_tuples(REFERENCE_A), _tuples(SCENE_A))
    assert len(stack._stack) == entries_before
    assert stack.undo_name == undo_name_before


def test_undo_after_a_restore_cannot_hand_over_another_cameras_alignment(
    controller, model, cameras
):
    DeviceViewerPublishController(model=model)
    _take_charge(controller, model, cameras)
    _switch(cameras, CAM_B)
    _set_live(model, REFERENCE_B, SCENE_B)
    _switch(cameras, CAM_A)

    # The restore is not on the stack: undo cannot put camera B's
    # alignment back under camera A.
    model.undo_manager.undo()
    _switch(cameras, CAM_B)

    assert controller.preset_store.last_used_for(CAM_A, "2x3device").scene_quad == (
        [list(point.toTuple()) for point in SCENE_A]
    )


def test_a_start_up_restore_pushes_no_undo_entry(controller, model, cameras):
    DeviceViewerPublishController(model=model)
    controller.preset_store.remember_last_used(_camera_preset(CAM_A, "camera_device"))
    model.preferences.preferences.set(
        LIVE_ALIGNMENT_SETUP_PREFERENCE,
        json.dumps(
            {
                "camera_id": "usb#b",
                "camera_label": "",
                "device_key": "2x3device",
                "owned": False,
            }
        ),
    )
    _set_live(model, REFERENCE_A, SCENE_A)
    stack = model.undo_manager.active_stack
    entries_before = len(stack._stack)

    controller.camera_model = cameras

    assert _live(model) == (_tuples(REFERENCE_B), _tuples(SCENE_B))
    assert len(stack._stack) == entries_before


def test_restore_waits_for_a_running_protocol(controller, model, cameras):
    _take_charge(controller, model, cameras)
    _switch(cameras, CAM_B)
    _set_live(model, REFERENCE_B, SCENE_B)
    model.editable = False

    _switch(cameras, CAM_A)

    assert _live(model) == (_tuples(REFERENCE_B), _tuples(SCENE_B))
    assert "when the protocol stops" in _status(controller)

    model.editable = True

    assert _live(model) == (_tuples(REFERENCE_A), _tuples(SCENE_A))


# ---------------------------------------------------------------------- #
# Device load
# ---------------------------------------------------------------------- #
def test_device_load_remembers_the_outgoing_and_restores_the_new(
    controller, model, cameras
):
    _take_charge(controller, model, cameras)
    _set_live(model, REFERENCE_B, SCENE_B)

    # A new device: nothing saved for camera A there.
    model.electrodes.set_electrodes_from_svg_file(str(DEVICES / "90_pin_array.svg"))
    controller.device_loaded()

    assert controller.preset_store.last_used_for(CAM_A, "2x3device").scene_quad == [
        list(point.toTuple()) for point in SCENE_B
    ]
    assert "No saved alignment" in _status(controller)

    _set_live(model, REFERENCE_A, SCENE_A)
    model.electrodes.set_electrodes_from_svg_file(str(DEVICES / "2x3device.svg"))
    controller.device_loaded()

    assert _live(model) == (_tuples(REFERENCE_B), _tuples(SCENE_B))
    assert controller.preset_store.last_used_for(CAM_A, "90_pin_array") is not None


# ---------------------------------------------------------------------- #
# Last used changes only on deliberate actions
# ---------------------------------------------------------------------- #
def test_a_drag_alone_does_not_rewrite_the_last_used(controller, model, cameras):
    _take_charge(controller, model, cameras)
    before = controller.preset_store.path.read_bytes()

    _set_live(model, REFERENCE_B, SCENE_B)

    assert controller.preset_store.path.read_bytes() == before


def test_confirmed_glide_updates_the_last_used(controller, model, cameras):
    _take_charge(controller, model, cameras)
    _set_live(model, REFERENCE_A, SCENE_A)

    controller._start_align_animation(list(SCENE_B), steps=1)
    controller._on_align_animation_tick()

    record = controller.preset_store.last_used_for(CAM_A, "2x3device")

    assert record.scene_quad == [list(point.toTuple()) for point in SCENE_B]


def test_reset_camera_perspective_forgets_the_last_used(controller, model, cameras):
    _take_charge(controller, model, cameras)

    model.camera_perspective.reset()

    assert controller.preset_store.last_used_for(CAM_A, "2x3device") is None


# ---------------------------------------------------------------------- #
# The open window follows the camera
# ---------------------------------------------------------------------- #
def test_presets_table_follows_a_camera_switch(controller, model, cameras):
    controller.preset_store.save_named("bench", _camera_preset(CAM_A, "camera_device"))
    _take_charge(controller, model, cameras)
    table = AlignmentPresetTable(
        store=controller.preset_store,
        current_device_key="2x3device",
        current_camera=CAM_A,
    )
    controller._alignment_model = CameraAlignmentModel(
        endpoint_pane=StubEndpointPane(),
        outline_pane=StubOutlinePane(),
        preset_table=table,
    )
    (row,) = table.rows

    assert row.warning == ""

    _switch(cameras, CAM_B)

    assert table.current_camera.same_as(CAM_B)
    assert "select that camera" in row.warning
    assert "No saved alignment" in table.setup_notice

    _switch(cameras, CAM_A)
    controller.live_frame_size = [1920.0, 1080.0]

    assert "shape differs" in row.warning
    assert table.setup_notice == ""


# ---------------------------------------------------------------------- #
# Review of #988: regressions
# ---------------------------------------------------------------------- #
def _scene(points):
    return [list(point.toTuple()) for point in points]


def _land_glide(controller):
    """Run the Go To Endpoint glide to its end without a timer."""

    while controller._align_timer is not None and controller._align_timer.isActive():
        controller._on_align_animation_tick()


def test_apply_keeps_a_working_alignment_only_last_used_holds(
    controller, model, cameras
):
    controller.endpoint_store.save("2x3device", ENDPOINT)
    _take_charge(controller, model, cameras)
    preset = controller.preset_store.save_named(
        "bench", _camera_preset(CAM_A, "camera_device")
    )

    controller.apply_preset(preset)
    _land_glide(controller)

    # The working alignment survives as a "Before" preset, although the
    # last-used record held it until the glide landed.
    (kept,) = [
        preset
        for preset in controller.preset_store.named_for("2x3device")
        if preset.name.startswith('Before "bench"')
    ]

    assert kept.scene_quad == _scene(SCENE_A)
    assert controller.preset_store.last_used_for(CAM_A, "2x3device").scene_quad == (
        _scene(SCENE_B)
    )


def test_align_mode_then_a_camera_switch_keeps_the_last_used(
    controller, model, cameras
):
    _take_charge(controller, model, cameras)

    # Align Camera Perspective clears the rects to place new ones.
    model.mode = "camera-place"
    _switch(cameras, CAM_B)

    assert controller.preset_store.last_used_for(CAM_A, "2x3device").scene_quad == (
        _scene(SCENE_A)
    )


def test_align_mode_then_a_device_load_keeps_the_last_used(controller, model, cameras):
    _take_charge(controller, model, cameras)

    model.mode = "camera-place"
    model.electrodes.set_electrodes_from_svg_file(str(DEVICES / "90_pin_array.svg"))
    controller.device_loaded()

    assert controller.preset_store.last_used_for(CAM_A, "2x3device").scene_quad == (
        _scene(SCENE_A)
    )


def test_a_glide_interrupted_by_a_camera_switch_stays_the_old_cameras(
    controller, model, cameras
):
    _take_charge(controller, model, cameras)
    controller._start_align_animation(list(SCENE_B), steps=3)
    controller._on_align_animation_tick()

    # Nothing saved for camera B: the restore places nothing.
    _switch(cameras, CAM_B)
    controller._on_align_animation_tick()
    controller._on_align_animation_tick()

    assert not controller._align_timer.isActive()
    assert controller.preset_store.last_used_for(CAM_B, "2x3device") is None
    # Camera A keeps what was being confirmed: the glide's targets.
    assert controller.preset_store.last_used_for(CAM_A, "2x3device").scene_quad == (
        _scene(SCENE_B)
    )


def test_a_glide_interrupted_by_a_device_load_stays_the_old_devices(
    controller, model, cameras
):
    _take_charge(controller, model, cameras)
    controller._start_align_animation(list(SCENE_B), steps=3)
    controller._on_align_animation_tick()

    model.electrodes.set_electrodes_from_svg_file(str(DEVICES / "90_pin_array.svg"))
    controller.device_loaded()
    controller._on_align_animation_tick()
    controller._on_align_animation_tick()

    assert controller.preset_store.last_used_for(CAM_A, "90_pin_array") is None
    assert controller.preset_store.last_used_for(CAM_A, "2x3device").scene_quad == (
        _scene(SCENE_B)
    )


#: The endpoint migrated into "2x3device endpoint", the device's default.
OLD_ENDPOINT = [[5.0, 5.0], [95.0, 5.0], [95.0, 75.0], [5.0, 75.0]]


def _migrate_an_endpoint_only_default(controller):
    controller.endpoint_store.save("2x3device", OLD_ENDPOINT)
    controller.preset_store.refresh()


def test_an_endpoint_only_default_never_overwrites_the_endpoint(
    controller, model, cameras
):
    _migrate_an_endpoint_only_default(controller)
    _take_charge(controller, model, cameras)

    # The user confirms a newer endpoint, then switches camera.
    controller.endpoint_store.save("2x3device", ENDPOINT)
    _switch(cameras, CAM_B)

    assert controller.endpoint_store.load("2x3device") == ENDPOINT
    assert _live(model) == (_tuples(REFERENCE_A), _tuples(SCENE_A))
    assert "No saved alignment" in _status(controller)


def test_restore_falls_through_an_endpoint_only_default(controller, model, cameras):
    _migrate_an_endpoint_only_default(controller)
    mount = controller.preset_store.save_named(
        "mount", _camera_preset(CAM_B, "camera", scene=SCENE_B)
    )
    controller.preset_store.set_default(mount.id)
    _take_charge(controller, model, cameras)

    _switch(cameras, CAM_B)

    # The device default (endpoint only) is skipped: the camera's
    # any-device default is reached.
    assert _live(model) == (_tuples(REFERENCE_B), _tuples(SCENE_B))
    assert "'mount'" in _status(controller)
    assert controller.endpoint_store.load("2x3device") == OLD_ENDPOINT


def test_no_camera_at_start_up_leaves_adoption_to_the_first_camera(controller, model):
    cameras = CameraModel()
    _set_live(model, REFERENCE_A, SCENE_A)

    # "<No Camera>" at start-up decides nothing...
    controller.camera_model = cameras

    assert model.preferences.preferences.get(LIVE_ALIGNMENT_SETUP_PREFERENCE) is None

    # ...the first camera selected adopts the alignment.
    _switch(cameras, CAM_A)

    assert controller.preset_store.last_used_for(CAM_A, "2x3device").scene_quad == (
        _scene(SCENE_A)
    )
    assert _live(model) == (_tuples(REFERENCE_A), _tuples(SCENE_A))


def _last_session(model, camera, owned=True):
    model.preferences.preferences.set(
        LIVE_ALIGNMENT_SETUP_PREFERENCE,
        json.dumps(
            {
                "camera_id": camera.camera_id,
                "camera_label": camera.label,
                "device_key": "2x3device",
                "owned": owned,
            }
        ),
    )


def test_start_up_with_another_camera_keeps_the_last_sessions_tuning(
    controller, model, cameras
):
    # Last session: camera B, recorded once, then hand-tuned to A's rects
    # before quitting.
    controller.preset_store.remember_last_used(_camera_preset(CAM_B, "camera_device"))
    _last_session(model, CAM_B)
    _set_live(model, REFERENCE_A, SCENE_A)

    controller.camera_model = cameras

    # Camera B keeps the hand tuning (converted through its 640x480 frame).
    kept = controller.preset_store.last_used_for(CAM_B, "2x3device")

    assert kept.scene_quad == _scene(SCENE_A)
    assert kept.camera_quad == [
        [10.0, 10.0],
        [110.0, 10.0],
        [110.0, 100.0],
        [10.0, 100.0],
    ]


def test_start_up_does_not_keep_an_alignment_the_last_camera_did_not_own(
    controller, model, cameras
):
    controller.preset_store.remember_last_used(_camera_preset(CAM_B, "camera_device"))
    _last_session(model, CAM_B, owned=False)
    _set_live(model, REFERENCE_A, SCENE_A)

    controller.camera_model = cameras

    assert controller.preset_store.last_used_for(CAM_B, "2x3device").scene_quad == (
        _scene(SCENE_B)
    )
