# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Presets strip's Qt-free table and naming models against a real
store in a temporary directory."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.models.alignment_preset import AlignmentPreset
from device_viewer.models.alignment_preset_store import AlignmentPresetStore
from device_viewer.models.alignment_preset_table import (
    AlignmentPresetName,
    AlignmentPresetTable,
)
from device_viewer.models.camera_identity import CameraIdentity
from device_viewer.utils.camera_endpoints import CameraEndpointStore

ENDPOINT = [[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]]


def _snapshot(device_key):
    return AlignmentPreset(
        device_key=device_key, scene_quad=ENDPOINT, endpoint_quad=ENDPOINT
    )


@pytest.fixture
def store(tmp_path):
    store = AlignmentPresetStore(
        path=tmp_path / "alignment_presets.json",
        endpoint_store=CameraEndpointStore(path=tmp_path / "endpoints.json"),
    )
    store.refresh()
    store.save_named("beta", _snapshot("chip-a"))
    store.save_named("Alpha", _snapshot("chip-a"))
    store.save_named("other", _snapshot("chip-b"))

    return store


@pytest.fixture
def table(store):
    return AlignmentPresetTable(store=store, current_device_key="chip-a")


def _row(table, name):
    return next(row for row in table.rows if row.name == name)


def test_lists_only_the_loaded_device_by_default(table):
    assert [row.name for row in table.rows] == ["Alpha", "beta"]


def test_filter_off_lists_every_device_loaded_device_first(table):
    table.this_device_only = False

    assert [(row.device_key, row.name) for row in table.rows] == [
        ("chip-a", "Alpha"),
        ("chip-a", "beta"),
        ("chip-b", "other"),
    ]


def test_current_device_rows_are_marked_and_applicable(table):
    table.this_device_only = False

    alpha, other = _row(table, "Alpha"), _row(table, "other")

    assert alpha.is_current_device and alpha.applicable
    assert alpha.highlighted
    assert not other.is_current_device and not other.applicable
    assert not other.highlighted
    assert "chip-b" in other.warning
    assert alpha.warning == ""


def test_rows_are_not_highlighted_while_filtered(table):
    assert not any(row.highlighted for row in table.rows)


def test_can_apply_needs_an_applicable_selection_and_editable(table):
    table.this_device_only = False

    assert not table.can_apply

    table.selected = _row(table, "other")

    assert not table.can_apply

    table.selected = _row(table, "Alpha")

    assert table.can_apply

    table.editable = False

    assert not table.can_apply


def test_apply_button_requests_the_selected_row(table):
    requested = []
    table.observe(lambda event: requested.append(event.new), "apply_requested")
    table.selected = _row(table, "Alpha")

    table.apply_button = True

    assert requested == [table.selected]


def test_double_click_applies_except_on_the_name(table):
    requested = []
    table.observe(lambda event: requested.append(event.new), "apply_requested")
    alpha = _row(table, "Alpha")

    table.double_clicked = (alpha, SimpleNamespace(name="name"))

    assert requested == []

    table.double_clicked = (alpha, SimpleNamespace(name="saved_at_text"))

    assert requested == [alpha]


def test_in_place_rename_writes_through(table, store):
    alpha = _row(table, "Alpha")

    alpha.name = "gamma"

    assert store.get(alpha.preset_id).name == "gamma"
    assert alpha.saved_name == "gamma"


def test_name_errors_block_the_rename(table, store):
    alpha = _row(table, "Alpha")

    alpha.name = "BETA"

    assert alpha.name_error
    assert alpha.warning == alpha.name_error
    assert store.get(alpha.preset_id).name == "Alpha"

    alpha.name = "   "

    assert alpha.name_error


def test_same_name_on_another_device_is_no_error(table):
    alpha = _row(table, "Alpha")

    alpha.name = "other"

    assert alpha.name_error == ""


def test_default_is_one_hot_per_device(table, store):
    table.this_device_only = False
    alpha, beta, other = (_row(table, name) for name in ("Alpha", "beta", "other"))

    other.is_default = True
    alpha.is_default = True
    beta.is_default = True

    assert not alpha.is_default
    assert beta.is_default
    assert other.is_default
    assert store.resolve_default("chip-a").id == beta.preset_id
    assert store.resolve_default("chip-b").id == other.preset_id


def test_set_and_clear_default_buttons(table, store):
    table.selected = _row(table, "Alpha")

    table.set_default_button = True

    assert store.resolve_default("chip-a").id == table.selected.preset_id

    table.clear_default_button = True

    assert store.resolve_default("chip-a") is None


def test_rows_follow_store_changes_and_drop_a_deleted_selection(table, store):
    alpha = _row(table, "Alpha")
    table.selected = alpha

    store.delete(alpha.preset_id)

    assert [row.name for row in table.rows] == ["beta"]
    assert table.selected is None


def test_naming_model_validates_the_name():
    model = AlignmentPresetName(name="alignment-1")

    assert model.is_name_valid

    model.name = "  "

    assert not model.is_name_valid
    assert model.name_error


CAMERA_QUAD = [[0.0, 0.0], [640.0, 0.0], [640.0, 480.0], [0.0, 480.0]]


