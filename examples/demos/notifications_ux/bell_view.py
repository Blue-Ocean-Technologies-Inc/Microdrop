# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The status-bar bell: a count pill over its shoulder, coloured by the most
urgent notification counted, "99+" past 99, hidden at zero. When the count
goes up the bell swings and the pill pops. A click emits ``clicked``.

Runs standalone against just a model::

    UxBellIndicator(pane_model=UxPaneModel()).widget.show()
"""

# Standard library imports.
import math

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Bool, HasTraits, Instance, Int, observe

# Microdrop package imports.
from microdrop_status_bar.consts import ICON_PRIORITY_RIGHTMOST
from notifications.consts import SEVERITY_COLORS

# Microdrop style imports.
from microdrop_style.colors import INFO_COLOR, WHITE
from microdrop_style.icons.icons import ICON_NOTIFICATIONS, ICON_NOTIFICATIONS_ACTIVE

# Local imports.
from .ux_consts import BADGE_MAX_COUNT, BELL_PULSE_MS, FEED_SEVERITY
from .ux_models import UxPaneModel
from .view_styles import icon_font, muted_text, text_font

#: Pixel size of the bell glyph.
BELL_SIZE = 20

#: Height (px) of the count pill, and how far it sits right of the bell's
#: centre.
BADGE_HEIGHT = 15
BADGE_OFFSET = 3

#: The quiet mark: a moon at the bell's lower left, and its pixel size.
QUIET_GLYPH = "bedtime"
QUIET_SIZE = 12

#: Most degrees the bell swings either way when the count goes up.
SWING_DEGREES = 16

_ALIGN = QtCore.Qt.AlignmentFlag


class UxBellIcon(QtWidgets.QWidget):
    """The painted bell and its pill."""

    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.count = 0
        self.color = None

        #: Whether toasts are held (a protocol runs): a small moon shows.
        self.quiet = False

        #: 0-1 through the swing; 1 at rest.
        self._swing = 1.0

        self.status_bar_icon_priority = ICON_PRIORITY_RIGHTMOST
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)

        self._animation = QtCore.QVariantAnimation(self)
        self._animation.setDuration(BELL_PULSE_MS)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._set_swing)

        self._fit()

    def show_count(self, count, color, quiet=False):
        """Show ``count`` in a ``color`` pill (nothing at zero), and the
        quiet mark."""
        self.count = count
        self.color = color
        self.quiet = quiet
        self._fit()
        self.update()

    def ring(self):
        """Swing the bell and pop the pill."""
        self._animation.stop()
        self._animation.start()

    def bell_center(self):
        """The bell's centre, in this widget's coordinates."""
        return QtCore.QPoint(BELL_SIZE // 2 + 2, self.height() // 2)

    def _badge_text(self):
        return (
            f"{BADGE_MAX_COUNT}+" if self.count > BADGE_MAX_COUNT else str(self.count)
        )

    def _badge_font(self):
        return text_font(self.font(), -2.0, QtGui.QFont.Weight.Bold)

    def _badge_width(self):
        if not self.count:
            return 0

        metrics = QtGui.QFontMetrics(self._badge_font())

        return max(metrics.horizontalAdvance(self._badge_text()) + 9, BADGE_HEIGHT)

    def _fit(self):
        width = max(
            BELL_SIZE + 4, BELL_SIZE // 2 + BADGE_OFFSET + self._badge_width() + 2
        )
        self.setFixedSize(width + 4, max(BELL_SIZE + 6, 24))

    def _set_swing(self, value):
        self._swing = value
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        progress = self._swing
        angle = SWING_DEGREES * math.sin(progress * math.pi * 5) * (1 - progress)

        bell = QtCore.QRectF(2, (self.height() - BELL_SIZE) / 2, BELL_SIZE, BELL_SIZE)
        glyph_color = QtGui.QColor(self.color) if self.count else muted_text(palette)

        if self.underMouse():
            glyph_color = (
                palette.color(QtGui.QPalette.ColorRole.Text)
                if not self.count
                else glyph_color.lighter(115)
            )

        # The bell hangs from its top: it swings about there.
        painter.save()
        pivot = QtCore.QPointF(bell.center().x(), bell.top() + 2)
        painter.translate(pivot)
        painter.rotate(angle)
        painter.translate(-pivot)
        painter.setFont(icon_font(BELL_SIZE))
        painter.setPen(glyph_color)
        painter.drawText(
            bell,
            _ALIGN.AlignCenter,
            ICON_NOTIFICATIONS_ACTIVE if self.count else ICON_NOTIFICATIONS,
        )
        painter.restore()

        if self.quiet:
            moon = QtCore.QRectF(
                bell.left() - 3, bell.bottom() - QUIET_SIZE + 3, QUIET_SIZE, QUIET_SIZE
            )
            painter.setFont(icon_font(QUIET_SIZE))
            painter.setPen(QtGui.QColor(INFO_COLOR))
            painter.drawText(moon, _ALIGN.AlignCenter, QUIET_GLYPH)

        if self.count:
            self._paint_badge(painter, bell, progress)

    def _paint_badge(self, painter, bell, progress):
        pop = 1 + 0.3 * math.sin(min(progress * 2.5, 1.0) * math.pi)
        width = self._badge_width()
        left = bell.center().x() + BADGE_OFFSET
        badge = QtCore.QRectF(left, 1, width, BADGE_HEIGHT)
        center = badge.center()

        painter.save()
        painter.translate(center)
        painter.scale(pop, pop)
        painter.translate(-center)

        # A ring of the status bar's own colour parts the pill from the bell.
        ring = self.palette().color(QtGui.QPalette.ColorRole.Window)
        painter.setPen(QtGui.QPen(ring, 2))
        painter.setBrush(QtGui.QColor(self.color))
        painter.drawRoundedRect(badge, BADGE_HEIGHT / 2, BADGE_HEIGHT / 2)

        painter.setFont(self._badge_font())
        painter.setPen(QtGui.QColor(WHITE))
        painter.drawText(
            badge.adjusted(0, 0, 0, -0.5), _ALIGN.AlignCenter, self._badge_text()
        )
        painter.restore()

    def mousePressEvent(self, event):

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            event.accept()
            self.clicked.emit()

            return

        super().mousePressEvent(event)


class UxBellIndicator(HasTraits):
    """Keeps the bell in step with the model's bell count."""

    pane_model = Instance(UxPaneModel)

    widget = Instance(UxBellIcon)

    #: The count shown, to ring only when it goes up.
    _shown = Int(0)

    #: Whether a refresh is queued.
    _refresh_queued = Bool(False)

    def _widget_default(self):
        return UxBellIcon()

    @observe("pane_model.[bell_count, bell_severity]")
    @observe("pane_model:toasts:quiet")
    @observe("pane_model:center:bulk_changed")
    def _queue_refresh(self, event):
        """Show the count once the current changes are done: the count is a
        Property, and one changed while its change is being announced can
        reach a late observer with the stale value."""

        if not self._refresh_queued:
            self._refresh_queued = True
            QtCore.QTimer.singleShot(0, self._show_count)

    def _show_count(self):
        """Show the count and its colour; ring when it went up."""
        self._refresh_queued = False

        if self.pane_model is None:
            return

        count = self.pane_model.bell_count
        severity = self.pane_model.bell_severity
        color = SEVERITY_COLORS.get(severity)

        # Only news posts counted: the newest one's publisher's colour.
        if severity == FEED_SEVERITY:
            unread = [entry for entry in self.pane_model.feed_alerts if entry.unread]
            color = unread[-1].feed_accent if unread else INFO_COLOR

        quiet = self.pane_model.toasts.quiet

        self.widget.show_count(count, color, quiet)

        if count > self._shown:
            self.widget.ring()

        self._shown = count

        if count:
            tooltip = f"Notifications: {count} new. Click to show them."

        else:
            tooltip = "Notifications: nothing new. Click to show them."

        if quiet:
            tooltip += (
                "\nQuiet while the protocol runs: only errors and actions pop up."
            )

        self.widget.setToolTip(tooltip)
