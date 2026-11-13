# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What Help mode draws besides the bubble: the accent outline around the
control being described, and the banner saying the mode is on."""

# Enthought library imports.
from pyface.qt.QtCore import QPoint, QRect, Qt, Signal
from pyface.qt.QtGui import QColor, QPainter, QPen
from pyface.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

# Microdrop style imports.
from microdrop_style.colors import ACCENT_COLOR, WHITE
from microdrop_style.touch_style import TOUCH_RADIUS_PX, TOUCH_TARGET_PX

# Local imports.
from .consts import HELP_BANNER_TEXT, HELP_MODE_CONTROL_PROPERTY, HELP_OUTLINE_PX

#: Gap between the banner and the top of the window it sits over.
_BANNER_TOP_GAP_PX = 36


class HelpOutline(QWidget):
    """An accent rounded rectangle drawn over a window, around a control.
    It is a child of that window, so it stacks with it and takes no input."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def outline(self, window, rect):
        """Outline the global ``rect`` over ``window``."""

        if self.parentWidget() is not window:
            self.setParent(window)

        margin = HELP_OUTLINE_PX
        top_left = window.mapFromGlobal(rect.topLeft())

        self.setGeometry(
            QRect(top_left, rect.size()).adjusted(-margin, -margin, margin, margin)
        )
        self.show()
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(ACCENT_COLOR), HELP_OUTLINE_PX))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        inset = HELP_OUTLINE_PX // 2 + 1
        painter.drawRoundedRect(
            self.rect().adjusted(inset, inset, -inset, -inset),
            TOUCH_RADIUS_PX,
            TOUCH_RADIUS_PX,
        )


class HelpBanner(QFrame):
    """A slim pill over the top of a window while Help mode is on, with a
    Done button that ends it."""

    #: Done was pressed.
    done = Signal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("help_banner")
        self.setStyleSheet(
            f"""
QFrame#help_banner {{
    background-color: {ACCENT_COLOR};
    border-radius: {TOUCH_TARGET_PX // 2}px;
}}
QLabel {{
    color: {WHITE};
    font-weight: bold;
    background: transparent;
}}
QPushButton {{
    min-height: {TOUCH_TARGET_PX - 8}px;
    padding: 0px 18px;
    border: 2px solid {WHITE};
    border-radius: {(TOUCH_TARGET_PX - 8) // 2}px;
    background-color: transparent;
    color: {WHITE};
    font-weight: bold;
}}
"""
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 4, 4, 4)
        layout.setSpacing(16)
        layout.addWidget(QLabel(HELP_BANNER_TEXT))

        done = QPushButton("Done")
        done.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        done.setProperty(HELP_MODE_CONTROL_PROPERTY, True)
        done.clicked.connect(self.done)
        layout.addWidget(done)

    def show_over(self, window):
        """Show centred along the top of ``window``."""
        self.adjustSize()
        frame = (
            window.frameGeometry() if window is not None else self.screen().geometry()
        )

        self.move(
            QPoint(
                frame.center().x() - self.width() // 2,
                frame.top() + _BANNER_TOP_GAP_PX,
            )
        )
        self.show()
        self.raise_()
