# library imports
import numpy as np

# local imports
from microdrop_utils._logger import get_logger

# enthought imports
from traits.api import Instance, Array, Str
from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import (QColor, QPen, QBrush, QFont, QPainterPath, QGraphicsPathItem, QGraphicsTextItem,
                             QGraphicsItem)

from .default_settings import default_colors, default_alphas
from device_viewer.models.electrodes import Electrode

logger = get_logger(__name__, level='DEBUG')


# electrode connection lines
class ElectrodeConnectionItem(QGraphicsPathItem):
    def __init__(self, key, src, dst):
        # Generate path
        path = QPainterPath()
        path.moveTo(src[0], src[1])
        path.lineTo(dst[0], dst[1])

        # Initialize the parent class constructor
        super().__init__(path)

        # Add a new variable specific to this class
        self.key = key
        self.set_inactive()

    def set_active(self, color=Qt.green):
        """
        Set connection item to visually active
        """
        self.setPen(QPen(color, 5))  # Example: Set pen color to green with thickness 5

    def set_inactive(self):
        """
        Set connection item to visually inactive. This is default.
        """
        #self.setPen(QPen(QColor(default_colors['connection']), 1))
        self.setPen(Qt.NoPen)


# electrode polygons
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
        # self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

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


