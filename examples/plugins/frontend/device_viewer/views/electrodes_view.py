# library imports
import numpy as np

# local imports
from microdrop_utils._logger import get_logger

# enthought imports
from traits.api import Instance, Array, Str
from pyface.qt.QtCore import Qt, QRectF
from pyface.qt.QtGui import (QColor, QPen, QBrush, QFont, QPainterPath, QGraphicsPathItem, QGraphicsTextItem,
                             QGraphicsItem, QGraphicsItemGroup)

# Relative imports
from ..models.electrodes import Electrode

logger = get_logger(__name__, level='DEBUG')

default_colors = {True: '#8d99ae', False: '#0a2463', 'no-channel': '#fc8eac',
                  'droplet': '#06d6a0', 'line': '#3e92cc', 'connection': '#ffffff'}

default_alphas = {'line': 1.0, 'fill': 1.0, 'text': 1.0}


class ElectrodeView(QGraphicsPathItem):
    """
    Class defining the view for an electrode in the device viewer:

    - This view is a QGraphicsPathItem that represents the electrode as a polygon with a text label in the center.
    The view is responsible for updating the color and alpha of the electrode based on the state of the electrode.

    - The view also handles the mouse events for the electrode. The view is selectable and focusable.
    the callbacks for the clicking has to be implemented by a controller for the view.

    - The view requires an electrode model to be passed to it.
    """

    def __init__(self, id_: Str, electrode: Instance(Electrode), path_data: Array, parent=None):
        super().__init__(parent)

        self.state_map = {k: v for k, v in default_colors.items()}
        self.state_map[None] = self.state_map[False]

        self.electrode = electrode
        self.id = id_
        self.alphas = default_alphas

        if str(self.electrode.channel) == 'None':
            self.state_map[False] = default_colors['no-channel']
            self.state_map[True] = default_colors['no-channel']
            self.state_map[None] = default_colors['no-channel']

        self.path = QPainterPath()
        self.path.moveTo(path_data[0][0], path_data[0][1])
        for x, y in path_data:
            self.path.lineTo(x, y)
        self.path.closeSubpath()
        self.setPath(self.path)

        # Pen for the outline
        self.pen_color = QColor(self.state_map['line'])
        self.pen_color.setAlphaF(self.alphas['line'])
        self.pen = QPen(self.pen_color, 1)  # line color outline
        self.setPen(self.pen)

        # Brush for the fill
        self.color = QColor(self.state_map[False])
        self.color.setAlphaF(self.alphas['fill'])
        self.brush = QBrush(self.color)  # Default fill color
        self.setBrush(self.brush)

        # Text item
        self.text_path = QGraphicsTextItem(parent=self)
        self.text_color = QColor(Qt.white)
        self.text_color.setAlphaF(self.alphas['text'])
        self.text_path.setDefaultTextColor(self.text_color)
        self.path_extremes = [np.min(path_data[:, 0]), np.max(path_data[:, 0]),
                              np.min(path_data[:, 1]), np.max(path_data[:, 1])]
        self._fit_text_in_path(str(self.electrode.channel), self.path_extremes)

        # Make the electrode selectable and focusable
        self.enable_electrode()

    def enable_electrode(self):
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    def disable_electrode(self):
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.on_clicked()  # Emit the clicked signal
        super().mousePressEvent(event)  # Call the superclass method to ensure proper event handling

    def on_clicked(self):
        """
        Method to be implemented by Controller
        """
        pass

    #################################################################################
    # electrode view protected methods
    ##################################################################################

    def _fit_text_in_path(self, text: str, path_extremes, default_font_size: int = 8):
        """
        Method to fit the text in the center of the electrode path
        """
        if text == 'None':
            self.text_path.setPlainText('')
            self.state_map[False] = default_colors['no-channel']
            self.state_map[True] = default_colors['no-channel']
            self.state_map[None] = default_colors['no-channel']
        else:
            self.text_path.setPlainText(text)
            self.state_map[False] = default_colors[False]
            self.state_map[True] = default_colors[True]
            self.state_map[None] = default_colors[False]
        # Determine the font size based on the path size
        left, right, top, bottom = path_extremes
        range_x = right - left
        range_y = bottom - top
        if len(text) == 1:
            font_size = min(range_x, range_y) / 1.2
        elif len(text) == 2:
            font_size = min(range_x, range_y) / 2
        else:
            font_size = min(range_x, range_y) / 3
            if font_size < default_font_size:
                font_size = default_font_size

        self.text_path.setFont(QFont('Arial', font_size))
        # Adjust the font size to fit the text in the path
        text_size = self.text_path.document().size()
        # center the text to the path
        posx = left + (right - left - text_size.width()) / 2
        posy = top + (bottom - top - text_size.height()) / 2
        self.text_path.setPos(posx, posy)

    ##################################################################################
    # Public electrode view update methods
    ##################################################################################
    def update_color(self, state):
        """
        Method to update the color of the electrode based on the state
        """
        self.color = QColor(self.state_map.get(state, self.state_map[False]))
        self.color.setAlphaF(self.alphas['fill'])
        self.setBrush(QBrush(self.color))
        self.update()

    def update_alpha(self, line=False, fill=False, text=False, global_alpha=False):
        """
        Method to update the alpha of the electrode view
        """
        if line or global_alpha:
            self.pen_color.setAlphaF(self.alphas['line'])
            self.setPen(QPen(self.pen_color, 1))

        if fill or global_alpha:
            self.color.setAlphaF(self.alphas['fill'])
            self.setBrush(QBrush(self.color))

        if text or global_alpha:
            self.text_color.setAlphaF(self.alphas['text'])
            self.text_path.setDefaultTextColor(self.text_color)

        self.update()


