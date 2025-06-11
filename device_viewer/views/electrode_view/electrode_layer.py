from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsScene

from .electrodes_view_base import ElectrodeView
from .electrode_view_helpers import generate_connection_line
from .default_settings import default_colors


class ElectrodeLayer():
    """
    Class defining the view for an electrode layer in the device viewer. Container for the elements used to establish
    the device viewer scene.

    - This view contains a group of electrode view objects
    - The view is responsible for updating the properties of all the electrode views contained in bulk.
    """

    def __init__(self, electrodes):
        # Create the connection and electrode items
        self.connection_items = []
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
        }

        for key, (src, dst) in self.connections.items():

            # Generate connection line
            connection_item = generate_connection_line(key, src, dst)

            # Store the generated connection item
            self.connection_items.append(connection_item)

    ################# add electrodes/connections from scene ############################################
    def add_electrodes_to_scene(self, parent_scene: 'QGraphicsScene'):
        for electrode_id, electrode_view in self.electrode_views.items():
            parent_scene.addItem(electrode_view)

    def add_connections_to_scene(self, parent_scene: 'QGraphicsScene'):
        """
        Method to draw the connections between the electrodes in the layer
        """
        for el in self.connection_items:
            parent_scene.addItem(el)

    ######################## remove electrodes/connections from scene ###################################
    def remove_electrodes_to_scene(self, parent_scene: 'QGraphicsScene'):
        for electrode_id, electrode_view in self.electrode_views.items():
            parent_scene.removeItem(electrode_view)

    def remove_connections_to_scene(self, parent_scene: 'QGraphicsScene'):
        """
        Method to draw the connections between the electrodes in the layer
        """
        for el in self.connection_items:
            parent_scene.removeItem(el)

    ######################## catch all methods to add / remove all elements from scene ###################
    def add_all_items_to_scene(self, parent_scene: 'QGraphicsScene'):
        self.add_electrodes_to_scene(parent_scene)
        self.add_connections_to_scene(parent_scene)

    def remove_all_items_to_scene(self, parent_scene: 'QGraphicsScene'):
        self.remove_electrodes_to_scene(parent_scene)
        self.remove_connections_to_scene(parent_scene)
