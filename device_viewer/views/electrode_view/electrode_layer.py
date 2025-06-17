from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsScene
from pyface.qt.QtCore import Qt

from .electrodes_view_base import ElectrodeView
from .electrode_view_helpers import generate_connection_line
from .default_settings import default_colors
from microdrop_utils._logger import get_logger
from device_viewer.models.route import RouteLayer, RouteLayerManager

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

        svg = electrodes.svg_model

        # # Scale to approx 360p resolution for display
        modifier = max(640 / (svg.max_x - svg.min_x), 360 / (svg.max_y - svg.min_y))

        # Create the electrode views for each electrode from the electrodes model and add them to the group
        for electrode_id, electrode in electrodes.electrodes.items():
            self.electrode_views[electrode_id] = ElectrodeView(electrode_id, electrodes[electrode_id],
                                                               modifier * electrode.path)

        # Create the connections between the electrodes
        self.connections = {
            key: ((coord1[0] * modifier, coord1[1] * modifier), (coord2[0] * modifier, coord2[1] * modifier))
            for key, (coord1, coord2) in svg.connections.items()
            # key here is form dmf_utils.SvgUtil (see neighbours_to_points), and is a tuple of 2 electrode_ids. if (id1, id2) exists in the dict, then (id2, id1) wont, and viice versa
        }

        for key, (src, dst) in self.connections.items():

            # Generate connection line
            connection_item = generate_connection_line(key, src, dst)

            # Store the generated connection item
            self.connection_items[key] = connection_item

    def get_connection_item(self, from_id, to_id):
        '''Returns tuple of key, value from connection_items if found'''
        item = self.connection_items.get((from_id, to_id), None)
        if item:
            return ((from_id, to_id), item)

        item = self.connection_items.get((to_id, from_id), None) # Try other way
        if item:
            return ((to_id, from_id), item)
        
        return (None, None)

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

    ######################## catch all methods to add / remove all elements from scene ###################
    def add_all_items_to_scene(self, parent_scene: 'QGraphicsScene'):
        self.add_electrodes_to_scene(parent_scene)
        self.add_connections_to_scene(parent_scene)

    def remove_all_items_to_scene(self, parent_scene: 'QGraphicsScene'):
        self.remove_electrodes_to_scene(parent_scene)
        self.remove_connections_to_scene(parent_scene)

    ######################## Redraw connctions based on list of routes ###########################
    def redraw_connections_to_scene(self, route_layer_manager: RouteLayerManager):
        # Routes are applied in order, so later routes will apply on top
        # To minimize the number of overlapping Qt calls, we'll apply changes to a dictionary then transfer it to the view at the end

        connection_map = {} # Temporary map to superimpose routes

        for route_layer in route_layer_manager.layers:
            color = QColor(route_layer.color)
            
            if route_layer.is_selected:
                color = Qt.yellow
            elif route_layer.route.is_loop():
                color = Qt.red
            
            for (route_from, route_to) in route_layer.route.get_segments():
                if route_layer.visible:
                    connection_map[(route_from, route_to)] = color if connection_map.get((route_from, route_to), None) != Qt.yellow else Qt.yellow
                    connection_map[(route_to, route_from)] = color if connection_map.get((route_to, route_from)) != Qt.yellow else Qt.yellow # We want either possible keys to be true
        
        # Apply map
        for key, connection_item in self.connection_items.items():
            color = connection_map.get(key, False)
            if color:
                connection_item.set_active(color)
            else:
                connection_item.set_inactive()
                