class ElectrodeLayer(QGraphicsItemGroup):
    """
    Class defining the view for an electrode layer in the device viewer.

    - This view is a QGraphicsItemGroup that contains a group of electrode view objects
    - The view is responsible for updating the properties of all the electrode views contained in bulk.
    """

    def __init__(self, id_: str, electrodes, bounding_box: QRectF = None,
                 rotation: int = 0, mirror: bool = False, parent=None):
        super().__init__(parent=parent)

        self.id = id_
        self.setHandlesChildEvents(False)  # Pass events to children

        self.electrode_views = {}

        svg = electrodes.svg_model

        if bounding_box is not None:
            # Scale to bounding box
            box_offset = 40
            bounding_box_ = bounding_box.adjusted(box_offset, box_offset, -box_offset, -box_offset)
            modifier = min(bounding_box_.width() / (svg.max_x - svg.min_x),
                           bounding_box_.height() / (svg.max_y - svg.min_y))
            svg_offset = np.array([(bounding_box.width() - svg.max_x * modifier) / 2,
                                   (bounding_box.height() - svg.max_y * modifier) / 2])
        else:
            # # Scale to approx 360p resolution for display
            modifier = max(640 / (svg.max_x - svg.min_x), 360 / (svg.max_y - svg.min_y))
            svg_offset = np.array([0, 0])

        logger.debug(f"Creating Electrode Layer {id_} with {len(electrodes.electrodes)} electrodes.")

        # Create the electrode views for each electrode from the electrodes model and add them to the group
        for electrode_id, electrode in electrodes.electrodes.items():
            points = electrode.path[:, 0, :]
            points = points if not rotation else rotate_points(points, [svg.max_x / 2, svg.max_y / 2], rotation)
            points = points if not mirror else mirror_points(points, [svg.max_x / 2, svg.max_y / 2])
            self.electrode_views[electrode_id] = ElectrodeView(electrode_id, electrodes[electrode_id],
                                                               modifier * points + svg_offset)

            self.addToGroup(self.electrode_views[electrode_id])

        self._electrodes = electrodes

        # Create the connections between the electrodes
        self.connections = []
        for con in svg.connections:
            con = con if not rotation else rotate_points(con, np.array([svg.max_x / 2, svg.max_y / 2]), rotation)
            con = con if not mirror else mirror_points(con, np.array([svg.max_x / 2, svg.max_y / 2]))
            con = con * modifier + svg_offset
            self.connections.append(con)

        # Create the connection items
        self.connection_items = []

        # Draw the connections
        self.draw_connections()

    def change_alphas(self, alpha: float, **kwargs):
        """
        Method to change the alpha of the electrode views in the layer
        """
        if kwargs.get('path'):
            self.update_connection_alpha(alpha)
            kwargs.pop('path')
        for name, e in self._electrodes.items():
            for k in kwargs.keys():
                if k in ['line', 'fill', 'text']:
                    self.electrode_views[name].alphas[k] = alpha
                if k == 'global_alpha':
                    self.electrode_views[name].alphas['line'] = alpha
                    self.electrode_views[name].alphas['fill'] = alpha
                    self.electrode_views[name].alphas['text'] = alpha

            self.electrode_views[name].update_alpha(**kwargs)

    def draw_connections(self):
        """
        Method to draw the connections between the electrodes in the layer
        """
        for connection in self.connections:
            path = QPainterPath()
            coords = connection.flatten()
            path.moveTo(coords[0], coords[1])
            path.lineTo(coords[2], coords[3])

            connection_item = QGraphicsPathItem(path, parent=self)
            color = QColor(default_colors['connection'])
            color.setAlphaF(1.0)
            connection_item.setPen(QPen(color, 1))
            self.connection_items.append(connection_item)

    def update_connection_alpha(self, alpha: float):
        """
        Method to update the alpha of the connections in the layer
        """
        for item in self.connection_items:
            color = item.pen().color()
            color.setAlphaF(alpha)
            item.setPen(QPen(color, 1))
            item.update()


def rotate_points(points: np.array, center: list, angle: float):
    """ Rotate points (NumPy arrays) around a center point by a given angle in degrees. """
    angle_rad = np.radians(angle)
    cos_theta, sin_theta = np.cos(angle_rad), np.sin(angle_rad)

    # Convert points to a NumPy array if not already
    points = np.asarray(points)
    center = np.array(center)

    # Translate points so center is at origin
    translated_points = points - center

    # Create the rotation matrix
    rotation_matrix = np.array([[cos_theta, -sin_theta],
                                [sin_theta, cos_theta]])

    # Rotate points
    rotated_points = translated_points.dot(rotation_matrix)

    # Translate points back to the original center
    rotated_points += center

    return rotated_points


def mirror_points(points: np.array, center: list):
    """ Mirror points across a vertical line through the center point using NumPy. """
    points = np.asarray(points)
    center = np.array(center)

    # Mirror points
    mirrored_points = points.copy()
    mirrored_points[:, 0] = 2 * center[0] - mirrored_points[:, 0]

    return mirrored_points
