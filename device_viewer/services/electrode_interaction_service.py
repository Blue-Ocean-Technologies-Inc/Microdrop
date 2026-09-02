# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import json

from PySide6.QtCore import QPointF
from PySide6.QtGui import QAction, QKeyEvent, Qt, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneWheelEvent,
    QGraphicsView,
    QMenu,
    QToolTip,
)

from traits.api import (
    Bool,
    DelegatesTo,
    Dict,
    HasTraits,
    Instance,
    List,
    Str,
    observe,
)

from device_viewer.default_settings import (
    AUTOROUTE_COLOR,
    actuated_electrodes_key,
    connections_key,
    electrode_fill_key,
    electrode_outline_key,
    electrode_text_key,
    routes_key,
)
from device_viewer.models.electrodes import Electrode
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.models.route import Route, RouteLayer
from device_viewer.utils.electrode_route_helpers import find_shortest_paths
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from device_viewer.views.electrode_view.electrodes_view_base import (
    ElectrodeConnectionItem,
    ElectrodeEndpointItem,
    ElectrodeView,
)
from dropbot_controller.consts import DETECT_DROPLETS

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.system_config import is_rpi

from ..preferences import DeviceViewerPreferences
from ..views.electrode_view.electrode_view_helpers import find_path_item
from ..views.electrode_view.scale_edit_view import ScaleEditViewController
from .electrode_stepping_service import ElectrodeSteppingService

from logger.logger_service import get_logger

logger = get_logger(__name__)

# Sentinel returned by channel-text parsing when the edit should be reverted
# (kept distinct from None, which means "unassign the channel").
_CHANNEL_REVERT = object()


