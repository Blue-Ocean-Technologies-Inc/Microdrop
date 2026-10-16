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
from pathlib import Path
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import HasTraits, Instance

# Microdrop package imports.
from device_viewer.consts import (
    ARROW_DIRECTIONS,
    KEYBOARD_SHORTCUT_GROUPS,
    KEYBOARD_SHORTCUTS,
)
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.models.route import Route
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

BUNDLED_2X3 = (
    Path(__file__).resolve().parents[1] / "resources" / "devices" / "2x3device.svg"
)


class RouteDrawingInteraction(HasTraits):
    """The interaction service's route drawing, without its Qt scene.

    handle_route_draw mirrors ElectrodeInteractionControllerService's in
    device_viewer/services/electrode_interaction_service.py, which needs a
    scene and widgets to construct.
    """

    #: Device view model.
    model = Instance(DeviceViewMainModel)

    def handle_route_draw(self, from_id, to_id):
        if self.model.mode not in ("edit", "edit-draw", "draw"):
            return

        if self.model.mode == "draw":
            self.model.routes.add_layer(Route(route=[from_id, to_id]))
            self.model.routes.selected_layer = self.model.routes.layers[-1]
            self.model.mode = "edit-draw"

            return

        current_route = self.model.routes.get_selected_route()

        if current_route is not None and current_route.can_add_segment(from_id, to_id):
            current_route.add_segment(from_id, to_id)


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


@pytest.fixture
def route_service(model):
    model.electrodes.set_electrodes_from_svg_file(str(BUNDLED_2X3))

    return KeyboardShortcutService(
        model=model,
        stepping=ElectrodeSteppingService(model=model),
        interaction=RouteDrawingInteraction(model=model),
        device_view=MagicMock(),
    )


def ch_of(model, electrode_id):
    return model.electrodes.electrode_ids_channels_map[electrode_id]


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
    model.electrodes.actuated_channels = {1}
    model.mode = "display"

    assert service.handle_key_press_event(key_event(Qt.Key.Key_X)) is False
    assert service.handle_key_press_event(key_event(Qt.Key.Key_D)) is False
    assert model.electrodes.actuated_channels == {1}
    assert model.mode == "display"


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


def alt_arrow(key):
    return key_event(key, Qt.KeyboardModifier.AltModifier)


def test_alt_arrow_starts_a_route_from_the_last_visited_electrode(route_service, model):
    route_service.stepping.last_electrode_id_visited = "electrode053"

    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))

    assert model.mode == "edit-draw"
    assert model.routes.get_selected_route().route == ["electrode053", "electrode054"]
    assert route_service.stepping.last_electrode_id_visited == "electrode054"


def test_alt_arrow_extends_the_selected_route_from_its_tail(route_service, model):
    route_service.stepping.last_electrode_id_visited = "electrode053"

    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))
    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))

    assert model.routes.get_selected_route().route == [
        "electrode053",
        "electrode054",
        "electrode050",
    ]


def test_alt_arrow_with_an_ambiguous_cursor_is_a_noop(route_service, model):
    route_service.stepping.last_electrode_id_visited = ""
    model.electrodes.actuated_channels = {
        ch_of(model, "electrode053"),
        ch_of(model, "electrode054"),
    }

    handled = route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Down))

    assert handled is False
    assert model.routes.layers == []


def test_alt_arrow_uses_the_single_actuated_electrode(route_service, model):
    route_service.stepping.last_electrode_id_visited = ""
    model.electrodes.actuated_channels = {ch_of(model, "electrode053")}

    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))

    assert model.routes.get_selected_route().route == ["electrode053", "electrode054"]


def test_backspace_erases_the_tail_and_delete_removes_the_route(route_service, model):
    route_service.stepping.last_electrode_id_visited = "electrode053"
    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))
    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))

    route_service.handle_key_press_event(key_event(Qt.Key.Key_Backspace))
    assert model.routes.get_selected_route().route == ["electrode053", "electrode054"]
    assert route_service.stepping.last_electrode_id_visited == "electrode054"

    route_service.handle_key_press_event(key_event(Qt.Key.Key_Delete))
    assert model.routes.layers == []


def test_backspace_on_a_shuttle_route_drops_only_the_last_electrode(
    route_service, model
):
    shuttle = ["electrode053", "electrode054", "electrode053", "electrode054"]
    model.routes.add_layer(Route(route=shuttle))
    layer = model.routes.layers[-1]
    model.routes.selected_layer = layer
    model.mode = "edit-draw"

    route_service.handle_key_press_event(key_event(Qt.Key.Key_Backspace))

    assert layer.route.route == ["electrode053", "electrode054", "electrode053"]
    assert model.routes.selected_layer is layer
    assert route_service.stepping.last_electrode_id_visited == "electrode053"


def test_the_selected_route_tail_wins_over_the_stepping_cursor(route_service, model):
    route_service.stepping.last_electrode_id_visited = "electrode053"
    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))
    route_service.stepping.last_electrode_id_visited = "electrode000"

    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))

    assert model.routes.get_selected_route().route == [
        "electrode053",
        "electrode054",
        "electrode050",
    ]


def test_backspace_on_a_last_segment_selects_no_other_route(route_service, model):
    model.routes.add_layer(Route(route=["electrode000", "electrode001"]))
    model.routes.selected_layer = None
    route_service.stepping.last_electrode_id_visited = "electrode053"
    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))

    route_service.handle_key_press_event(key_event(Qt.Key.Key_Backspace))

    assert len(model.routes.layers) == 1
    assert model.routes.selected_layer is None


def test_delete_leaves_nothing_selected_when_other_routes_remain(route_service, model):
    model.routes.add_layer(Route(route=["electrode000", "electrode001"]))
    # Adding a layer auto-selects it; draw the new route with none picked.
    model.routes.selected_layer = None
    route_service.stepping.last_electrode_id_visited = "electrode053"
    route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))

    route_service.handle_key_press_event(key_event(Qt.Key.Key_Delete))

    assert len(model.routes.layers) == 1
    assert model.routes.selected_layer is None


def test_alt_arrow_is_inert_outside_route_modes(route_service, model):
    model.mode = "merge"
    route_service.stepping.last_electrode_id_visited = "electrode053"

    handled = route_service.handle_key_press_event(alt_arrow(Qt.Key.Key_Right))

    assert handled is False
    assert model.mode == "merge"
