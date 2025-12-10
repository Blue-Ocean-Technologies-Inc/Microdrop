import json

from PySide6.QtGui import QKeyEvent, Qt, QWheelEvent, QAction
from PySide6.QtWidgets import QGraphicsView, QGraphicsSceneWheelEvent, QGraphicsSceneContextMenuEvent, QMenu
from traits.api import HasTraits, Instance, Dict, List, Str, observe, Bool
from pyface.qt.QtCore import QPointF

from device_viewer.models.electrodes import Electrode
from device_viewer.utils.electrode_route_helpers import find_shortest_paths
from dropbot_controller.consts import DETECT_DROPLETS
from logger.logger_service import get_logger
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.models.route import Route, RouteLayer
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from device_viewer.views.electrode_view.electrodes_view_base import ElectrodeView, ElectrodeConnectionItem, \
    ElectrodeEndpointItem
from device_viewer.default_settings import AUTOROUTE_COLOR, NUMBER_OF_CHANNELS, electrode_outline_key, \
    electrode_fill_key, actuated_electrodes_key, electrode_text_key, routes_key
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from ..preferences import DeviceViewerPreferences
from ..views.electrode_view.electrode_view_helpers import find_path_item
from ..views.electrode_view.scale_edit_view import ScaleEditViewController

logger = get_logger(__name__)

###### Channel edit helper methods #################
def remove_last_digit(number: int | None) -> int | None:
    if number == None: return None

    string = str(number)[:-1]
    if string == "":
        return None
    else:
        return int(string)

def add_digit(number: int | None, digit: str) -> int:
    if number == None:
        return int(digit)
    else:
        return int(str(number) + digit)