class ElectrodeInteractionControllerService(HasTraits):
    """Service to handle electrode interactions. Converts complicated Qt-events into
    more application specific events.
    Note that this is not an Envisage or Pyface callback/handler class, and is only
    called manually from the ElectrodeScene class.

    The following should be passed as kwargs to the constructor:
    - model: The main model instance.
    - electrode_view_layer: The current electrode layer view.
    - device_view: the current QGraphics device view
    - device_viewer_preferences: preferences for the current device viewer
    """

    #: Device view Model
    model = Instance(DeviceViewMainModel)

    #: The current electrode layer view
    electrode_view_layer = Instance(ElectrodeLayer)

    #: The current device view
    device_view = Instance(QGraphicsView)

    #: The preferences for the current device view
    device_viewer_preferences = Instance(DeviceViewerPreferences)

    #: Electrode cursor actions (arrow stepping, split); shared with the
    #: gamepad service so both inputs move the same cursor
    stepping = Instance(ElectrodeSteppingService)

    autoroute_paths = Dict({})

    electrode_hovered = Instance(ElectrodeView)

    rect_editing_index = -1  # Index of the point being edited in the reference rect
    rect_buffer = List(Instance(QPointF), [])

    #: state data fields
    _last_electrode_id_visited = DelegatesTo("stepping", "last_electrode_id_visited")

    _left_mouse_pressed = Bool(False)
    _right_mouse_pressed = Bool(False)

    _edit_reference_rect = Bool(
        False, desc="Is the reference rect editable without affecting perpective."
    )

    _electrode_tooltip_visible = Bool(True)

    _is_drag = Bool(False, desc="Is user dragging the pointer on screen")

    #######################################################################################################
    # Helpers
    #######################################################################################################

    def traits_init(self):
        # Cumulative device-view rotation is stored on the model as
        # model.device_rotation_deg (persisted via preferences). Apply any
        # rotation loaded from preferences to the view now that both the
        # QGraphicsView and the electrode layer are bound.
        self._apply_persisted_device_rotation()

    def _apply_persisted_device_rotation(self) -> None:
        """Apply the persisted rotation angle to the QGraphicsView.

        Mirrors the sequence used by `_rotate_device_view` (rotate the
        view, counter-rotate label text, then re-fit) so the loaded state
        looks identical to what a user-driven rotate would produce.
        """
        rot = int(self.model.device_rotation_deg or 0) % 360
        if not rot:
            return
        self.device_view.rotate(rot)
        self.electrode_view_layer.rotate_electrode_views_texts(-rot)
        self.device_view.fit_to_scene_rect()

    def _zoom_in(self, scale=None):
        logger.debug("Zoom In")
        # disable auto fit if user wants to zoom in
        if self.device_view.auto_fit:
            self.device_view.auto_fit = False

        if scale is None:
            scale = self.device_viewer_preferences._zoom_scale

        self.device_view.scale(scale, scale)

    def _zoom_out(self, scale=None):
        logger.debug("Zoom Out")

        if scale is None:
            scale = self.device_viewer_preferences._zoom_scale

        self.device_view.scale(1 / scale, 1 / scale)

    def _rotate_device_view(self, angle_step):

        # enable auto fit for rotations:
        if not self.device_view.auto_fit:
            self.device_view.auto_fit = True

        # rotate entire view:
        self.device_view.rotate(angle_step)

        # Track cumulative device-view rotation to remap controller directions.
        # Writing the model trait also persists the new angle to preferences
        # via the observer on DeviceViewMainModel.
        self.model.device_rotation_deg = (
            int(self.model.device_rotation_deg or 0) + int(angle_step)
        ) % 360
        # undo rotation on text for maintaining readability
        self.electrode_view_layer.rotate_electrode_views_texts(-angle_step)

        self.device_view.fit_to_scene_rect()

    def _apply_pan_mode(self):
        enabled = self.model.mode == "pan"

        # Disable interaction with items (clicking/hovering) while panning
        self.device_view.setInteractive(not enabled)

        if enabled:
            self.device_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            self.device_view.setDragMode(QGraphicsView.DragMode.NoDrag)

    def get_electrode_view_for_scene_pos(self, scene_pos):
        return self.device_view.scene().get_item_under_mouse(scene_pos, ElectrodeView)

    def detect_droplet(self):
        """Placeholder for a context menu action."""
        publish_message(
            topic=DETECT_DROPLETS,
            message=json.dumps(
                list(self.model.electrodes.channels_electrode_ids_map.keys())
            ),
        )

    #######################################################################################################
    # Perspective Handlers
    #######################################################################################################

    def handle_reference_point_placement(self, point: QPointF):
        """Handle the placement of a reference point for perspective correction."""
        # Add the new point to the reference rect
        self.rect_buffer.append(point)

    def handle_perspective_edit_start(self, point: QPointF):
        """Handle the start of perspective editing."""
        closest_point, closest_index = self.model.camera_perspective.get_closest_point(
            point
        )
        self.rect_editing_index = (
            closest_index  # Store the index of the point being edited
        )

    def handle_perspective_edit(self, point: QPointF):
        """Handle the editing of a reference point during perspective correction."""

        # check if we are editing just the reference rect buffer or the actual rect
        # tied to transforming perspective
        if self._edit_reference_rect:
            logger.debug("Only reference rect buffer changed")
            if not self.rect_buffer:
                self.rect_buffer = (
                    self.model.camera_perspective.transformed_reference_rect.copy()
                )
            rect_to_edit = self.rect_buffer
        else:
            logger.debug("Reference rect tied to perspective transform changed")
            rect_to_edit = self.model.camera_perspective.transformed_reference_rect

        rect_to_edit[self.rect_editing_index] = point

    def handle_perspective_edit_end(self):
        """Finalize the perspective editing."""
        self.rect_editing_index = -1

    def handle_rotate_device(self):
        self._rotate_device_view(90)

    def handle_rotate_camera(self):
        self.model.camera_perspective.rotate_output(90)

    def handle_toggle_edit_reference_rect(self):
        if self._edit_reference_rect:
            logger.info(
                "Toggling reference rect edit mode off. Changed will affect "
                "camera perspective"
            )
        else:
            logger.info(
                "Toggling reference rect edit mode on. Changed will not affect "
                "camera perspective"
            )

        self._edit_reference_rect = not self._edit_reference_rect

    #######################################################################################################
    # Electrode Handlers
    #######################################################################################################

    def handle_electrode_hover(self, electrode_view: ElectrodeView):
        self.electrode_hovered = electrode_view

    def handle_electrode_channel_editing(self, electrode: Electrode):
        self.model.electrodes.electrode_editing = electrode

    def handle_channel_label_press(self, event) -> bool:
        """In channel-edit mode, a left-click on an electrode enters (or
        switches to) inline label editing.

        Returns True when a NEW edit is started — the caller consumes the press
        so the whole value stays selected (type to replace). Returns False for
        clicks inside the field already being edited, letting Qt place the caret
        or start a drag-selection."""
        if self.model.mode != "channel-edit" or event.button() != Qt.LeftButton:
            return False
        electrode_view = self.get_electrode_view_for_scene_pos(event.scenePos())
        if electrode_view is None:
            return False
        if getattr(self, "_editing_view", None) is electrode_view:
            return False  # already editing this label — in-field click
        self._begin_channel_label_edit(electrode_view)
        return True

    def _begin_channel_label_edit(self, electrode_view):
        # Commit and close any editor already open before opening the new one —
        # only one label edits at a time. Done explicitly (not via focus-out) so
        # the switch is deterministic regardless of focus event ordering.
        if getattr(self, "_editing_view", None) is not None:
            self._on_channel_label_committed()

        self.model.electrodes.electrode_editing = electrode_view.electrode  # highlight
        self._editing_view = electrode_view

        text_item = electrode_view.text_path
        text_item.editing_committed.connect(self._on_channel_label_committed)
        text_item.editing_cancelled.connect(self._on_channel_label_cancelled)
        electrode_view.enter_label_edit()

    def _end_channel_label_edit(self):
        electrode_view = getattr(self, "_editing_view", None)
        if electrode_view is None:
            return
        text_item = electrode_view.text_path
        try:
            text_item.editing_committed.disconnect(self._on_channel_label_committed)
            text_item.editing_cancelled.disconnect(self._on_channel_label_cancelled)
        except (RuntimeError, TypeError):
            pass  # already disconnected
        electrode_view.exit_label_edit()
        self._editing_view = None
        # Snap the label back to the model value: on commit this repaints the
        # committed number; on cancel/revert it discards the typed text.
        self.electrode_view_layer.redraw_electrode_labels(self.model)

    def _on_channel_label_committed(self):
        electrode_view = getattr(self, "_editing_view", None)
        if electrode_view is None:
            return
        new_channel = self._parse_channel_text(electrode_view.text_path.toPlainText())
        if new_channel is not _CHANNEL_REVERT:
            # Writing the channel fires the label-redraw observer; we still tear
            # down below to reset interaction state.
            electrode_view.electrode.channel = new_channel
        self._end_channel_label_edit()

    def _on_channel_label_cancelled(self):
        self._end_channel_label_edit()

    def _parse_channel_text(self, text):
        """Map raw field text to a channel value: '' -> None (unassign), an
        in-range int -> that int, anything else -> _CHANNEL_REVERT (keep the
        prior value)."""
        text = text.strip()
        if text == "":
            return None
        try:
            value = int(text)
        except ValueError:
            return _CHANNEL_REVERT  # digits are blocked live, so unexpected
        n_channels = self.device_viewer_preferences.NUMBER_OF_CHANNELS
        if 0 <= value < n_channels:
            return value
        return _CHANNEL_REVERT

    def handle_electrode_click(self, electrode_id: Str):
        """Handle an electrode click event."""
        if self.model.mode == "channel-edit":
            self.model.electrode_editing = self.model.electrodes[electrode_id]

        elif self.model.mode in ("edit", "draw", "edit-draw", "merge"):
            clicked_electrode_channel = self.model.electrodes[electrode_id].channel
            if clicked_electrode_channel is not None:  # The channel can be unassigned!
                if clicked_electrode_channel in self.model.electrodes.disabled_channels:
                    return  # Disabled electrodes cannot be actuated

                if clicked_electrode_channel in self.model.electrodes.actuated_channels:
                    self.model.electrodes.actuated_channels.remove(
                        clicked_electrode_channel
                    )
                else:
                    self.model.electrodes.actuated_channels.add(
                        clicked_electrode_channel
                    )

    def handle_toggle_electrode_tooltips(self, checked):
        """Handle toggle electrode tooltip."""
        self._electrode_tooltip_visible = checked
        self.electrode_view_layer.toggle_electrode_tooltips(checked)

    #######################################################################################################
    # Route Handlers
    #######################################################################################################

    def handle_route_draw(self, from_id, to_id):
        """Handle a route segment being drawn or first electrode being added"""
        if self.model.mode in ("edit", "edit-draw", "draw"):
            if self.model.mode == "draw":  # Create a new layer
                self.model.routes.add_layer(Route(route=[from_id, to_id]))
                self.model.routes.selected_layer = self.model.routes.layers[
                    -1
                ]  # Select the route we just added
                self.model.mode = (
                    "edit-draw"  # We now want to extend the route we just made
                )
            else:  # In some edit mode, try to modify currently selected layer
                current_route = self.model.routes.get_selected_route()
                if current_route is None:
                    return

                if current_route.can_add_segment(from_id, to_id):
                    current_route.add_segment(from_id, to_id)

    def handle_route_erase(self, from_id, to_id):
        """Handle a route segment being erased"""
        current_route = self.model.routes.get_selected_route()
        if current_route is None:
            return

        if current_route.can_remove(from_id, to_id):
            new_routes = [
                Route(route_list)
                for route_list in current_route.remove_segment(from_id, to_id)
            ]
            self.model.routes.replace_layer(
                self.model.routes.selected_layer, new_routes
            )

    def handle_endpoint_erase(self, electrode_id):
        """Handle the erase being triggered by hovering an endpoint"""
        current_route = self.model.get_selected_route()
        if current_route is None:
            return

        endpoints = current_route.get_endpoints()
        segments = current_route.get_segments()
        if (
            len(endpoints) == 0 or len(segments) == 0
        ):  # Path of length 0 or path length of 1
            self.model.routes.delete_layer(
                self.model.routes.selected_layer
            )  # Delete layer
        elif electrode_id == endpoints[0]:  # Starting endpoint erased
            self.handle_route_erase(*segments[0])  # Delete the first segment
        elif electrode_id == endpoints[1]:  # Ending endpoint erased
            self.handle_route_erase(*segments[-1])  # Delete last segment

    def handle_autoroute_start(
        self, from_id, avoid_collisions=True
    ):  # Run when the user enables autorouting an clicks on an electrode
        logger.debug("Start Autoroute")
        routes = [layer.route for layer in self.model.routes.layers]
        self.autoroute_paths = find_shortest_paths(
            from_id,
            self.model.electrodes.svg_model.neighbours,
            routes,
            avoid_collisions=avoid_collisions,
        )  # Run the BFS and cache the result dict
        self.model.routes.autoroute_layer = RouteLayer(
            route=Route(), color=AUTOROUTE_COLOR
        )

    def handle_autoroute(self, to_id):
        logger.debug(f"Autoroute: Adding route to {to_id}")
        self.model.routes.autoroute_layer.route.route = self.autoroute_paths.get(
            to_id, []
        ).copy()  # Display cached result from BFS

    def handle_autoroute_end(self):
        # only proceed if there is at least one segment and autoroute layer exists
        if self.model.routes.autoroute_layer:
            logger.debug("End Autoroute")
            self.autoroute_paths = {}
            if self.model.routes.autoroute_layer.route.get_segments():
                self.model.routes.add_layer(
                    self.model.routes.autoroute_layer.route
                )  # Keep the route, generate a normal color
            self.model.routes.autoroute_layer = None
            self.model.routes.selected_layer = self.model.routes.layers[
                -1
            ]  # Select just created layer
            # self.model.mode = 'edit'
        else:
            logger.warning(
                "Autoroute needs to start by clicking and dragging from an "
                "electrode polygon."
            )

    #######################################################################################################
    # Key handlers
    #######################################################################################################

    def handle_ctrl_key_left(self):
        self.model.camera_perspective.rotate_output(-90)

    def handle_ctrl_key_right(self):
        self.model.camera_perspective.rotate_output(90)

    def handle_alt_key_left(self):
        angle_step = -90
        self._rotate_device_view(angle_step)

    def handle_alt_key_right(self):
        angle_step = 90
        self._rotate_device_view(angle_step)

    def handle_ctrl_mouse_wheel_event(self, angle):

        if angle > 0:
            self.model.zoom_in_event = True
        else:
            self.model.zoom_out_event = True

    def handle_ctrl_plus(self):
        self.model.zoom_in_event = True  # Observer routine will call zoom in

    def handle_ctrl_minus(self):
        self.model.zoom_out_event = True  # Observer routine will call zoom out

    def handle_space(self):
        self.model.flip_mode_activation(mode="pan")
        # Observer routine will call apply pan mode #

    ##########################################################################################
    # Electrode Scene global input delegations
    ##########################################################################################

    def handle_key_press_event(self, event: QKeyEvent):
        key = event.key()

        # Arrow-key stepping (keyboard).
        # Only when Ctrl/Alt are NOT held to avoid conflicts with existing shortcuts.
        if not (event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            # We accept either Qt6 enum style (Qt.Key.Key_Left) or legacy aliases.
            key_left = {
                getattr(Qt, "Key_Left", None),
                getattr(getattr(Qt, "Key", None), "Key_Left", None),
            }
            key_right = {
                getattr(Qt, "Key_Right", None),
                getattr(getattr(Qt, "Key", None), "Key_Right", None),
            }
            key_up = {
                getattr(Qt, "Key_Up", None),
                getattr(getattr(Qt, "Key", None), "Key_Up", None),
            }
            key_down = {
                getattr(Qt, "Key_Down", None),
                getattr(getattr(Qt, "Key", None), "Key_Down", None),
            }
            if key in key_left:
                self.stepping.step_active_electrodes(
                    self.stepping.map_direction_for_device_rotation("left")
                )
            elif key in key_right:
                self.stepping.step_active_electrodes(
                    self.stepping.map_direction_for_device_rotation("right")
                )
            elif key in key_up:
                self.stepping.step_active_electrodes(
                    self.stepping.map_direction_for_device_rotation("up")
                )
            elif key in key_down:
                self.stepping.step_active_electrodes(
                    self.stepping.map_direction_for_device_rotation("down")
                )

        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_Right:
                self.handle_ctrl_key_right()

            if event.key() == Qt.Key_Left:
                self.handle_ctrl_key_left()

            # Check for Plus (Key_Plus is Numpad, Key_Equal is standard keyboard '+')
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.handle_ctrl_plus()

            if event.key() == Qt.Key.Key_Minus:
                self.handle_ctrl_minus()

        if event.modifiers() & Qt.AltModifier:
            if event.key() == Qt.Key_Right:
                self.handle_alt_key_right()

            elif event.key() == Qt.Key_Left:
                self.handle_alt_key_left()

        if event.key() == Qt.Key.Key_Space:
            self.handle_space()

    def handle_mouse_press_event(self, event):
        """Handle the start of a mouse click event."""

        button = event.button()
        mode = self.model.mode

        electrode_view = self.get_electrode_view_for_scene_pos(event.scenePos())
        if button == Qt.LeftButton:
            self._left_mouse_pressed = True

            if mode in ("edit", "draw", "edit-draw"):
                if electrode_view:
                    self._last_electrode_id_visited = electrode_view.id

            elif mode == "auto":
                if electrode_view:
                    is_alt_pressed = event.modifiers() & Qt.KeyboardModifier.AltModifier
                    self.handle_autoroute_start(
                        electrode_view.id, avoid_collisions=not is_alt_pressed
                    )

            elif mode == "channel-edit":
                if electrode_view:
                    self.handle_electrode_channel_editing(electrode_view.electrode)

            elif mode == "camera-place":
                self.handle_reference_point_placement(event.scenePos())

            elif mode == "camera-edit":
                self.handle_perspective_edit_start(event.scenePos())

        elif button == Qt.RightButton:
            self._right_mouse_pressed = True
            if electrode_view:
                self.model.electrodes.electrode_right_clicked = electrode_view.electrode
            else:
                self.model.electrodes.electrode_left_clicked = None

    def handle_mouse_move_event(self, event):
        """Handle the dragging motion."""

        mode = self.model.mode
        electrode_view = self.get_electrode_view_for_scene_pos(event.scenePos())
        self.handle_electrode_hover(electrode_view)

        if self._left_mouse_pressed:
            # Only proceed if we are in the appropriate mode with a valid electrode
            # view. If last electrode view is none then no electrode was clicked yet
            # (for example, first click was not on electrode)
            if (
                mode in ("edit", "draw", "edit-draw")
                and electrode_view
                and self._last_electrode_id_visited
            ):
                found_connection_item = find_path_item(
                    self.device_view.scene(),
                    (self._last_electrode_id_visited, electrode_view.id),
                )

                if (
                    found_connection_item
                ):  # Are the electrodes neighbours? (This excludes self)
                    self.handle_route_draw(
                        self._last_electrode_id_visited, electrode_view.id
                    )
                    # Since more than one electrode is left clicked, its a drag, not
                    # a single electrode click
                    self._is_drag = True

            elif mode == "auto" and electrode_view:
                # only proceed if a new electrode id was visited
                if electrode_view.id != self._last_electrode_id_visited:
                    self.handle_autoroute(
                        electrode_view.id
                    )  # We store last_electrode_id_visited as the source node

            elif mode == "camera-edit":
                self.handle_perspective_edit(event.scenePos())

        if self._right_mouse_pressed:
            if (
                mode in ("edit", "draw", "edit-draw")
                and event.modifiers() & Qt.ControlModifier
            ):
                connection_item = self.device_view.scene().get_item_under_mouse(
                    event.scenePos(), ElectrodeConnectionItem
                )
                endpoint_item = self.device_view.scene().get_item_under_mouse(
                    event.scenePos(), ElectrodeEndpointItem
                )
                if connection_item:
                    (from_id, to_id) = connection_item.key
                    self.handle_route_erase(from_id, to_id)
                elif endpoint_item:
                    self.handle_endpoint_erase(endpoint_item.electrode_id)

        # End of routine: now the current electrode view becomes the "last electrode
        # visited"
        if electrode_view:
            self._last_electrode_id_visited = electrode_view.id

    def handle_mouse_release_event(self, event):
        """Finalize the drag operation."""
        button = event.button()

        if button == Qt.LeftButton:
            self._left_mouse_pressed = False
            mode = self.model.mode
            if mode == "auto":
                self.handle_autoroute_end()

            elif mode in ("edit", "draw", "edit-draw"):
                electrode_view = self.get_electrode_view_for_scene_pos(event.scenePos())
                # If it's a click (not a drag) since only one electrode selected:
                if not self._is_drag and electrode_view:
                    self.handle_electrode_click(electrode_view.id)

                    # The rig's touchscreen has no hover — surface the
                    # electrode tooltip at the finger after a tap instead.
                    # Shown at release: shown any earlier, the release
                    # event itself hides it again. The Enable Electrode
                    # Tooltip toggle still governs it.
                    if is_rpi() and electrode_view.toolTip():
                        QToolTip.showText(event.screenPos(), electrode_view.toolTip())

                # Reset left-click related vars
                self._is_drag = False

                if mode == "edit-draw":  # Go back to draw
                    self.model.mode = "draw"
            elif mode == "camera-edit":
                self.handle_perspective_edit_end()
        elif button == Qt.RightButton:
            self._right_mouse_pressed = False

    def handle_scene_wheel_event(self, event: "QGraphicsSceneWheelEvent"):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.delta()
            self.handle_ctrl_mouse_wheel_event(angle)
            event.accept()
            return True
        else:
            return False

    def handle_wheel_event(self, event: "QWheelEvent"):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            self.handle_ctrl_mouse_wheel_event(angle)
            event.accept()
            return True
        else:
            return False

    def handle_context_menu_event(self, event: QGraphicsSceneContextMenuEvent):
        # Resolve the electrode under the event position at menu time — a
        # touch long-press posts a context-menu event without the
        # right-button press that used to set electrode_right_clicked, and
        # this also drops the stale electrode a previous right click left.
        electrode_view = self.get_electrode_view_for_scene_pos(event.scenePos())
        self.model.electrodes.electrode_right_clicked = (
            electrode_view.electrode if electrode_view else None
        )

        if not (
            event.modifiers() & Qt.ControlModifier
        ):  # If control is pressed, we do not show the context menu
            context_menu = QMenu()

            if self.model.mode.split("-")[0] == "camera":

                def set_camera_place_mode():
                    self.model.mode = "camera-place"

                reference_rect_edit_action = QAction(
                    "Edit Reference Rect",
                    checkable=True,
                    checked=self._edit_reference_rect,
                    toolTip=(
                        "Edit Reference Rectangle without changing camera perspective"
                    ),
                )

                reference_rect_edit_action.triggered.connect(
                    self.handle_toggle_edit_reference_rect
                )

                context_menu.addAction(
                    "Reset Reference Rectangle", set_camera_place_mode
                )
                context_menu.addAction(reference_rect_edit_action)
                context_menu.addSeparator()

            else:
                context_menu.addAction(
                    "Measure Liquid Capacitance", self.model.measure_liquid_capacitance
                )
                context_menu.addAction(
                    "Measure Filler Capacitance", self.model.measure_filler_capacitance
                )
                context_menu.addSeparator()
                context_menu.addAction(
                    "Clear Electrodes", self.model.electrodes.clear_electrode_states
                )
                context_menu.addAction("Clear Routes", self.model.routes.clear_routes)
                context_menu.addSeparator()
                context_menu.addAction("Find Liquid", self.detect_droplet)
                context_menu.addSeparator()

                # Bulk enable/disable all electrodes
                has_disabled = len(self.model.electrodes.disabled_channels) > 0

                def enable_all_electrodes():
                    self.model.electrodes.disabled_channels.clear()

                def disable_all_electrodes():
                    all_channels = set(
                        self.model.electrodes.channels_electrode_ids_map.keys()
                    )
                    self.model.electrodes.disabled_channels = all_channels

                if has_disabled:
                    context_menu.addAction(
                        "Enable All Electrodes", enable_all_electrodes
                    )
                context_menu.addAction("Disable All Electrodes", disable_all_electrodes)
                context_menu.addSeparator()

                if self.model.electrodes.electrode_right_clicked is not None:
                    right_clicked = self.model.electrodes.electrode_right_clicked
                    channel = right_clicked.channel

                    # Disable/Enable electrode toggle
                    if channel is not None:
                        is_disabled = channel in self.model.electrodes.disabled_channels
                        label = (
                            "Enable Electrode" if is_disabled else "Disable Electrode"
                        )

                        def toggle_disable(ch=channel, currently_disabled=is_disabled):
                            if currently_disabled:
                                self.model.electrodes.disabled_channels.discard(ch)
                            else:
                                self.model.electrodes.disabled_channels.add(ch)

                        context_menu.addAction(label, toggle_disable)

                    scale_edit_view_controller = ScaleEditViewController(
                        model=self.model
                    )

                    context_menu.addAction(
                        "Adjust Electrode Area Scale",
                        scale_edit_view_controller.configure_traits,
                    )
                    context_menu.addSeparator()

            # tooltip enabled by default
            tooltip_toggle_action = QAction(
                "Enable Electrode Tooltip",
                checkable=True,
                checked=self._electrode_tooltip_visible,
            )

            tooltip_toggle_action.triggered.connect(
                self.handle_toggle_electrode_tooltips
            )

            context_menu.addAction(tooltip_toggle_action)

            context_menu.exec(event.screenPos())

    ################################################################################################################
    # ------------------ Traits observers --------------------------------------------
    ################################################################################################################

    @observe("model.routes.layers.items.visible")
    @observe("model.routes.selected_layer")
    @observe("model.routes.layers.items.route.route.items")
    @observe("model.routes.layers.items")
    @observe("model.routes.autoroute_layer.route.route.items")
    def route_redraw(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_connections_to_scene(self.model)

    @observe("model.electrodes.electrode_editing")
    @observe("model.electrodes.electrodes.items.channel")
    def electrode_state_recolor(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_colors(
                self.model,
                self.electrode_hovered,
            )

    @observe("model.electrodes.electrode_editing")
    def _teardown_label_edit_on_deselect(self, event):
        # Leaving channel-edit mode clears electrode_editing (main_model), so an
        # open editor is cancelled and reset along with the deselection.
        if event.new is None and getattr(self, "_editing_view", None) is not None:
            self._end_channel_label_edit()

    @observe("model.electrodes.actuated_channels.items")
    @observe("model.electrodes.disabled_channels.items")
    def actuation_state_recolor(self, event):
        """Recolor only the electrodes whose channels changed — the hot
        path during protocol runs (each phase touches a handful of the
        board's channels).

        Two event shapes arrive here: in-place mutation gives a
        SetChangeEvent (added/removed); wholesale replacement — what
        RouteExecutionService._apply_phase does every phase — gives the
        container change event (old/new sets), diffed here by symmetric
        difference (= exactly the channels whose membership flipped)."""
        if not self.electrode_view_layer:
            return
        added = getattr(event, "added", None)
        removed = getattr(event, "removed", None)
        if added is not None or removed is not None:
            changed_channels = set(added or ()) | set(removed or ())
        else:
            old, new = getattr(event, "old", None), getattr(event, "new", None)
            if not isinstance(old, (set, frozenset)) or not isinstance(
                new, (set, frozenset)
            ):
                # Unknown event shape: recolor everything rather than guess.
                self.electrode_view_layer.redraw_electrode_colors(
                    self.model, self.electrode_hovered
                )
                return
            changed_channels = old ^ new
        self.electrode_view_layer.redraw_electrode_colors_for_channels(
            self.model, changed_channels, self.electrode_hovered
        )

    @observe("electrode_hovered")
    def hovered_electrode_recolor(self, event):
        """Hover only affects the two electrodes involved; recoloring the
        whole board per mouse move made hovering expensive."""
        if not self.electrode_view_layer:
            return
        for electrode_view in (event.old, event.new):
            if electrode_view is not None:
                self.electrode_view_layer.recolor_electrode(
                    self.model, electrode_view, self.electrode_hovered
                )

    @observe("model.electrodes.electrodes.items.channel")
    def electrode_channel_change(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_labels(self.model)

    @observe("model:camera_perspective:transformed_reference_rect")
    def _reference_rect_change(self, event):
        logger.debug(f"Reference rectangle change: {event}")
        if self.electrode_view_layer and self.model.mode.split("-")[0] == "camera":
            self.electrode_view_layer.redraw_reference_rect(rect=event.new)

    @observe("model:camera_perspective:transformed_reference_rect:items")
    def _reference_rect_items_change(self, event):
        logger.debug(f"Reference rectangle items change: {event}")
        if self.electrode_view_layer and self.model.mode.split("-")[0] == "camera":
            self.electrode_view_layer.redraw_reference_rect(rect=event.object)

    @observe("rect_buffer:items")
    def _rect_buffer_change(self, event):
        logger.debug(
            f"rect_buffer change: adding point {event.added}. "
            f"Buffer of length {len(self.rect_buffer)} now."
        )
        if len(self.rect_buffer) == 4:  # We have a rectangle now
            inverse = self.model.camera_perspective.transformation.inverted()[
                0
            ]  # Get the inverse of the existing transformation matrix
            self.model.camera_perspective.reference_rect = [
                inverse.map(point) for point in event.object
            ]
            self.model.camera_perspective.transformed_reference_rect = (
                self.rect_buffer.copy()
            )

            # User may have already completed the reference rectangle and in edit mode.
            # sometimes user is just editing a completed rect_buffer when
            # edit_reference_rect is enabled
            # Only need to do this and give log message when its the first time the
            # reference rect is completed.
            if self.model.mode != "camera-edit":
                logger.info(
                    "Reference rectangle complete!\n"
                    "Proceed to camera perspective editing!!"
                )
                self.model.mode = (
                    "camera-edit"  # Switch to camera-edit mode if not already there
                )

        else:
            self.electrode_view_layer.redraw_reference_rect(rect=event.object)

    @observe("model:mode")
    def _on_mode_change(self, event):
        if event.old in ("camera-edit", "camera-place") and event.new != "camera-edit":
            self.electrode_view_layer.clear_reference_rect()

        if event.new == "camera-edit":
            self.electrode_view_layer.redraw_reference_rect(
                self.model.camera_perspective.transformed_reference_rect
            )

        if event.old != "camera-place" and event.new == "camera-place":
            self.rect_buffer.clear()

        if event.new == "pan" or event.old == "pan":
            self._apply_pan_mode()

    @observe("model.electrode_scale", post_init=True)
    def electrode_area_scale_edited(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_all_electrode_tooltips()

    @observe("model.alpha_map.items.[alpha, visible]", post_init=True)
    def _alpha_change(self, event):

        changed_key = event.object.key

        if changed_key == electrode_outline_key and self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_lines(self.model)

        if changed_key in [electrode_fill_key, actuated_electrodes_key]:
            self.electrode_state_recolor(None)

        if changed_key == electrode_text_key:
            self.electrode_channel_change(None)

        if changed_key in (routes_key, connections_key):
            self.route_redraw(None)

    @observe("model:zoom_in_event", post_init=True)
    def _zoom_in_event_triggered(self, event):
        self._zoom_in()

    @observe("model:zoom_out_event", post_init=True)
    def _zoom_out_event_triggered(self, event):
        self._zoom_out()

    @observe("model:reset_view_event", post_init=True)
    def _reset_view_event_triggered(self, event):
        self.device_view.fit_to_scene_rect()
