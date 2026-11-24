# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The status-bar bell: the unread count beside a bell coloured by the most
urgent unread notification. A click emits ``clicked``.

Two plain labels rather than a TraitsUI panel: it is built at launch, where
a TraitsUI panel costs over ten times as much. Runs standalone against just
its model: ``NotificationBellIndicator(center=NotificationCenter()).widget.show()``.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from microdrop_status_bar.consts import ICON_PRIORITY_RIGHTMOST

# Microdrop style imports.
from microdrop_style.colors import WHITE
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_style.icons.icons import ICON_NOTIFICATIONS, ICON_NOTIFICATIONS_ACTIVE

# Local imports.
from ..consts import SEVERITY_COLORS
from ..models.notification_center import NotificationCenter

#: Style of the count badge, before its colour.
BADGE_STYLE = "border-radius: 7px; padding: 0px 4px; font-weight: bold;"

#: Counts above this show as "99+".
BADGE_MAX_COUNT = 99


class NotificationBellIcon(QtWidgets.QWidget):
    """The bell glyph and its count badge; emits ``clicked`` on a left
    press (Qt synthesises one from a touch tap)."""

    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.status_bar_icon_priority = ICON_PRIORITY_RIGHTMOST

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.glyph = QtWidgets.QLabel(ICON_NOTIFICATIONS, self)
        font = QtGui.QFont(ICON_FONT_FAMILY)
        font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        self.glyph.setFont(font)
        layout.addWidget(self.glyph)

        self.badge = QtWidgets.QLabel(self)
        self.badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.badge.hide()
        layout.addWidget(self.badge)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            event.accept()
            self.clicked.emit()

            return

        super().mousePressEvent(event)


class NotificationBellIndicator(HasTraits):
    """Keeps the bell in step with the unread notifications."""

    #: The notifications counted.
    center = Instance(NotificationCenter)

    #: The widget the status bar shows.
    widget = Instance(NotificationBellIcon)

    def _widget_default(self):
        return NotificationBellIcon()

    @observe("center.[unread_count, unread_severity]")
    def _show_unread(self, event):
        count = self.center.unread_count
        bell = self.widget

        if not count:
            bell.glyph.setText(ICON_NOTIFICATIONS)
            bell.glyph.setStyleSheet("")
            bell.badge.hide()
            bell.setToolTip("Notifications: nothing new. Click to show or hide.")

            return

        color = SEVERITY_COLORS[self.center.unread_severity]
        badge_text = f"{BADGE_MAX_COUNT}+" if count > BADGE_MAX_COUNT else str(count)

        bell.glyph.setText(ICON_NOTIFICATIONS_ACTIVE)
        bell.glyph.setStyleSheet(f"color: {color};")
        bell.badge.setText(badge_text)
        bell.badge.setStyleSheet(f"{BADGE_STYLE} background: {color}; color: {WHITE};")
        bell.badge.show()
        bell.setToolTip(f"Notifications: {count} new. Click to show or hide.")
