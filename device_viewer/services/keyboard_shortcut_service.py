# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from functools import partial

# Enthought library imports.
from pyface.qt import QtCore
from traits.api import Any, Bool, Callable, Dict, HasTraits, Instance

# Microdrop package imports.
from device_viewer.consts import (
    ARROW_DIRECTIONS,
    KEYBOARD_SHORTCUT_GROUPS,
    KEYBOARD_SHORTCUTS,
)
from device_viewer.models.main_model import DeviceViewMainModel
from dropbot_controller.consts import SET_REALTIME_MODE

# Microdrop utils imports.
from microdrop_utils import keyboard_shortcuts
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from .electrode_stepping_service import ElectrodeSteppingService

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

Qt = QtCore.Qt

# Actions that run in every mode, Display included: they change the view
# or talk to the hardware, never the electrode or route state being edited.
# Only toggle_realtime mirrors the gamepad's ungated hardware action; find
# liquid clears the actuation first, so a stray F during a run must not fire.
VIEW_ONLY_ACTIONS = frozenset(
    {
        "zoom_in",
        "zoom_out",
        "fit_view",
        "rotate_device",
        "rotate_camera",
        "mode_pan",
        "escape",
        "show_shortcuts",
        "toggle_realtime",
    }
)

# Verbs of the "<verb>_<direction>" arrow actions; each has a "_<verb>"
# helper on the service taking the device-frame direction.
ARROW_VERBS = ("step", "extend", "shrink", "split", "draw_route")

# Modes in which Alt+arrows draw routes. Leaving merge, channel-edit,
# camera or zone modes for them would discard their in-progress state.
ROUTE_DRAWING_MODES = ("edit", "draw", "edit-draw")

# Releasing either of these ends a Ctrl+Shift+arrow split session.
_SPLIT_MODIFIER_KEYS = (Qt.Key.Key_Control, Qt.Key.Key_Shift)


#: The table helpers bound to KEYBOARD_SHORTCUTS, for the mode picker's
#: tooltips and the cheat sheet.
shortcut_label = partial(keyboard_shortcuts.shortcut_label, KEYBOARD_SHORTCUTS)
cheat_sheet_rows = partial(
    keyboard_shortcuts.cheat_sheet_rows, KEYBOARD_SHORTCUTS, KEYBOARD_SHORTCUT_GROUPS
)