class ElectrodeInteractionControllerService(HasTraits):
    """Service to handle electrode interactions. Converts complicated Qt-events into more application specific events.
    Note that this is not an Envisage or Pyface callback/handler class, and is only called manually from the ElectrodeScene class.

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

    autoroute_paths = Dict({})

    electrode_hovered = Instance(ElectrodeView)

    rect_editing_index = -1  # Index of the point being edited in the reference rect
    rect_buffer = List(Instance(QPointF), [])

    #: state data fields
    _last_electrode_id_visited = Str(allow_none=True, desc="The last electrode clicked / dragged on by user's id.")

    _left_mouse_pressed = Bool(False)
    _right_mouse_pressed = Bool(False)

    _electrode_view_right_clicked = Instance(ElectrodeView, allow_none=True)

    _edit_reference_rect = Bool(False, desc='Is the reference rect editable without affecting perpective.')

    _electrode_tooltip_visible = Bool(False)

    _is_drag = Bool(False, desc='Is user dragging the pointer on screen')

    #######################################################################################################
    # Helpers
    #######################################################################################################

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
        publish_message(topic=DETECT_DROPLETS,
                        message=json.dumps(list(self.model.electrodes.channels_electrode_ids_map.keys())))

    #######################################################################################################
    # Perspective Handlers
    #######################################################################################################

    def handle_reference_point_placement(self, point: QPointF):
        """Handle the placement of a reference point for perspective correction."""
        # Add the new point to the reference rect
        self.rect_buffer.append(point)

    def handle_perspective_edit_start(self, point: QPointF):
        """Handle the start of perspective editing."""
        closest_point, closest_index = self.model.camera_perspective.get_closest_point(point)
        self.rect_editing_index = closest_index  # Store the index of the point being edited

    def handle_perspective_edit(self, point: QPointF):
        """Handle the editing of a reference point during perspective correction."""
        self.model.camera_perspective.transformed_reference_rect[self.rect_editing_index] = point

    def handle_perspective_edit_end(self):
        """Finalize the perspective editing."""
        self.rect_editing_index = -1

    def handle_rotate_device(self):
        self._rotate_device_view(90)

    def handle_rotate_camera(self):
        self.model.camera_perspective.rotate_output(90)

    def handle_toggle_edit_reference_rect(self):
        if self._edit_reference_rect:
            logger.info(f"Toggling reference rect edit mode off. Changed will affect camera perspective")
        else:
            logger.info(f"Toggling reference rect edit mode on. Changed will not affect camera perspective")

        self._edit_reference_rect = not self._edit_reference_rect

    #######################################################################################################
    # Electrode Handlers
    #######################################################################################################

    def handle_electrode_hover(self, electrode_view: ElectrodeView):
        self.electrode_hovered = electrode_view

    def handle_electrode_channel_editing(self, electrode: Electrode):
        self.model.electrodes.electrode_editing = electrode

    def handle_electrode_click(self, electrode_id: Str):
        """Handle an electrode click event."""
        if self.model.mode == "channel-edit":
            self.model.electrode_editing = self.model.electrodes[electrode_id]
        elif self.model.mode in ("edit", "draw", "edit-draw", "merge"):
            clicked_electrode_channel = self.model.electrodes[electrode_id].channel
            if clicked_electrode_channel != None: # The channel can be unassigned!
                self.model.electrodes.channels_states_map[clicked_electrode_channel] = \
                    not self.model.electrodes.channels_states_map.get(clicked_electrode_channel, False)

    def handle_toggle_electrode_tooltips(self, checked):
        """Handle toggle electrode tooltip."""
        self._electrode_tooltip_visible = checked
        self.electrode_view_layer.toggle_electrode_tooltips(checked)

    #######################################################################################################
    # Route Handlers
    #######################################################################################################

    def handle_route_draw(self, from_id, to_id):
        '''Handle a route segment being drawn or first electrode being added'''
        if self.model.mode in ("edit", "edit-draw", "draw"):
            if self.model.mode == "draw": # Create a new layer
                self.model.routes.add_layer(Route(route=[from_id, to_id]))
                self.model.routes.selected_layer = self.model.routes.layers[-1] # Select the route we just added
                self.model.mode = "edit-draw" # We now want to extend the route we just made
            else: # In some edit mode, try to modify currently selected layer
                current_route = self.model.routes.get_selected_route()
                if current_route == None: return

                if current_route.can_add_segment(from_id, to_id):
                    current_route.add_segment(from_id, to_id)

    def handle_route_erase(self, from_id, to_id):
        '''Handle a route segment being erased'''
        current_route = self.model.routes.get_selected_route()
        if current_route == None: return

        if current_route.can_remove(from_id, to_id):
            new_routes = [Route(route_list) for route_list in current_route.remove_segment(from_id, to_id)]
            self.model.routes.replace_layer(self.model.routes.selected_layer, new_routes)

    def handle_endpoint_erase(self, electrode_id):
        '''Handle the erase being triggered by hovering an endpoint'''
        current_route = self.model.get_selected_route()
        if current_route == None: return

        endpoints = current_route.get_endpoints()
        segments = current_route.get_segments()
        if len(endpoints) == 0 or len(segments) == 0: # Path of length 0 or path length of 1
            self.model.routes.delete_layer(self.model.routes.selected_layer) # Delete layer
        elif electrode_id == endpoints[0]: # Starting endpoint erased
            self.handle_route_erase(*segments[0]) # Delete the first segment
        elif electrode_id == endpoints[1]: # Ending endpoint erased
            self.handle_route_erase(*segments[-1]) # Delete last segment

    def handle_autoroute_start(self, from_id, avoid_collisions=True): # Run when the user enables autorouting an clicks on an electrode
        logger.debug("Start Autoroute")
        routes = [layer.route for layer in self.model.routes.layers]
        self.autoroute_paths = find_shortest_paths(from_id, self.model.electrodes.svg_model.neighbours, routes, avoid_collisions=avoid_collisions) # Run the BFS and cache the result dict
        self.model.routes.autoroute_layer = RouteLayer(route=Route(), color=AUTOROUTE_COLOR)

    def handle_autoroute(self, to_id):
        logger.debug(f"Autoroute: Adding route to {to_id}")
        self.model.routes.autoroute_layer.route.route = self.autoroute_paths.get(to_id, []).copy() # Display cached result from BFS

    def handle_autoroute_end(self):
        # only proceed if there is at least one segment and autoroute layer exists
        if self.model.routes.autoroute_layer:
            logger.debug("End Autoroute")
            self.autoroute_paths = {}
            if self.model.routes.autoroute_layer.route.get_segments():
                self.model.routes.add_layer(self.model.routes.autoroute_layer.route) # Keep the route, generate a normal color
            self.model.routes.autoroute_layer = None
            self.model.routes.selected_layer = self.model.routes.layers[-1] # Select just created layer
            # self.model.mode = 'edit'
        else:
            logger.warning("Autoroute needs to start by clicking and dragging from an electrode polygon.")

    #######################################################################################################
    # Key handlers
    #######################################################################################################

    def handle_digit_input(self, digit: str):
        if self.model.mode == "channel-edit":
            new_channel = add_digit(self.model.electrodes.electrode_editing.channel, digit)
            if new_channel == None or 0 <= new_channel < NUMBER_OF_CHANNELS:
                self.model.electrodes.electrode_editing.channel = new_channel

            self.electrode_view_layer.redraw_electrode_tooltip(self.model.electrodes.electrode_editing.id)

    def handle_backspace(self):
        if self.model.mode == "channel-edit":
            new_channel = remove_last_digit(self.model.electrodes.electrode_editing.channel)
            if new_channel == None or 0 <= new_channel < NUMBER_OF_CHANNELS:
                self.model.electrodes.electrode_editing.channel = new_channel

            self.electrode_view_layer.redraw_electrode_tooltip(self.model.electrodes.electrode_editing.id)

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
        self.model.zoom_in_event = True # Observer routine will call zoom in

    def handle_ctrl_minus(self):
        self.model.zoom_out_event = True # Observer routine will call zoom out

    def handle_space(self):
        self.model.flip_mode_activation(mode='pan')
        # Observer routine will call apply pan mode #

    ##########################################################################################
    # Electrode Scene global input delegations
    ##########################################################################################

    def handle_key_press_event(self, event: QKeyEvent):
        char = event.text()
        key = event.key()

        if char.isprintable() and char.isdigit():  # If an actual char digit was inputted
            self.handle_digit_input(char)

        elif key == Qt.Key_Backspace:
            self.handle_backspace()

        if (event.modifiers() & Qt.ControlModifier):
            if event.key() == Qt.Key_Right:
                self.handle_ctrl_key_right()

            if event.key() == Qt.Key_Left:
                self.handle_ctrl_key_left()

            # Check for Plus (Key_Plus is Numpad, Key_Equal is standard keyboard '+')
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.handle_ctrl_plus()

            if event.key() == Qt.Key.Key_Minus:
                self.handle_ctrl_minus()

        if (event.modifiers() & Qt.AltModifier):
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

        if button == Qt.LeftButton:
            self._left_mouse_pressed = True
            electrode_view =  self.get_electrode_view_for_scene_pos(event.scenePos())

            if mode in ("edit", "draw", "edit-draw"):
                if electrode_view:
                    self._last_electrode_id_visited = electrode_view.id

            elif mode == "auto":
                if electrode_view:
                    is_alt_pressed = event.modifiers() & Qt.KeyboardModifier.AltModifier
                    self.handle_autoroute_start(electrode_view.id,
                                                                    avoid_collisions=not is_alt_pressed)

            elif mode == "channel-edit":
                if electrode_view:
                    self.handle_electrode_channel_editing(electrode_view.electrode)

            elif mode == "camera-place":
                self.handle_reference_point_placement(event.scenePos())

            elif mode == "camera-edit":
                self.handle_perspective_edit_start(event.scenePos())

        elif button == Qt.RightButton:
            self._right_mouse_pressed = True
            self._electrode_view_right_clicked =  self.get_electrode_view_for_scene_pos(event.scenePos())

    def handle_mouse_move_event(self, event):
        """Handle the dragging motion."""

        mode = self.model.mode
        electrode_view = self.get_electrode_view_for_scene_pos(event.scenePos())
        self.handle_electrode_hover(electrode_view)

        if self._left_mouse_pressed:
            # Only proceed if we are in the appropriate mode with a valid electrode view.
            # If last electrode view is none then no electrode was clicked yet (for example, first click was not on electrode)
            if mode in ("edit", "draw", "edit-draw") and electrode_view and self._last_electrode_id_visited:

                    found_connection_item = find_path_item(self.device_view.scene(),
                                                           (self._last_electrode_id_visited, electrode_view.id))

                    if found_connection_item:  # Are the electrodes neighbours? (This excludes self)
                        self.handle_route_draw(self._last_electrode_id_visited, electrode_view.id)
                        self._is_drag = True  # Since more than one electrode is left clicked, its a drag, not a single electrode click

            elif mode == "auto" and electrode_view:
                # only proceed if a new electrode id was visited
                if electrode_view.id != self._last_electrode_id_visited:
                    self.handle_autoroute(electrode_view.id)  # We store last_electrode_id_visited as the source node

            elif mode == "camera-edit":
                self.handle_perspective_edit(event.scenePos())

        if self._right_mouse_pressed:
            if mode in ("edit", "draw", "edit-draw") and event.modifiers() & Qt.ControlModifier:
                connection_item = self.device_view.scene().get_item_under_mouse(event.scenePos(), ElectrodeConnectionItem)
                endpoint_item = self.device_view.scene().get_item_under_mouse(event.scenePos(), ElectrodeEndpointItem)
                if connection_item:
                    (from_id, to_id) = connection_item.key
                    self.handle_route_erase(from_id, to_id)
                elif endpoint_item:
                    self.handle_endpoint_erase(endpoint_item.electrode_id)

        # End of routine: now the current electrode view becomes the "last electrode visited"
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

                # Reset left-click related vars
                self._is_drag = False

                if mode == "edit-draw":  # Go back to draw
                    self.model.mode = "draw"
            elif mode == "camera-edit":
                self.handle_perspective_edit_end()
        elif button == Qt.RightButton:
            self._right_mouse_pressed = False

    def handle_scene_wheel_event(self, event: 'QGraphicsSceneWheelEvent'):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.delta()
            self.handle_ctrl_mouse_wheel_event(angle)
            event.accept()
            return True
        else:
            return False

    def handle_wheel_event(self, event: 'QWheelEvent'):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            self.handle_ctrl_mouse_wheel_event(angle)
            event.accept()
            return True
        else:
            return False

    def handle_context_menu_event(self, event: QGraphicsSceneContextMenuEvent):

        if not (event.modifiers() & Qt.ControlModifier): # If control is pressed, we do not show the context menu

            context_menu = QMenu()

            if self.model.mode.split("-")[0] == "camera":
                def set_camera_place_mode():
                    self.model.mode = "camera-place"


                reference_rect_edit_action = QAction("Edit Reference Rect", checkable=True,
                                              checked=self._edit_reference_rect,
                                              toolTip="Edit Reference Rectangle without changing perspective")

                reference_rect_edit_action.triggered.connect(self.handle_toggle_edit_reference_rect)

                context_menu.addAction("Reset Reference Rectangle", set_camera_place_mode)
                context_menu.addAction(reference_rect_edit_action)
                context_menu.addSeparator()

            else:
                context_menu.addAction("Measure Liquid Capacitance", self.model.measure_liquid_capacitance)
                context_menu.addAction("Measure Filler Capacitance", self.model.measure_filler_capacitance)
                context_menu.addSeparator()
                context_menu.addAction("Reset Electrodes", self.model.electrodes.reset_electrode_states)
                context_menu.addAction("Find Liquid", self.detect_droplet)
                context_menu.addSeparator()

                if self._electrode_view_right_clicked is not None:

                    scale_edit_view_controller = ScaleEditViewController(
                        model=self._electrode_view_right_clicked.electrode,
                        device_view_model=self.model)

                    context_menu.addAction("Adjust Electrode Area Scale", scale_edit_view_controller.configure_traits)
                    context_menu.addSeparator()

            # tooltip enabled by default
            tooltip_toggle_action = QAction("Enable Electrode Tooltip", checkable=True,
                                            checked=self._electrode_tooltip_visible)

            tooltip_toggle_action.triggered.connect(self.handle_toggle_electrode_tooltips)

            context_menu.addAction(tooltip_toggle_action)

            context_menu.exec(event.screenPos())

    ################################################################################################################
    #------------------ Traits observers --------------------------------------------
    ################################################################################################################

    @observe("model.routes.layers.items.visible")
    @observe("model.routes.selected_layer")
    @observe("model.routes.layers.items.route.route.items")
    @observe("model.routes.layers.items")
    @observe("model.routes.autoroute_layer.route.route.items")
    def route_redraw(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_connections_to_scene(self.model)

    @observe("model.electrodes.channels_states_map.items")
    @observe("model.electrodes.electrode_editing")
    @observe("model.electrodes.electrodes.items.channel")
    @observe("electrode_hovered")
    def electrode_state_recolor(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_colors(
                self.model,
                self.electrode_hovered,
            )

    @observe("model.electrodes.electrodes.items.channel")
    def electrode_channel_change(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_labels(self.model)

    @observe("model:camera_perspective:transformed_reference_rect:items")
    @observe("rect_buffer:items")
    def _reference_rect_change(self, event):
        if self.electrode_view_layer and self.model.mode.split("-")[0] == "camera":
                self.electrode_view_layer.redraw_reference_rect(rect=event.object)

    @observe("rect_buffer:items")
    def _rect_buffer_change(self, event):
        logger.debug(f"rect_buffer change: adding point {event.added}. Buffer of length {len(self.rect_buffer)} now.")
        if len(self.rect_buffer) == 4:  # We have a rectangle now
            logger.info(f"Reference rectangle complete!\nProceed to camera perspective editing!!")
            inverse = self.model.camera_perspective.transformation.inverted()[0]  # Get the inverse of the existing transformation matrix
            self.model.camera_perspective.reference_rect = [inverse.map(point) for point in event.object]
            self.model.camera_perspective.transformed_reference_rect = self.rect_buffer.copy()
            self.model.mode = "camera-edit"  # Switch to camera-edit mode

    @observe("model:mode")
    def _on_mode_change(self, event):
        if event.old in ("camera-edit", "camera-place") and event.new != "camera-edit":
            self.electrode_view_layer.clear_reference_rect()

        if event.new == "camera-edit":
            self.electrode_view_layer.redraw_reference_rect(self.model.camera_perspective.transformed_reference_rect)

        if event.old != "camera-place" and event.new == "camera-place":
            self.rect_buffer.clear()

        if event.new == 'pan' or event.old == 'pan':
            self._apply_pan_mode()

    @observe('model.electrode_scale', post_init=True)
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

        if changed_key == routes_key:
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




