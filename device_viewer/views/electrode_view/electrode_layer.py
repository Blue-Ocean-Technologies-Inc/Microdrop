from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsScene
from pyface.qt.QtCore import Qt, QPointF

from .electrodes_view_base import ElectrodeView, ElectrodeConnectionItem, ElectrodeEndpointItem
from .electrode_view_helpers import loop_is_ccw
from .default_settings import ROUTE_CW_LOOP, ROUTE_CCW_LOOP, ROUTE_SELECTED, ELECTRODE_CHANNEL_EDITING, ELECTRODE_OFF, ELECTRODE_ON, ELECTRODE_NO_CHANNEL
from microdrop_utils._logger import get_logger
from device_viewer.models.main_model import MainModel

logger = get_logger(__name__)

class ElectrodeLayer():
    """
    Class defining the view for an electrode layer in the device viewer. Container for the elements used to establish
    the device viewer scene.

    - This view contains a group of electrode view objects
    - The view is responsible for updating the properties of all the electrode views contained in bulk.
    """

    def __init__(self, electrodes):
        # Create the connection and electrode items
        self.connection_items = {}
        self.electrode_views = {}
        self.electrode_endpoints = {}

        self.svg = electrodes.svg_model

        # # Scale to approx 360p resolution for display
        modifier = max(640 / (self.svg.max_x - self.svg.min_x), 360 / (self.svg.max_y - self.svg.min_y))

        # Create the electrode views for each electrode from the electrodes model and add them to the group
        for electrode_id, electrode in electrodes.electrodes.items():
            self.electrode_views[electrode_id] = ElectrodeView(electrode_id, electrodes[electrode_id],
                                                               modifier * electrode.path)
            self.electrode_endpoints[electrode_id] = ElectrodeEndpointItem(electrode_id,
                    QPointF(self.svg.electrode_centers[electrode_id][0] * modifier, self.svg.electrode_centers[electrode_id][1] * modifier), 2 * modifier)

        # Create the connections between the electrodes
        connections = {
            key: (QPointF(coord1[0] * modifier, coord1[1] * modifier), QPointF(coord2[0] * modifier, coord2[1] * modifier))
            for key, (coord1, coord2) in self.svg.connections.items()
            # key here is form dmf_utils.SvgUtil (see neighbours_to_points), and is a tuple of 2 electrode_ids. if (id1, id2) exists in the dict, then (id2, id1) wont, and viice versa
        }

        for key, (src, dst) in connections.items():
            self.connection_items[key] = ElectrodeConnectionItem(key, src, dst)

    ################# add electrodes/connections from scene ############################################
    def add_electrodes_to_scene(self, parent_scene: 'QGraphicsScene'):
        for electrode_id, electrode_view in self.electrode_views.items():
            parent_scene.addItem(electrode_view)

    def add_connections_to_scene(self, parent_scene: 'QGraphicsScene'):
        """
        Method to draw the connections between the electrodes in the layer
        """
        for key, item in self.connection_items.items():
            parent_scene.addItem(item)

    def add_endpoints_to_scene(self, parent_scene: 'QGraphicsScene'):
        for electrode_id, endpoint_view in self.electrode_endpoints.items():
            parent_scene.addItem(endpoint_view)

    ######################## remove electrodes/connections from scene ###################################
    def remove_electrodes_to_scene(self, parent_scene: 'QGraphicsScene'):
        for electrode_id, electrode_view in self.electrode_views.items():
            parent_scene.removeItem(electrode_view)

    def remove_connections_to_scene(self, parent_scene: 'QGraphicsScene'):
        """
        Method to draw the connections between the electrodes in the layer
        """
        for key, item in self.connection_items.items():
            parent_scene.removeItem(item)

    def remove_endpoints_to_scene(self, parent_scene: 'QGraphicsScene'):
        for electrode_id, endpoint_view in self.electrode_views.items():
            parent_scene.removeItem(endpoint_view)

    ######################## catch all methods to add / remove all elements from scene ###################
    def add_all_items_to_scene(self, parent_scene: 'QGraphicsScene'):
        self.add_electrodes_to_scene(parent_scene)
        self.add_connections_to_scene(parent_scene)
        self.add_endpoints_to_scene(parent_scene)

    def remove_all_items_to_scene(self, parent_scene: 'QGraphicsScene'):
        self.remove_electrodes_to_scene(parent_scene)
        self.remove_connections_to_scene(parent_scene)
        self.remove_endpoints_to_scene(parent_scene)

    ######################## Redraw functions ###########################
    def redraw_connections_to_scene(self, model: MainModel):
        # Routes are applied in order, so later routes will apply on top
        # To minimize the number of overlapping Qt calls, we'll apply changes to a dictionary then transfer it to the view at the end

        connection_map = {} # Temporary map to superimpose routes
        endpoint_map = {} # Temporary map to superimpose endpoints

        layers = model.layers

        if model.selected_layer:
            layers = layers + [model.selected_layer] # Paint the selected layer again so its always on top

        if model.autoroute_layer:
            layers = layers + [model.autoroute_layer] # Paint autoroute layer on top
        
        for i in range(len(layers)):
            route_layer = layers[i]
            color = QColor(route_layer.color)
            z = i # Make sure each route is it own layer. Prevents weird overlap patterns
            if route_layer == model.selected_layer:
                color = QColor(ROUTE_SELECTED)
            elif route_layer.route.is_loop():
                if loop_is_ccw(route_layer.route, self.svg.electrode_centers):
                    color = QColor(ROUTE_CCW_LOOP)
                else:
                    color = QColor(ROUTE_CW_LOOP)
            if route_layer.visible:
                for endpoint_id in route_layer.route.get_endpoints():
                    endpoint_map[endpoint_id] = (color, z)

                for (route_from, route_to) in route_layer.route.get_segments(): # Connections 
                    connection_map[(route_from, route_to)] = (color, z)
        
        # Apply map
        for key, connection_item in self.connection_items.items():
            (color, z) = connection_map.get(key, (None, None))
            if color:
                connection_item.set_active(color)
                connection_item.setZValue(z) # We want to make sure the whole route is on the same z value
            else:
                connection_item.set_inactive()
        
        for endpoint_id, endpoint_view in self.electrode_endpoints.items():
            (color, z) = endpoint_map.get(endpoint_id, (None, None))
            if color:
                endpoint_view.set_active(color)
                endpoint_view.setZValue(z)
            else:
                endpoint_view.set_inactive()
    
    def redraw_electrode_colors(self, model: MainModel, electrode_hovered: ElectrodeView):
        for electrode_id, electrode_view in self.electrode_views.items():
            if electrode_view.electrode == model.electrode_editing:
                color = ELECTRODE_CHANNEL_EDITING
            elif electrode_view.electrode.channel == None:
                color = ELECTRODE_NO_CHANNEL
            else:
                color = ELECTRODE_ON if model.channels_states_map.get(electrode_view.electrode.channel, False) else ELECTRODE_OFF
            
            if electrode_hovered == electrode_view:
                color = QColor(color).lighter(120).name()

            electrode_view.update_color(color)

    def redraw_electrode_labels(self, model: MainModel):
        for electrode_id, electrode_view in self.electrode_views.items():
            electrode_view.update_label()