class KeyboardShortcutService(HasTraits):
    """Run the device view's keyboard shortcuts from KEYBOARD_SHORTCUTS.

    Qt-light: it reads key events but only drives the shared model, the
    stepping service and the interaction service. A handler returns False
    when it did nothing, so the scene can pass the key on; any other
    return value means the shortcut ran.
    """

    #: Device view model.
    model = Instance(DeviceViewMainModel)

    #: The electrode cursor shared with the gamepad and the pointer handlers.
    stepping = Instance(ElectrodeSteppingService)

    #: The ElectrodeInteractionControllerService, for actions it owns
    #: (rotation, droplet detection, route drawing). Typed loosely because
    #: that module will import this one.
    interaction = Any()

    #: The AutoFitGraphicsView showing the device.
    device_view = Any()

    #: Called by Ctrl+Z; None leaves the key unhandled.
    undo_handler = Callable()

    #: Called by Ctrl+Y and Ctrl+Shift+Z; None leaves the keys unhandled.
    redo_handler = Callable()

    #: Opens the keyboard shortcut cheat sheet.
    show_shortcuts_handler = Callable()

    #: QKeySequence -> action name, built once from KEYBOARD_SHORTCUTS.
    _actions_by_sequence = Dict()

    #: True from a split step until Ctrl or Shift is released.
    _split_session_active = Bool(False)

    def traits_init(self):
        self._actions_by_sequence = keyboard_shortcuts.actions_by_sequence(
            KEYBOARD_SHORTCUTS
        )

    # ------------------ Key events ------------------------------------

    def handle_key_press_event(self, event):
        """Run the shortcut bound to the pressed keys; return True if one ran."""
        action = self._actions_by_sequence.get(
            keyboard_shortcuts.key_sequence_of(event)
        )

        if action is None:
            return False

        primary = keyboard_shortcuts.primary_action(action)

        if not (self.model.editable or primary in VIEW_ONLY_ACTIONS):
            return False

        return self.resolve_action(action)() is not False

    def handle_key_release_event(self, event):
        """End the split session when one of its modifiers is released."""
        if self._split_session_active and event.key() in _SPLIT_MODIFIER_KEYS:
            self.stepping.reset_split_state()
            self._split_session_active = False

    def resolve_action(self, action):
        """Return the callable that runs ``action``, or None if there is none.

        Arrow directions are mapped from the screen to the device frame, so
        an arrow moves the way it points whatever the view rotation.
        """
        verb, _, direction = action.rpartition("_")

        if verb in ARROW_VERBS and direction in ARROW_DIRECTIONS:
            return partial(
                getattr(self, f"_{verb}"),
                self.stepping.map_direction_for_device_rotation(direction),
            )

        primary = keyboard_shortcuts.primary_action(action)

        return getattr(self, f"action_{primary}", None)

    # ------------------ Arrow actions ---------------------------------

    def _step(self, direction):
        self.stepping.step_active_electrodes(direction)

    def _extend(self, direction):
        self.stepping.extend_active_electrodes(direction)

    def _shrink(self, direction):
        self.stepping.shrink_active_electrodes(direction)

    def _split(self, direction):
        self.stepping.split_step(direction)
        self._split_session_active = True

    def _draw_route(self, direction):
        """Grow a route one electrode in ``direction`` from the route cursor.

        With no route being edited this starts one, the same way a mouse
        drag in Draw mode does.
        """
        if self.model.mode not in ROUTE_DRAWING_MODES:
            return False

        cursor = self._route_cursor()

        if cursor is None:
            return False

        target = self.stepping.neighbor_in_direction(cursor, direction)

        if target is None:
            return False

        if self.model.routes.get_selected_route() is None:
            self.model.mode = "draw"

        self.interaction.handle_route_draw(cursor, target)

        route = self.model.routes.get_selected_route()

        if route is None or route.get_endpoints()[1] != target:
            return False

        self.stepping.last_electrode_id_visited = target

        return True

    def _route_cursor(self):
        """Return the electrode a keyboard-drawn route grows from, or None.

        The selected route's tail while editing it, else the stepping
        cursor, else the one actuated electrode; None when several are
        actuated and nothing else says which.
        """
        route = self.model.routes.get_selected_route()

        if self.model.mode in ("edit", "edit-draw") and route is not None:
            endpoints = route.get_endpoints()

            if endpoints:
                return endpoints[1]

        if self.stepping.last_electrode_id_visited:
            return self.stepping.last_electrode_id_visited

        active_ids = self.stepping.get_active_electrode_ids()

        if len(active_ids) == 1:
            return next(iter(active_ids))

        return None

    # ------------------ Routes ----------------------------------------

    def action_erase_route_tail(self):
        """Drop the selected route's last electrode, undoing one Alt+arrow.

        Truncated in place rather than through the segment erase, which
        removes every pass over a segment and so would wipe a shuttle
        route like A-B-A-B whole.
        """
        route = self.model.routes.get_selected_route()

        if route is None:
            return False

        if len(route.route) <= 2:
            # Nothing of two electrodes would remain; drop the route rather
            # than let the layer manager select another one.
            return self.action_delete_route()

        route.route.pop()
        self.stepping.last_electrode_id_visited = route.route[-1]

    def action_delete_route(self):
        """Delete the selected route and leave none selected.

        The layer manager selects the last remaining route when one is
        removed; the keyboard must not move on to a route nobody picked.
        """
        routes = self.model.routes

        if routes.selected_layer is None:
            return False

        routes.delete_layer(routes.selected_layer)
        routes.selected_layer = None

    # ------------------ Modes -----------------------------------------

    def action_mode_draw(self):
        self.model.flip_mode_activation("draw")

    def action_mode_edit(self):
        self.model.flip_mode_activation("edit")

    def action_mode_auto(self):
        self.model.flip_mode_activation("auto")

    def action_mode_channel_edit(self):
        self.model.flip_mode_activation("channel-edit")

    def action_mode_pan(self):
        self.model.flip_mode_activation("pan")

    def action_escape(self):
        """Leave Pan mode, or stop extending the route being drawn."""
        if self.model.mode == "pan":
            self.model.goto_last_mode()

            return True

        if self.model.mode == "edit-draw":
            self.model.mode = "edit"

            return True

        return False

    # ------------------ View ------------------------------------------

    def action_zoom_in(self):
        self.model.zoom_in_event = True

    def action_zoom_out(self):
        self.model.zoom_out_event = True

    def action_fit_view(self):
        if self.device_view is None:
            return False

        self.device_view.auto_fit = True
        self.device_view.fit_to_scene_rect()

    def action_rotate_device(self):
        self.interaction.handle_rotate_device()

    def action_rotate_camera(self):
        self.interaction.handle_rotate_camera()

    # ------------------ Actions ---------------------------------------

    def action_clear_electrodes(self):
        self.model.electrodes.clear_electrode_states()
        self.stepping.reset_split_state()

    def action_clear_routes(self):
        self.model.routes.clear_routes()

    def action_find_liquid(self):
        """Clear the actuation, then detect droplets (the gamepad's sequence)."""
        self.model.electrodes.clear_electrode_states()
        self.stepping.reset_split_state()
        self.interaction.detect_droplet()

    def action_toggle_realtime(self):
        if not self.model.connected:
            logger.info("Realtime mode needs a connected DropBot; ignoring key")

            return False

        publish_message(
            topic=SET_REALTIME_MODE, message=str(not self.model.realtime_mode)
        )

    def action_undo(self):
        if self.undo_handler is None:
            return False

        self.undo_handler()

    def action_redo(self):
        if self.redo_handler is None:
            return False

        self.redo_handler()

    # ------------------ Help ------------------------------------------

    def action_show_shortcuts(self):
        if self.show_shortcuts_handler is None:
            return False

        self.show_shortcuts_handler()
