from PySide6.QtWidgets import QGraphicsView
from traits.api import HasTraits, Instance, Dict, List, Str, observe
from pyface.qt.QtCore import QPointF

from envisage.api import IApplication

from device_viewer.models.electrodes import Electrode
from device_viewer.utils.electrode_route_helpers import find_shortest_paths
from logger.logger_service import get_logger
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.models.route import Route, RouteLayer
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from device_viewer.views.electrode_view.electrodes_view_base import ElectrodeView
from device_viewer.default_settings import AUTOROUTE_COLOR, NUMBER_OF_CHANNELS, electrode_outline_key, \
    electrode_fill_key, actuated_electrodes_key, electrode_text_key, routes_key

logger = get_logger(__name__)

class ElectrodeInteractionControllerService(HasTraits):
    """Service to handle electrode interactions. Converts complicated Qt-events into more application specific events.
    Note that this is not an Envisage or Pyface callback/handler class, and is only called manually from the ElectrodeScene class.

    The following should be passed as kwargs to the constructor:
    - model: The main model instance.
    - electrode_view_layer: The current electrode layer view.
    - device_view: the current QGraphics device view
    - application: The main Envisage application instance.
    """

    #: Device view Model
    model = Instance(DeviceViewMainModel)

    #: The current electrode layer view
    electrode_view_layer = Instance(ElectrodeLayer)

    #: The current device view
    device_view = Instance(QGraphicsView)

    #: The current parent envisage application
    application = Instance(IApplication)

    autoroute_paths = Dict({})

    electrode_hovered = Instance(ElectrodeView)

    rect_editing_index = -1  # Index of the point being edited in the reference rect
    rect_buffer = List([])


    # -------------------- Helpers ------------------------

    def remove_last_digit(self, number: int | None) -> int | None:
        if number == None: return None

        string = str(number)[:-1]
        if string == "":
            return None
        else:
            return int(string)

    def add_digit(self, number: int | None, digit: str) -> int:
        if number == None:
            return int(digit)
        else:
            return int(str(number) + digit)

    # -------------------- Handlers -----------------------

    def handle_reference_point_placement(self, point: QPointF):
        """Handle the placement of a reference point for perspective correction."""
        # Add the new point to the reference rect
        self.rect_buffer.append(point)
        if len(self.rect_buffer) == 4:  # We have a rectangle now
            inverse = self.model.camera_perspective.transformation.inverted()[0]  # Get the inverse of the existing transformation matrix
            self.model.camera_perspective.reference_rect = [inverse.map(point) for point in self.rect_buffer]
            self.model.camera_perspective.transformed_reference_rect = self.rect_buffer.copy()
            self.model.mode = "camera-edit"  # Switch to camera-edit mode

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

    def handle_electrode_hover(self, electrode_view: ElectrodeView):
        self.electrode_hovered = electrode_view

    def handle_electrode_channel_editing(self, electrode: Electrode):
        self.model.electrodes.electrode_editing = electrode

    #######################################################################################################
    # Key handlers
    #######################################################################################################
    def handle_digit_input(self, digit: str):
        if self.model.mode == "channel-edit":
            new_channel = self.add_digit(self.model.electrodes.electrode_editing.channel, digit)
            if new_channel == None or 0 <= new_channel < NUMBER_OF_CHANNELS:
                self.model.electrodes.electrode_editing.channel = new_channel

            self.electrode_view_layer.redraw_electrode_tooltip(self.model.electrodes.electrode_editing.id)

    def handle_backspace(self):
        if self.model.mode == "channel-edit":
            new_channel = self.remove_last_digit(self.model.electrodes.electrode_editing.channel)
            if new_channel == None or 0 <= new_channel < NUMBER_OF_CHANNELS:
                self.model.electrodes.electrode_editing.channel = new_channel

            self.electrode_view_layer.redraw_electrode_tooltip(self.model.electrodes.electrode_editing.id)

    def handle_ctrl_key_left(self):
        self.model.camera_perspective.rotate_output(-90)

    def handle_ctrl_key_right(self):
        self.model.camera_perspective.rotate_output(90)

    def handle_rotate_camera(self):
        self.model.camera_perspective.rotate_output(90)

    def handle_alt_key_left(self):
        angle_step = -90
        self._rotate_device_view(angle_step)

    def handle_alt_key_right(self):
        angle_step = 90
        self._rotate_device_view(angle_step)

    def handle_rotate_device(self):
        self._rotate_device_view(90)

    def _rotate_device_view(self, angle_step):
        # rotate entire view:
        self.device_view.rotate(angle_step)
        # undo rotation on text for maintaining readability
        self.electrode_view_layer.rotate_electrode_views_texts(-angle_step)

        self.device_view.fit_to_scene_rect()

    def handle_mouse_wheel_event(self, angle, sx=1.15, sy=1.15):

        if angle > 0:
            self._zoom_in(sx, sy)
        else:
            self._zoom_out(sx, sy)

    def _zoom_in(self, sx, sy):
        logger.debug("Zoom In")
        self.device_view.scale(sx, sy)

    def _zoom_out(self, sx, sy):
        logger.debug("Zoom Out")
        self.device_view.scale(1 / sx, 1 / sy)


    ########################################################################################################

    def handle_electrode_click(self, electrode_id: Str):
        """Handle an electrode click event."""
        if self.model.mode == "channel-edit":
            self.model.electrode_editing = self.model.electrodes[electrode_id]
        elif self.model.mode in ("edit", "draw", "edit-draw", "merge"):
            clicked_electrode_channel = self.model.electrodes[electrode_id].channel
            if clicked_electrode_channel != None: # The channel can be unassigned!
                self.model.electrodes.channels_states_map[clicked_electrode_channel] = \
                    not self.model.electrodes.channels_states_map.get(clicked_electrode_channel, False)

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
        routes = [layer.route for layer in self.model.routes.layers]
        self.autoroute_paths = find_shortest_paths(from_id, self.model.electrodes.svg_model.neighbours, routes, avoid_collisions=avoid_collisions) # Run the BFS and cache the result dict
        self.model.routes.autoroute_layer = RouteLayer(route=Route(), color=AUTOROUTE_COLOR)

    def handle_autoroute(self, to_id):
        self.model.routes.autoroute_layer.route.route = self.autoroute_paths.get(to_id, []).copy() # Display cached result from BFS

    def handle_autoroute_end(self):
        self.autoroute_paths = {}
        # only proceed if there is at least one segment
        if self.model.routes.autoroute_layer.route.get_segments():
            self.model.routes.add_layer(self.model.routes.autoroute_layer.route) # Keep the route, generate a normal color
        self.model.routes.autoroute_layer = None
        self.model.routes.selected_layer = self.model.routes.layers[-1] # Select just created layer
        # self.model.mode = 'edit'

    def handle_toggle_electrode_tooltip(self, checked):
        '''Handle toggle electrode tooltip.'''
        self.electrode_view_layer.toggle_electrode_tooltips(checked)

    def get_mode(self):
        return self.model.mode

    def set_mode(self, mode):
        self.model.mode = mode

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

    @observe("model.camera_perspective.transformation")
    @observe("rect_buffer.items")
    def update_perspective_rect(self, event):
        if self.electrode_view_layer:
            if self.model.mode == "camera-edit" and len(self.model.camera_perspective.reference_rect) == 4:
                self.electrode_view_layer.redraw_reference_rect(self.model)
            elif self.model.mode == "camera-place" and len(self.rect_buffer) > 1:
                self.electrode_view_layer.redraw_reference_rect(self.model, partial_rect=self.rect_buffer)

    @observe("model.mode")
    def _on_mode_change(self, event):
        if event.old in ("camera-edit", "camera-place") and event.new != "camera-edit":
            self.electrode_view_layer.clear_reference_rect()

        if event.old != "camera-place" and event.new == "camera-place":
            self.rect_buffer = []

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





