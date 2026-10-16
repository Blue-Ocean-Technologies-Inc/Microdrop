# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the device viewer's keyboard shortcut table and dispatch."""

# Standard library imports.
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop package imports.
from device_viewer.consts import (
    ARROW_DIRECTIONS,
    KEYBOARD_SHORTCUT_GROUPS,
    KEYBOARD_SHORTCUTS,
)
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.preferences import DeviceViewerPreferences
from device_viewer.services.electrode_stepping_service import (
    ElectrodeSteppingService,
)
from device_viewer.services.keyboard_shortcut_service import (
    KeyboardShortcutService,
    cheat_sheet_rows,
    shortcut_label,
)
from dropbot_controller.consts import SET_REALTIME_MODE

Qt = QtCore.Qt


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def model():
    model = DeviceViewMainModel(preferences=DeviceViewerPreferences())
    model.mode = "edit"

    return model


@pytest.fixture
def service(model):
    return KeyboardShortcutService(
        model=model,
        stepping=ElectrodeSteppingService(model=model),
        interaction=MagicMock(),
        device_view=MagicMock(),
    )


@pytest.fixture
def stepping_spy(service):
    spy = MagicMock(spec=ElectrodeSteppingService)
    spy.map_direction_for_device_rotation.side_effect = lambda direction: direction
    service.stepping = spy

    return spy


@pytest.fixture
def publish_spy():
    with patch(
        "device_viewer.services.keyboard_shortcut_service.publish_message"
    ) as spy:
        yield spy


def key_event(key, modifiers=Qt.KeyboardModifier.NoModifier, release=False):
    if release:
        event_type = QtCore.QEvent.Type.KeyRelease
    else:
        event_type = QtCore.QEvent.Type.KeyPress

    return QtGui.QKeyEvent(event_type, key, modifiers)


def test_shortcut_sequences_are_unique():
    sequences = [row[0] for row in KEYBOARD_SHORTCUTS]

    assert len(sequences) == len(set(sequences))


def test_every_arrow_verb_has_all_four_directions():
    actions = {row[1] for row in KEYBOARD_SHORTCUTS}

    for verb in ("step", "extend", "shrink", "split", "draw_route"):
        assert {f"{verb}_{d}" for d in ARROW_DIRECTIONS} <= actions


def test_the_requested_modifier_mapping():
    by_sequence = {row[0]: row[1] for row in KEYBOARD_SHORTCUTS}

    assert by_sequence["Up"] == "step_up"
    assert by_sequence["Shift+Up"] == "extend_up"
    assert by_sequence["Ctrl+Up"] == "shrink_up"
    assert by_sequence["Alt+Up"] == "draw_route_up"
    assert by_sequence["Ctrl+Shift+Up"] == "split_up"


def test_every_row_names_a_known_group():
    assert {row[3] for row in KEYBOARD_SHORTCUTS} <= set(KEYBOARD_SHORTCUT_GROUPS)


def test_unmatched_key_returns_false(service):
    assert service.handle_key_press_event(key_event(Qt.Key.Key_Q)) is False


def test_every_table_action_resolves_to_a_handler(service):
    for _, action, _, _ in KEYBOARD_SHORTCUTS:
        assert service.resolve_action(action) is not None


def test_shift_arrow_extends_and_ctrl_arrow_shrinks(service, stepping_spy):
    service.handle_key_press_event(
        key_event(Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    )
    service.handle_key_press_event(
        key_event(Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
    )

    assert stepping_spy.extend_active_electrodes.call_args.args == ("right",)
    assert stepping_spy.shrink_active_electrodes.call_args.args == ("left",)


def test_releasing_a_split_modifier_resets_the_split_session(service, stepping_spy):
    service.handle_key_press_event(
        key_event(
            Qt.Key.Key_Up,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
    )
    service.handle_key_release_event(
        key_event(Qt.Key.Key_Shift, Qt.KeyboardModifier.ControlModifier, release=True)
    )

    assert stepping_spy.split_step.call_args.args == ("up",)
    stepping_spy.reset_split_state.assert_called()


def test_editing_shortcuts_are_inert_in_display_mode(service, model):
    model.mode = "display"

    assert service.handle_key_press_event(key_event(Qt.Key.Key_X)) is False
    assert service.handle_key_press_event(key_event(Qt.Key.Key_D)) is False
    assert model.electrodes.actuated_channels == set()


def test_mode_keys_flip_modes(service, model):
    service.handle_key_press_event(key_event(Qt.Key.Key_D))
    assert model.mode == "draw"

    service.handle_key_press_event(key_event(Qt.Key.Key_D))
    assert model.mode == "edit"


def test_realtime_toggle_needs_a_connected_dropbot(service, model, publish_spy):
    model.connected = False
    service.handle_key_press_event(key_event(Qt.Key.Key_T))
    publish_spy.assert_not_called()

    model.connected = True
    service.handle_key_press_event(key_event(Qt.Key.Key_T))
    publish_spy.assert_called_once_with(topic=SET_REALTIME_MODE, message="True")


def test_cheat_sheet_folds_alternate_keys_into_one_row():
    rows = dict(cheat_sheet_rows())

    assert any(key == "F1 / Ctrl+/" for key, _ in rows["Help"])
    assert shortcut_label("mode_draw") == "D"
