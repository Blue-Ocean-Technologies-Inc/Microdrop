from traits.api import HasTraits, Instance, Dict, List, Str, observe
import json
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from device_viewer.models.electrodes import Electrodes
from device_viewer.models.route import Route, RouteLayer, RouteLayerManager
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from device_viewer.views.electrode_view.default_settings import AUTOROUTE_COLOR

logger = get_logger(__name__)


class ElectrodeInteractionControllerService(HasTraits):
    """Service to handle electrode interactions. Note that this is not an Envisage or Pyface callback/handler class, and is only called manually from the ElectrodeScene class."""

    #: The electrodes model containing all electrode data
    electrodes_model = Instance(Electrodes)

    #: The current electrode layer view
    electrode_view_layer = Instance(ElectrodeLayer)

    #: Routes model
    route_layer_manager = Instance(RouteLayerManager)

    autoroute_paths = Dict({})

    # -------------------- Handlers -----------------------

    def handle_electrode_click(self, _electrode_id: Str):
        """Handle an electrode click event."""

        # get electrode model for current electrode clicked
        _clicked_electrode_channel = self.electrodes_model[_electrode_id].channel

        affected_electrode_ids = self.electrodes_model.channels_electrode_ids_map[_clicked_electrode_channel]

        logger.debug(f"Affected electrodes {affected_electrode_ids} with same channel as clicked electrode")

        for affected_electrode_id in affected_electrode_ids:
            # obtain affected electrode object
            _electrode = self.electrodes_model[affected_electrode_id]

            # update electrode model for electrode clicked and all electrodes with same channel affected by this click.
            _electrode.state = not _electrode.state

    def handle_route_draw(self, from_id, to_id):
        '''Handle a route segment being drawn or first electrode being added'''
        if self.route_layer_manager.mode in ("edit", "edit-draw", "draw"):
            if self.route_layer_manager.mode == "draw": # Create a new layer
                self.route_layer_manager.add_layer(Route(route=[from_id, to_id], channel_map=self.electrodes_model.channels_electrode_ids_map))
                self.route_layer_manager.selected_layer = self.route_layer_manager.layers[-1] # Select the route we just added
                self.route_layer_manager.mode = "edit-draw" # We now want to extend the route we just made
            else: # In some edit mode, try to modify currently selected layer
                current_route = self.route_layer_manager.get_selected_route()
                if current_route == None: return

                if current_route.can_add_segment(from_id, to_id):
                    current_route.add_segment(from_id, to_id)

    def handle_route_erase(self, from_id, to_id):
        '''Handle a route segment being erased'''
        current_route = self.route_layer_manager.get_selected_route()
        if current_route == None: return
        
        if current_route.can_remove(from_id, to_id):
            new_routes = [Route(route_list, channel_map=current_route.channel_map) for route_list in current_route.remove_segment(from_id, to_id)]
            self.route_layer_manager.replace_layer(self.route_layer_manager.selected_layer, new_routes)
    
    def handle_endpoint_erase(self, electrode_id):
        '''Handle the erase being triggered by hovering an endpoint'''
        current_route = self.route_layer_manager.get_selected_route()
        if current_route == None: return

        endpoints = current_route.get_endpoints()
        segments = current_route.get_segments()
        if len(endpoints) == 0 or len(segments) == 0: # Path of length 0 or path length of 1
            self.route_layer_manager.delete_layer(self.route_layer_manager.selected_layer) # Delete layer
        elif electrode_id == endpoints[0]: # Starting endpoint erased
            self.handle_route_erase(*segments[0]) # Delete the first segment
        elif electrode_id == endpoints[1]: # Ending endpoint erased
            self.handle_route_erase(*segments[-1]) # Delete last segment

    def handle_autoroute_start(self, from_id): # Run when the user enables autorouting an clicks on an electrode
        routes = [layer.route for layer in self.route_layer_manager.layers]
        self.autoroute_paths = Route.find_shortest_paths(from_id, routes, self.electrodes_model.svg_model.neighbours) # Run the BFS and cache the result dict
        self.route_layer_manager.autoroute_layer = RouteLayer(route=Route(channel_map=self.electrodes_model.channels_electrode_ids_map), color=AUTOROUTE_COLOR)

    def handle_autoroute(self, to_id):
        self.route_layer_manager.autoroute_layer.route.route = self.autoroute_paths.get(to_id, []).copy() # Display cached result from BFS

    def handle_autoroute_end(self):
        self.autoroute_paths = {}
        self.route_layer_manager.add_layer(self.route_layer_manager.autoroute_layer.route) # Keep the route, generate a normal color
        self.route_layer_manager.autoroute_layer = None
        self.route_layer_manager.selected_layer = self.route_layer_manager.layers[-1] # Select just created layer
        self.route_layer_manager.mode = 'edit'

    def get_mode(self):
        return self.route_layer_manager.mode
    
    def set_mode(self, mode):
        self.route_layer_manager.mode = mode

    @observe("route_layer_manager.layers.items.visible")
    @observe("route_layer_manager.selected_layer")
    @observe("route_layer_manager.layers.items.route.route.items")
    @observe("route_layer_manager.layers.items")
    @observe("route_layer_manager.autoroute_layer.route.route.items")
    def route_redraw(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_connections_to_scene(self.route_layer_manager)
    
    @observe("electrodes_model._electrodes.items.state")
    def electrode_recolor(self, event):
        if event.name == "state": # State change
            electrode_view = self.electrode_view_layer.electrode_views[event.object.id]
            electrode_view.update_color(event.new)

