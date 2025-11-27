from PySide6.QtGui import QColor, QFont, QPolygonF, QPen, QPainterPath
from PySide6.QtWidgets import QGraphicsScene, QApplication, QGraphicsPathItem
from pyface.qt.QtCore import QPointF

from microdrop_utils.pyside_helpers import get_qcolor_lighter_percent_from_factor
from .electrodes_view_base import ElectrodeView, ElectrodeConnectionItem, ElectrodeEndpointItem
from .electrode_view_helpers import loop_is_ccw
from ...default_settings import ROUTE_CW_LOOP, ROUTE_CCW_LOOP, ROUTE_SELECTED, ELECTRODE_CHANNEL_EDITING, ELECTRODE_OFF, \
    ELECTRODE_ON, ELECTRODE_NO_CHANNEL, PERSPECTIVE_RECT_COLOR, PERSPECTIVE_RECT_COLOR_EDITING, electrode_outline_key, \
    electrode_fill_key, actuated_electrodes_key, electrode_text_key, routes_key, hovered_actuation_key, \
    hovered_electrode_key
from logger.logger_service import get_logger
from device_viewer.models.main_model import DeviceViewMainModel

logger = get_logger(__name__)

class ElectrodeLayer():
    """
    Class defining the view for an electrode layer in the device viewer. Container for the elements used to establish
    the device viewer scene.

    - This view contains a group of electrode view objects
    - The view is responsible for updating the properties of all the electrode views contained in bulk.
    """

    def __init__(self, electrodes, default_alphas: dict[int, float]):
        # Create the connection and electrode items
        self.connection_items = {}
        self.electrode_views = {}
        self.electrode_endpoints = {}
        self.reference_rect_item = None
        self.reference_rect_path_item = None

        self.svg = electrodes.svg_model

        # # Scale to approx 360p resolution for display
        modifier = max(640 / (self.svg.max_x - self.svg.min_x), 360 / (self.svg.max_y - self.svg.min_y))

        # Create the electrode views for each electrode from the electrodes model and add them to the group
        for electrode_id, electrode in electrodes.electrodes.items():
            self.electrode_views[electrode_id] = ElectrodeView(electrode_id, electrodes[electrode_id],
                                                               modifier * electrode.path, default_alphas=default_alphas)
            self.electrode_endpoints[electrode_id] = ElectrodeEndpointItem(electrode_id,
                    QPointF(self.svg.electrode_centers[electrode_id][0] * modifier, self.svg.electrode_centers[electrode_id][1] * modifier), 8)

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
        for electrode_id, endpoint_view in self.electrode_endpoints.items():
            parent_scene.removeItem(endpoint_view)

    ######################## catch all methods to add / remove all elements from scene ###################
    def add_all_items_to_scene(self, parent_scene: 'QGraphicsScene'):
        self.add_electrodes_to_scene(parent_scene)
        self.add_connections_to_scene(parent_scene)
        self.add_endpoints_to_scene(parent_scene)

        self.reference_rect_item = parent_scene.addPolygon(QPolygonF(), QPen(QColor(PERSPECTIVE_RECT_COLOR), 3))

        self.reference_rect_path_item = QGraphicsPathItem()
        self.reference_rect_path_item.setPen(QPen(QColor(PERSPECTIVE_RECT_COLOR_EDITING), 2))
        parent_scene.addItem(self.reference_rect_path_item)

    def remove_all_items_to_scene(self, parent_scene: 'QGraphicsScene'):
        self.remove_electrodes_to_scene(parent_scene)
        self.remove_connections_to_scene(parent_scene)
        self.remove_endpoints_to_scene(parent_scene)
        parent_scene.removeItem(self.reference_rect_item)

    def toggle_electrode_tooltips(self, checked):
        for electrode_id, electrode_view in self.electrode_views.items():
            electrode_view.toggle_tooltip(checked)

    ######################## Redraw functions ###########################
    def redraw_connections_to_scene(self, model: DeviceViewMainModel):
        # Routes are applied in order, so later routes will apply on top
        # To minimize the number of overlapping Qt calls, we'll apply changes to a dictionary then transfer it to the view at the end

        connection_map = {} # Temporary map to superimpose routes
        endpoint_map = {} # Temporary map to superimpose endpoints

        layers = model.routes.layers

        if model.routes.selected_layer:
            layers = layers + [model.routes.selected_layer] # Paint the selected layer again so its always on top

        if model.routes.autoroute_layer:
            layers = layers + [model.routes.autoroute_layer] # Paint autoroute layer on top
        
        for i in range(len(layers)):
            route_layer = layers[i]
            color = QColor(route_layer.color)
            z = i # Make sure each route is it own layer. Prevents weird overlap patterns
            if route_layer == model.routes.selected_layer:
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
        alpha = model.get_alpha(routes_key)

        for key, connection_item in self.connection_items.items():
            (color, z) = connection_map.get(key, (None, None))
            if color:
                connection_item.set_active(color, alpha)
                connection_item.setZValue(z) # We want to make sure the whole route is on the same z value
            else:
                connection_item.set_inactive()
        
        for endpoint_id, endpoint_view in self.electrode_endpoints.items():
            (color, z) = endpoint_map.get(endpoint_id, (None, None))
            if color:
                endpoint_view.set_active(color, alpha)
                endpoint_view.setZValue(z)
            else:
                endpoint_view.set_inactive()
    
    def redraw_electrode_lines(self, model: DeviceViewMainModel):
        """
        Method to redraw the electrode lines in the layer
        """
        alpha = model.get_alpha(electrode_outline_key)
        for electrode_id, electrode_view in self.electrode_views.items():
            electrode_view.update_line_alpha(alpha)

    def redraw_electrode_colors(self, model: DeviceViewMainModel, electrode_hovered: ElectrodeView):
        
        for electrode_id, electrode_view in self.electrode_views.items():
            # initialize color stack
            color_stack = []

            # determine base_color:
            if electrode_view.electrode == model.electrodes.electrode_editing:
                base_color = ELECTRODE_CHANNEL_EDITING

            elif electrode_view.electrode.channel == None:
                base_color = ELECTRODE_NO_CHANNEL

            else:
                base_color = ELECTRODE_OFF

            # construct the base QColor
            base_color = QColor(base_color)
            base_color.setAlphaF(model.get_alpha(electrode_fill_key))

            # check if electrode is on to see if additional color_layer needed:
            on_color = None
            if model.electrodes.channels_states_map.get(electrode_view.electrode.channel, False):
                on_color = QColor(ELECTRODE_ON)
                on_color.setAlphaF(model.get_alpha(actuated_electrodes_key))

            # check if fills need editing if they are hovered:
            if electrode_hovered == electrode_view:
                lighter_percent = get_qcolor_lighter_percent_from_factor(base_color, model.get_alpha(hovered_electrode_key))
                base_color = base_color.lighter(lighter_percent)
                if on_color:
                    lighter_percent = get_qcolor_lighter_percent_from_factor(on_color, model.get_alpha(hovered_actuation_key))
                    on_color = on_color.lighter(lighter_percent)

            color_stack.append(base_color)
            if on_color:
                color_stack.append(on_color)

            electrode_view.update_color(color_stack)

    def redraw_electrode_labels(self, model: DeviceViewMainModel):
        alpha = model.get_alpha(electrode_text_key)
        for electrode_id, electrode_view in self.electrode_views.items():
            electrode_view.update_label(alpha)

    def redraw_reference_rect(self, model: DeviceViewMainModel, partial_rect=None):
        if len(model.camera_perspective.reference_rect) == 4:
            # Update the reference rect visualization
            self.reference_rect_item.setPolygon(QPolygonF(model.camera_perspective.transformed_reference_rect))
            self.reference_rect_path_item.setVisible(False)  # Hide the path item if we're using a polygon
            self.reference_rect_item.setVisible(True)  # Show the polygon item
        elif partial_rect is not None and len(partial_rect) > 1:
            path = QPainterPath()
            path.moveTo(partial_rect[0])
            # Draw the path for the reference rect
            for point in partial_rect[1:]:
                path.lineTo(point)
            self.reference_rect_path_item.setPath(path)
            self.reference_rect_path_item.setVisible(True)
            self.reference_rect_item.setVisible(False)  # Hide the polygon item if we're using a path

    def clear_reference_rect(self):
        """Reset the reference rectangle to its initial state."""
        self.reference_rect_item.setPolygon(QPolygonF())
        self.reference_rect_item.setVisible(False)
        self.reference_rect_path_item.setPath(QPainterPath())
        self.reference_rect_path_item.setVisible(False)

    def redraw_electrode_tooltip(self, changed_electrode_id):
        logger.debug(f"redraw_electrode_tooltip: {changed_electrode_id}")
        self.electrode_views[changed_electrode_id].update_tooltip()

    def redraw_all_electrode_tooltips(self):
        logger.debug(f"redraw_all_electrode_tooltips")
        for changed_electrode_id in self.electrode_views:
            self.redraw_electrode_tooltip(changed_electrode_id)

    def rotate_electrode_views_texts(self, angle=0):
        for electrode_view in self.electrode_views.values():
            electrode_view.rotate_electrode_text(angle)