def _save_camera_preset(store, name, frame_size):
    return store.save_named(
        name,
        AlignmentPreset(
            device_key="chip-a",
            frame_size=frame_size,
            camera_quad=CAMERA_QUAD,
            scene_quad=ENDPOINT,
            endpoint_quad=ENDPOINT,
        ),
    )


def test_warning_while_the_camera_picture_shape_differs(table, store):
    _save_camera_preset(store, "vga", [640.0, 480.0])

    table.live_frame_size = [1280.0, 960.0]

    assert _row(table, "vga").warning == ""

    table.live_frame_size = [1920.0, 1080.0]

    assert "shape differs" in _row(table, "vga").warning
    assert _row(table, "vga").applicable
    # Endpoint-only presets have no picture to mismatch.
    assert _row(table, "Alpha").warning == ""


def test_warning_for_an_invalid_saved_frame_size(table, store):
    _save_camera_preset(store, "broken", [640.0, 0.0])

    assert "invalid" in _row(table, "broken").warning


CAM_A = CameraIdentity(camera_id="usb#a", label="USB Camera")
CAM_B = CameraIdentity(camera_id="usb#b", label="USB Camera")


def _save_for_camera(store, name, camera, scope, device_key="chip-a"):
    return store.save_named(
        name,
        AlignmentPreset(
            device_key=device_key,
            scope=scope,
            camera_id=camera.camera_id,
            camera_label=camera.label,
            frame_size=[640.0, 480.0],
            camera_quad=CAMERA_QUAD,
            scene_quad=ENDPOINT,
            endpoint_quad=ENDPOINT,
        ),
    )


def test_camera_column_and_tooltip(table, store):
    _save_for_camera(store, "cam a", CAM_A, "camera_device")
    _save_for_camera(store, "by name", CameraIdentity(label="ASI"), "camera_device")

    cam_a, by_name, alpha = (
        _row(table, name) for name in ("cam a", "by name", "Alpha")
    )

    assert cam_a.camera_text == "USB Camera"
    assert cam_a.camera_tooltip == "Camera id: usb#a"
    assert "matched by name" in by_name.camera_text
    assert "no stable id" in by_name.camera_tooltip
    assert alpha.camera_text == "Any camera"
    assert alpha.scope_text == "This device, any camera"


def test_presets_of_another_camera_are_listed_but_flagged(table, store):
    _save_for_camera(store, "cam a", CAM_A, "camera_device")
    table.current_camera = CAM_B

    row = _row(table, "cam a")

    assert not row.applicable
    assert "select that camera" in row.warning
    assert _row(table, "Alpha").applicable
    assert _row(table, "Alpha").highlighted

    # The camera switch while the window is open re-evaluates the rows.
    table.current_camera = CAM_A

    assert _row(table, "cam a").applicable
    assert _row(table, "cam a").warning == ""


def test_any_device_presets_of_the_camera_are_listed_on_every_device(table, store):
    _save_for_camera(store, "mount", CAM_A, "camera", device_key="chip-z")

    assert "mount" not in [row.name for row in table.rows]

    table.current_camera = CAM_A

    assert _row(table, "mount").applicable


def test_shape_warning_follows_the_live_frame(table, store):
    _save_for_camera(store, "cam a", CAM_A, "camera_device")
    table.current_camera = CAM_A

    assert _row(table, "cam a").warning == ""

    table.live_frame_size = [1920.0, 1080.0]

    assert "shape differs" in _row(table, "cam a").warning


def test_scope_picker_writes_through_and_offers_only_valid_scopes(table, store):
    preset = _save_for_camera(store, "cam a", CAM_A, "camera_device")
    table.current_camera = CAM_A
    table.selected = _row(table, "cam a")

    assert table.selected_scope == "This camera + device"
    assert table.selected_scope_choices == [
        "This camera + device",
        "This device, any camera",
        "This camera, any device",
    ]

    table.selected_scope = "This device, any camera"

    assert store.get(preset.id).scope == "device"

    # A preset saved without a camera can only be device-wide.
    table.selected = _row(table, "Alpha")

    assert table.selected_scope_choices == ["This device, any camera"]


def test_default_is_one_hot_per_slot_not_per_device(table, store):
    cam_a = _save_for_camera(store, "cam a", CAM_A, "camera_device")
    cam_b = _save_for_camera(store, "cam b", CAM_B, "camera_device")
    table.current_camera = CAM_A

    _row(table, "cam a").is_default = True
    _row(table, "cam b").is_default = True
    _row(table, "Alpha").is_default = True

    assert all(_row(table, name).is_default for name in ("cam a", "cam b", "Alpha"))
    assert store.resolve_default("chip-a", CAM_A).id == cam_a.id
    assert store.resolve_default("chip-a", CAM_B).id == cam_b.id
    assert "'cam a'" in table.setup_text


def test_setup_text_names_the_camera_and_its_default(table, store):
    assert "none selected" in table.setup_text
    assert table.setup_text.endswith("none")

    table.current_camera = CameraIdentity(label="ASI")

    assert "ASI (matched by name" in table.setup_text


def test_save_needs_editable_and_a_writable_store(table, store):
    assert table.can_save

    table.editable = False

    assert not table.can_save

    table.editable = True
    store.mark_unavailable("Presets are read-only this session.")

    assert not table.can_save
    assert table.notice == "Presets are read-only this session."
