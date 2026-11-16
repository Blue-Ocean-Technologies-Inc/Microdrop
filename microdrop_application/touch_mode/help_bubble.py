# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The help bubble: a callout with a bold title and the help text, its
arrow pointing at the control it describes, kept clear of the finger.

A tooltip-type window that takes no input and never activates. Its shape
is a mask as well as a painted path, since the portable rig's X11 session
has no compositor to draw translucent corners. Instantiable on its own.
"""

# Enthought library imports.
from pyface.qt.QtCore import QPoint, QPointF, QRectF, Qt
from pyface.qt.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF, QRegion
from pyface.qt.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

# Microdrop style imports.
from microdrop_style.helpers import is_dark_mode
from microdrop_style.touch_style import TOUCH_RADIUS_PX, get_touch_colors

# Local imports.
from .consts import (
    HELP_BUBBLE_ARROW_PX,
    HELP_BUBBLE_FINGER_CLEARANCE_PX,
    HELP_BUBBLE_GAP_PX,
    HELP_BUBBLE_MAX_WIDTH_PX,
    HELP_NO_DESCRIPTION_TEXT,
)

#: Inner padding around the bubble's text.
_PADDING_PX = 10

#: Outline width of the bubble.
_BORDER_PX = 2


def place_bubble(size, anchor, finger, area):
    """Place a bubble of ``size`` (arrow included) for ``anchor``.

    It goes above the control and above the finger when there is room, else
    below both; for a tall control it stays near the finger rather than its
    far edge. It slides sideways to stay inside ``area`` and its arrow aims
    at the finger's x inside the control.

    Returns
    -------
    (QPoint, int, bool)
        The bubble's top-left, the arrow tip's x within the bubble, and
        whether the bubble is below (arrow on top).
    """
    width, height = size.width(), size.height()
    clearance = HELP_BUBBLE_FINGER_CLEARANCE_PX
    gap = HELP_BUBBLE_GAP_PX
    target_x = min(max(finger.x(), anchor.left()), anchor.right())

    top_edge = min(
        max(anchor.top(), finger.y() - 3 * clearance), finger.y() - clearance
    )
    y = top_edge - gap - height
    below = y < area.top()

    if below:
        bottom_edge = max(
            min(anchor.bottom(), finger.y() + 3 * clearance), finger.y() + clearance
        )
        y = bottom_edge + gap

    y = min(max(y, area.top()), area.bottom() + 1 - height)
    x = min(max(target_x - width // 2, area.left()), area.right() + 1 - width)

    inset = TOUCH_RADIUS_PX + HELP_BUBBLE_ARROW_PX
    arrow_x = min(max(target_x - x, inset), width - inset)

    return QPoint(x, y), arrow_x, below


class HelpBubble(QWidget):
    """The callout; ``show_topic`` fills, places and shows it."""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._arrow_x = 0
        self._below = False
        self._colors = {}

        self._title = QLabel()
        title_font = self._title.font()
        title_font.setBold(True)
        self._title.setFont(title_font)

        self._text = QLabel()
        self._text.setWordWrap(True)
        self._text.setTextFormat(Qt.TextFormat.AutoText)
        self._text.setMaximumWidth(HELP_BUBBLE_MAX_WIDTH_PX)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._text)

    def show_topic(self, topic, finger):
        """Describe ``topic`` (a HelpTopic) in the bubble, placed for a
        touch at ``finger`` (global) on the anchor's screen."""
        self._colors = get_touch_colors(QApplication.palette(), is_dark_mode())
        has_text = bool(topic.text)

        self._title.setText(topic.title)
        self._title.setVisible(bool(topic.title))
        self._text.setText(topic.text if has_text else HELP_NO_DESCRIPTION_TEXT)

        # A word-wrapped label otherwise settles on a narrow column; short
        # text keeps its natural width, long text wraps at the maximum.
        natural_width = self._text.fontMetrics().horizontalAdvance(self._text.text())
        self._text.setMinimumWidth(min(natural_width + 2, HELP_BUBBLE_MAX_WIDTH_PX))

        text_color = self._colors["text"] if has_text else self._colors["disabled_text"]
        self._title.setStyleSheet(f"color: {self._colors['text']};")
        self._text.setStyleSheet(f"color: {text_color};")

        # The arrow strip is the same height on either side, so the size is
        # known before the side is.
        self._set_arrow_side(below=False)
        self.adjustSize()

        screen = QApplication.screenAt(finger) or QApplication.primaryScreen()
        top_left, self._arrow_x, below = place_bubble(
            self.size(), topic.anchor, finger, screen.availableGeometry()
        )

        self._set_arrow_side(below)
        self.move(top_left)
        self.setMask(QRegion(self._outline().toFillPolygon().toPolygon()))
        self.show()
        self.raise_()
        self.update()

    def _set_arrow_side(self, below):
        self._below = below
        arrow = HELP_BUBBLE_ARROW_PX

        self.layout().setContentsMargins(
            _PADDING_PX,
            _PADDING_PX + (arrow if below else 0),
            _PADDING_PX,
            _PADDING_PX + (0 if below else arrow),
        )

    def _outline(self):
        """The bubble's rounded body plus its arrow, as one path."""
        arrow = HELP_BUBBLE_ARROW_PX
        inset = _BORDER_PX / 2
        body = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)

        if self._below:
            body.setTop(body.top() + arrow)
            base_y, tip_y = body.top(), body.top() - arrow
        else:
            body.setBottom(body.bottom() - arrow)
            base_y, tip_y = body.bottom(), body.bottom() + arrow

        path = QPainterPath()
        path.addRoundedRect(body, TOUCH_RADIUS_PX, TOUCH_RADIUS_PX)

        tip = QPolygonF(
            [
                QPointF(self._arrow_x - arrow, base_y),
                QPointF(self._arrow_x, tip_y),
                QPointF(self._arrow_x + arrow, base_y),
            ]
        )
        arrow_path = QPainterPath()
        arrow_path.addPolygon(tip)
        arrow_path.closeSubpath()

        return path.united(arrow_path)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(self._colors.get("accent", "#000000")), _BORDER_PX))
        painter.setBrush(QColor(self._colors.get("base", "#ffffff")))
        painter.drawPath(self._outline())
