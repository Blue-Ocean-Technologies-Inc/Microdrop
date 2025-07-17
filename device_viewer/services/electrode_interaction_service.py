from traits.api import HasTraits, Instance, Dict, List, Str, observe
from pyface.qt.QtCore import QPointF
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from device_viewer.models.main_model import MainModel
from device_viewer.models.route import Route, RouteLayer, RouteLayerManager
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from device_viewer.views.electrode_view.electrodes_view_base import ElectrodeView
from device_viewer.views.electrode_view.default_settings import AUTOROUTE_COLOR, NUMBER_OF_CHANNELS

logger = get_logger(__name__)


class ElectrodeInteractionControllerService(HasTraits):
    """Service to handle electrode interactions. Note that this is not an Envisage or Pyface callback/handler class, and is only called manually from the ElectrodeScene class."""

    #: Model
    model = Instance(MainModel)

    #: The current electrode layer view
    electrode_view_layer = Instance(ElectrodeLayer)

    autoroute_paths = Dict({})

    electrode_hovered = Instance(ElectrodeView)

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
        self.model.camera_perspective.reference_rect.append(point)
        if len(self.model.camera_perspective.reference_rect) == 4: # We have a rectangle now
            self.model.mode = "camera-edit"  # Switch to camera-edit mode

    def handle_electrode_hover(self, electrode_view: ElectrodeView):
        self.electrode_hovered = electrode_view

    def handle_digit_input(self, digit: str):
        if self.model.mode == "channel-edit":
            new_channel = self.add_digit(self.model.electrode_editing.channel, digit)
            if new_channel == None or 0 <= new_channel < NUMBER_OF_CHANNELS:
                self.model.electrode_editing.channel = new_channel
    
    def handle_backspace(self):
        if self.model.mode == "channel-edit":
            new_channel = self.remove_last_digit(self.model.electrode_editing.channel)
            if new_channel == None or 0 <= new_channel < NUMBER_OF_CHANNELS:
                self.model.electrode_editing.channel = new_channel

    def handle_electrode_click(self, electrode_id: Str):
        """Handle an electrode click event."""
        if self.model.mode == "channel-edit":
            self.model.electrode_editing = self.model.electrodes[electrode_id]
        elif self.model.mode in ("edit", "draw", "edit-draw", "merge"):
            clicked_electrode_channel = self.model[electrode_id].channel
            if clicked_electrode_channel != None: # The channel can be unassigned!
                self.model.channels_states_map[clicked_electrode_channel] = not self.model.channels_states_map.get(clicked_electrode_channel, False)

    def handle_route_draw(self, from_id, to_id):
        '''Handle a route segment being drawn or first electrode being added'''
        if self.model.mode in ("edit", "edit-draw", "draw"):
            if self.model.mode == "draw": # Create a new layer
                self.model.add_layer(Route(route=[from_id, to_id]))
                self.model.selected_layer = self.model.layers[-1] # Select the route we just added
                self.model.mode = "edit-draw" # We now want to extend the route we just made
            else: # In some edit mode, try to modify currently selected layer
                current_route = self.model.get_selected_route()
                if current_route == None: return

                if current_route.can_add_segment(from_id, to_id):
                    current_route.add_segment(from_id, to_id)

    def handle_route_erase(self, from_id, to_id):
        '''Handle a route segment being erased'''
        current_route = self.model.get_selected_route()
        if current_route == None: return
        
        if current_route.can_remove(from_id, to_id):
            new_routes = [Route(route_list) for route_list in current_route.remove_segment(from_id, to_id)]
            self.model.replace_layer(self.model.selected_layer, new_routes)
    
    def handle_endpoint_erase(self, electrode_id):
        '''Handle the erase being triggered by hovering an endpoint'''
        current_route = self.model.get_selected_route()
        if current_route == None: return

        endpoints = current_route.get_endpoints()
        segments = current_route.get_segments()
        if len(endpoints) == 0 or len(segments) == 0: # Path of length 0 or path length of 1
            self.model.delete_layer(self.model.selected_layer) # Delete layer
        elif electrode_id == endpoints[0]: # Starting endpoint erased
            self.handle_route_erase(*segments[0]) # Delete the first segment
        elif electrode_id == endpoints[1]: # Ending endpoint erased
            self.handle_route_erase(*segments[-1]) # Delete last segment

    def handle_autoroute_start(self, from_id): # Run when the user enables autorouting an clicks on an electrode
        routes = [layer.route for layer in self.model.layers]
        self.autoroute_paths = Route.find_shortest_paths(from_id, routes, self.model.svg_model.neighbours) # Run the BFS and cache the result dict
        self.model.autoroute_layer = RouteLayer(route=Route(), color=AUTOROUTE_COLOR)

    def handle_autoroute(self, to_id):
        self.model.autoroute_layer.route.route = self.autoroute_paths.get(to_id, []).copy() # Display cached result from BFS

    def handle_autoroute_end(self):
        self.autoroute_paths = {}
        self.model.add_layer(self.model.autoroute_layer.route) # Keep the route, generate a normal color
        self.model.autoroute_layer = None
        self.model.selected_layer = self.model.layers[-1] # Select just created layer
        self.model.mode = 'edit'

    def get_mode(self):
        return self.model.mode
    
    def set_mode(self, mode):
        self.model.mode = mode

    @observe("model.layers.items.visible")
    @observe("model.selected_layer")
    @observe("model.layers.items.route.route.items")
    @observe("model.layers.items")
    @observe("model.autoroute_layer.route.route.items")
    @observe("model.alpha_map.items.alpha")
    def route_redraw(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_connections_to_scene(self.model)
    
    @observe("model.channels_states_map.items")
    @observe("model.electrode_editing")
    @observe("model.electrodes.items.channel")
    @observe("electrode_hovered")
    @observe("model.alpha_map.items.alpha")
    def electrode_state_recolor(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_colors(self.model, self.electrode_hovered)

    @observe("model.electrodes.items.channel")
    @observe("model.alpha_map.items.alpha")
    def electrode_channel_change(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_labels(self.model)

    @observe("model.step_label")
    def step_label_change(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_editing_text(self.model)

    @observe("model.mode")
    def mode_change(self, event):
        if self.electrode_view_layer:
            if event.new == "camera-edit":
                self.electrode_view_layer.redraw_reference_rect(self.model)
            if event.old == "camera-edit" and event.new != "camera-edit":
                self.electrode_view_layer.reset_reference_rect()  # Clear the reference rect when leaving camera-edit mode