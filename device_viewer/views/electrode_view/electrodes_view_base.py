# library imports
import math
from typing import List

import numpy as np
from PySide6.QtGui import QTransform
from traits.observation.observe import observe

# local imports
from logger.logger_service import get_logger

# enthought imports
from traits.api import Instance, Array, Str
from pyface.qt.QtCore import Qt, QPointF
from pyface.qt.QtGui import (QColor, QPen, QBrush, QFont, QPainterPath, QGraphicsPathItem, QGraphicsTextItem,
                             QGraphicsItem)

from microdrop_utils.decorators import debounce
from ...default_settings import ELECTRODE_OFF, ELECTRODE_ON, ELECTRODE_NO_CHANNEL, ELECTRODE_LINE, ELECTRODE_TEXT_COLOR, \
    CONNECTION_LINE_ON_DEFAULT, default_alphas, electrode_text_key, electrode_outline_key
from device_viewer.models.electrodes import Electrode

logger = get_logger(__name__, level='INFO')


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

    def set_active(self, color=QColor(CONNECTION_LINE_ON_DEFAULT), alpha=1.0):
        """
        Set connection item to visually active
        """
        color.setAlphaF(alpha)
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

    def set_active(self, color=QColor(CONNECTION_LINE_ON_DEFAULT), alpha=1.0):
        """
        Set connection item to visually active
        """
        color.setAlphaF(alpha)
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

    def __init__(self, id_: Str, electrode: Instance(Electrode), path_data: Array, default_alphas, parent=None):
        super().__init__(parent)

        self.color_stack = None # only supports two right now: base, and actuation layer color
        self.state_map = { # Maps electrode states to colors
            None: ELECTRODE_OFF,
            False: ELECTRODE_OFF,
            True: ELECTRODE_ON
        }

        self.electrode = electrode
        self.id = id_

        self.path = QPainterPath()
        self.path.moveTo(path_data[0][0], path_data[0][1])
        for x, y in path_data:
            self.path.lineTo(x, y)
        self.path.closeSubpath()
        self.setPath(self.path)

        self._inner_path = self._create_inner_path(self.path, scale_factor=0.8)

        # Pen for the outline
        self.pen_color = QColor(ELECTRODE_LINE)
        self.update_line_alpha(default_alphas.get(electrode_outline_key,1.0))

        # Text item
        self.text_path = QGraphicsTextItem(parent=self)
        self.text_color = QColor(ELECTRODE_TEXT_COLOR)
        self.text_path.setDefaultTextColor(self.text_color)
        self.path_extremes = [np.min(path_data[:, 0]), np.max(path_data[:, 0]),
                              np.min(path_data[:, 1]), np.max(path_data[:, 1])]
        self._fit_text_in_path(alpha=default_alphas.get(electrode_text_key, 1.0)) # Called again by electrode_layer set the proper alphas using the model

        # Make the electrode selectable and focusable
        # self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

        # Show electrode info on hover
        self.setToolTip(self._tooltip_text)

    #################################################################################
    # electrode view protected methods
    ##################################################################################

    def _create_inner_path(self, original_path, scale_factor):
        """
        Creates a scaled-down and centered version of the original path.
        """
        center = original_path.boundingRect().center()
        transform = QTransform()
        transform.translate(center.x(), center.y())
        transform.scale(scale_factor, scale_factor)
        transform.translate(-center.x(), -center.y())

        return transform.map(original_path)

    @property
    def _tooltip_text(self):
        _tooltip_text = f"Electrode ID: {self.id}\n" \
                        f"Channel: {self.electrode.channel}\n" \
                        f"Area (mm²): {self.electrode.area_scaled:.2f}"

        return _tooltip_text

    def _fit_text_in_path(self, alpha = 1.0, default_font_size: int = 8):
        """
        Method to fit the text in the center of the electrode path
        """

        text = str(self.electrode.channel)
        path_extremes = self.path_extremes

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

        new_color = QColor(self.text_color)
        new_color.setAlphaF(alpha)
        self.text_path.setDefaultTextColor(new_color)

        # Adjust the font size to fit the text in the path
        text_size = self.text_path.document().size()
        # center the text to the path
        posx = left + (right - left - text_size.width()) / 2
        posy = top + (bottom - top - text_size.height()) / 2
        self.text_path.setPos(posx, posy)

    ##################################################################################
    # Public electrode view update methods
    ##################################################################################
    def update_color(self, colors: List[QColor]):
        """
        Method to update the color of the electrode based on the state
        """
        # set the color stack: supports only two elements right now.
        self.color_stack = colors
        self.update()

    def paint(self, painter, option, widget):

        # if only one element, then only base color given
        painter.fillPath(self.path, self.color_stack[0])

        # second element should be the actuation color.
        if len(self.color_stack) > 1:
            painter.fillPath(self._inner_path, self.color_stack[1])

        # take care of the outline color
        painter.strokePath(self.path, self.pen())

    def update_label(self, alpha: float = 1.0):
        self._fit_text_in_path(alpha)

    def update_line_alpha(self, alpha: float = 1.0):
        """
        Method to update the alpha of the electrode outline
        """
        new_color = QColor(self.pen_color)
        new_color.setAlphaF(alpha)
        self.setPen(QPen(new_color, 1))

    def update_tooltip(self):
        # if tooltip toggled on, it's not empty: Needs updating to show new information.
        if self.toolTip():
            self.setToolTip(self._tooltip_text)
            logger.debug(f"{self.id}: Redrew electrode tooltip")

    def toggle_tooltip(self, checked: bool):
        if checked:
            # Set the tooltip to show on hover
            self.setToolTip(self._tooltip_text)
        else:
            self.setToolTip("")


