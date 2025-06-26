# library imports
import math
import numpy as np

# local imports
from microdrop_utils._logger import get_logger

# enthought imports
from traits.api import Instance, Array, Str
from pyface.qt.QtCore import Qt, QPointF
from pyface.qt.QtGui import (QColor, QPen, QBrush, QFont, QPainterPath, QGraphicsPathItem, QGraphicsTextItem,
                             QGraphicsItem)

from .default_settings import ELECTRODE_OFF, ELECTRODE_ON, ELECTRODE_NO_CHANNEL, ELECTRODE_LINE, ELECTRODE_TEXT_COLOR, CONNECTION_LINE_ON_DEFAULT, default_alphas
from device_viewer.models.electrodes import Electrode

logger = get_logger(__name__, level='DEBUG')


# electrode connection lines
class ElectrodeConnectionItem(QGraphicsPathItem):
    """
    Class defining an Elecrode connection view. These are the small segments that connect neighboring electrodes, visually
    appearing to be a line segment with an arrow pointing to is directionality

    Parameters:
    - key: The connection item's id/key. A unique and addressable identifier. In electrode_layer.py, this is the tuple (from_id, to_id), where ids are for electrodes
    - src: A (relative) coordinate for where the line starts
    - dst: A (relative) coordinate for where the line ends
    """
    def __init__(self, key, src: QPointF, dst: QPointF):
        super().__init__()

        # Generate path
        path = QPainterPath()

        
        # Generate line
        path.moveTo(src)
        path.lineTo(dst)

        # Arrow start point (2/3 of the way along the line)
        start = QPointF(
            src.x() + ((dst.x() - src.x()) / (3/2)),
            src.y() + ((dst.y() - src.y()) / (3/2))
        )

        # Arrow end 'level' (along the line, 8 pixels behind start)
        # We abuse the fact that QPointF addition/scaling works exactly as vector addition/scaling for a bit cleaner computation
        end_diff = src - dst # Backwards! 
        end_diff /= math.hypot(end_diff.x(), end_diff.y()) # Normalize
        end_diff *= 4 # Scale
        end = start + end_diff
        
        # Generate ticks
        con_vec = dst - src
        perp_vec = QPointF(con_vec.y(), -con_vec.x())
        perp_vec /= math.hypot(perp_vec.x(), perp_vec.y()) # Normalize
        perp_vec *= 4 # Scale

        first_tick = end + perp_vec
        second_tick = end - perp_vec

        # Build arrowhead triangle
        path.moveTo(first_tick)
        path.lineTo(start)
        path.lineTo(second_tick)

        self.setPath(path)
   
        # Add a new variable specific to this class
        self.key = key
        self.set_inactive()

    def set_active(self, color=QColor(CONNECTION_LINE_ON_DEFAULT)):
        """
        Set connection item to visually active
        """
        self.setPen(QPen(color, 3))  # Example: Set pen color to green with thickness 5

    def set_inactive(self):
        """
        Set connection item to visually inactive. This is default.
        """
        self.setPen(Qt.NoPen)

class ElectrodeEndpointItem(QGraphicsPathItem):
    """
    Class defining an endpoint view item. Visually, appears to be a small square situated in the center of an electrode.

    Parameters:
    - electrode_id: The id of the electrode it is situated on. Also serves as an id for itself
    - centerpoint: The centerpoint of the electrode it is situated on
    - size: The size of one of the sides of the square, in the same coordinate system as centerpoint
    """
    def __init__(self, electrode_id, centerpoint: QPointF, size=5):
        super().__init__()

        # Generate path
        path = QPainterPath()
        
        current_point = centerpoint + QPointF(size/2, size/2) # First corner, top right

        path.moveTo(current_point)
        current_point += QPointF(0, -size) # Bottom right
        path.lineTo(current_point)
        current_point += QPointF(-size, 0) # Bottom left
        path.lineTo(current_point)
        current_point += QPointF(0, size) # Top left
        path.lineTo(current_point)
        path.closeSubpath()

        self.setPath(path)
   
        # Add a new variable specific to this class
        self.electrode_id = electrode_id
        self.set_inactive()

    def set_active(self, color=QColor(CONNECTION_LINE_ON_DEFAULT)):
        """
        Set connection item to visually active
        """
        self.setPen(QPen(color, 3))  # Example: Set pen color to green with thickness 5
        self.setBrush(QBrush(color))

    def set_inactive(self):
        """
        Set connection item to visually inactive. This is default.
        """
        self.setPen(Qt.NoPen)
        self.setBrush(Qt.NoBrush)


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

        self.state_map = { # Maps electrode states to colors
            None: ELECTRODE_OFF,
            False: ELECTRODE_OFF,
            True: ELECTRODE_ON
        }

        self.electrode = electrode
        self.id = id_
        self.alphas = default_alphas

        if str(self.electrode.channel) == 'None':
            self.state_map = { # Maps electrode states to colors
            None: ELECTRODE_NO_CHANNEL,
            False: ELECTRODE_NO_CHANNEL,
            True: ELECTRODE_NO_CHANNEL
        }

        self.path = QPainterPath()
        self.path.moveTo(path_data[0][0], path_data[0][1])
        for x, y in path_data:
            self.path.lineTo(x, y)
        self.path.closeSubpath()
        self.setPath(self.path)

        # Pen for the outline
        self.pen_color = QColor(ELECTRODE_LINE)
        self.pen_color.setAlphaF(self.alphas['line'])
        self.pen = QPen(self.pen_color, 1)  # line color outline
        self.setPen(self.pen)

        # Brush for the fill
        self.color = QColor(ELECTRODE_OFF)
        self.color.setAlphaF(self.alphas['fill'])
        self.brush = QBrush(self.color)  # Default fill color
        self.setBrush(self.brush)

        # Text item
        self.text_path = QGraphicsTextItem(parent=self)
        self.text_color = QColor(ELECTRODE_TEXT_COLOR)
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
        self.text_path.setPlainText(text if text != "None" else "")

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

        resized_font = QFont("Arial") # Get the default font
        resized_font.setPointSize(font_size)
        self.text_path.setFont(resized_font)
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


