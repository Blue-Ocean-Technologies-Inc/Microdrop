from traits.api import HasTraits, Instance, Dict, List, Str, observe
import json
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from device_viewer.models.main_model import MainModel
from device_viewer.models.route import Route, RouteLayer, RouteLayerManager
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from device_viewer.views.electrode_view.default_settings import AUTOROUTE_COLOR

logger = get_logger(__name__)


class ElectrodeInteractionControllerService(HasTraits):
    """Service to handle electrode interactions. Note that this is not an Envisage or Pyface callback/handler class, and is only called manually from the ElectrodeScene class."""

    #: Model
    model = Instance(MainModel)

    #: The current electrode layer view
    electrode_view_layer = Instance(ElectrodeLayer)

    autoroute_paths = Dict({})

    # -------------------- Handlers -----------------------

    def handle_electrode_click(self, electrode_id: Str):
        """Handle an electrode click event."""

        # get electrode model for current electrode clicked
        clicked_electrode_channel = self.model[electrode_id].channel

        self.model.channels_states_map[clicked_electrode_channel] = not self.model.channels_states_map.get(clicked_electrode_channel, False)

    def handle_route_draw(self, from_id, to_id):
        '''Handle a route segment being drawn or first electrode being added'''
        if self.model.mode in ("edit", "edit-draw", "draw"):
            if self.model.mode == "draw": # Create a new layer
                self.model.add_layer(Route(route=[from_id, to_id], channel_map=self.model.channels_electrode_ids_map))
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
            new_routes = [Route(route_list, channel_map=current_route.channel_map) for route_list in current_route.remove_segment(from_id, to_id)]
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
        self.model.autoroute_layer = RouteLayer(route=Route(channel_map=self.model.channels_electrode_ids_map), color=AUTOROUTE_COLOR)

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
    def route_redraw(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_connections_to_scene(self.model)
    
    @observe("model.channels_states_map.items")
    def electrode_recolor(self, event):
        if hasattr(event, "added"): # Dict Change Event
            for channel in event.removed.keys():
                for affected_electrode_id in self.model.channels_electrode_ids_map[channel]:
                    self.electrode_view_layer.electrode_views[affected_electrode_id].update_color(False)

            for channel, state in event.added.items():
                for affected_electrode_id in self.model.channels_electrode_ids_map[channel]:
                    self.electrode_view_layer.electrode_views[affected_electrode_id].update_color(state)


