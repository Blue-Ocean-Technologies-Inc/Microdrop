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
urgent notification counted, "99+" past 99, hidden at zero; a small moon
while quiet. When the count goes up the bell swings and the pill pops. A
click emits ``clicked``.

One painted widget, built at launch: the only thing the plugin shows before
anything is used. Runs standalone against just a model::

    NotificationBellIndicator(pane_model=NotificationsPaneModel()).widget.show()
"""

# Standard library imports.
import math

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Bool, HasTraits, Instance, Int, observe

# Microdrop package imports.
from microdrop_status_bar.consts import ICON_PRIORITY_RIGHTMOST

# Microdrop style imports.
from microdrop_style import colour_roles
from microdrop_style.color_contrast import label_on
from microdrop_style.colors import INFO_COLOR
from microdrop_style.icons.icons import ICON_NOTIFICATIONS, ICON_NOTIFICATIONS_ACTIVE
from microdrop_style.palette_helpers import icon_font
from microdrop_style.panel_theme import accent_of, muted_text, role_color, theme_palette
from microdrop_style.typography import CHIP, role_font

# Local imports.
from ..models.notifications_pane_model import ALERT_SEVERITY, NotificationsPaneModel
from .view_consts import BADGE_MAX_COUNT, BELL_PULSE_MS

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

_PALETTE_EVENTS = (
    QtCore.QEvent.Type.PaletteChange,
    QtCore.QEvent.Type.ApplicationPaletteChange,
)


class NotificationBellIcon(QtWidgets.QWidget):
    """The painted bell and its pill."""

    clicked = QtCore.Signal()

    #: The theme changed: the pill's colour is resolved again.
    theme_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.count = 0
        self.color = None

        #: Whether toasts are held (a protocol runs): a small moon shows.
        self.quiet = False

        #: 0-1 through the swing; 1 at rest.
        self._swing = 1.0

        #: Made on the first ring.
        self._animation = None

        self.status_bar_icon_priority = ICON_PRIORITY_RIGHTMOST
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
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

        if self._animation is None:
            self._animation = QtCore.QVariantAnimation(self)
            self._animation.setDuration(BELL_PULSE_MS)
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.valueChanged.connect(self._set_swing)

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
        return role_font(CHIP, QtGui.QFont.Weight.Bold)

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
        palette = theme_palette()
        progress = self._swing
        angle = SWING_DEGREES * math.sin(progress * math.pi * 5) * (1 - progress)
        bell = QtCore.QRectF(2, (self.height() - BELL_SIZE) / 2, BELL_SIZE, BELL_SIZE)
        glyph_color = QtGui.QColor(self.color) if self.count else muted_text(palette)

        if self.underMouse():
            glyph_color = (
                glyph_color.lighter(115)
                if self.count
                else palette.color(QtGui.QPalette.ColorRole.Text)
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
            self._paint_badge(painter, bell, progress, palette)

    def _paint_badge(self, painter, bell, progress, palette):
        pop = 1 + 0.3 * math.sin(min(progress * 2.5, 1.0) * math.pi)
        width = self._badge_width()
        left = bell.center().x() + BADGE_OFFSET
        badge = QtCore.QRectF(left, 1, width, BADGE_HEIGHT)
        center = badge.center()
        fill = QtGui.QColor(self.color)

        painter.save()
        painter.translate(center)
        painter.scale(pop, pop)
        painter.translate(-center)

        # A ring of the status bar's own colour parts the pill from the bell.
        ring = palette.color(QtGui.QPalette.ColorRole.Window)
        painter.setPen(QtGui.QPen(ring, 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(badge, BADGE_HEIGHT / 2, BADGE_HEIGHT / 2)

        painter.setFont(self._badge_font())
        painter.setPen(QtGui.QColor(label_on(fill.name())))
        painter.drawText(
            badge.adjusted(0, 0, 0, -0.5), _ALIGN.AlignCenter, self._badge_text()
        )
        painter.restore()

    def event(self, event):

        if event.type() in _PALETTE_EVENTS:
            self.theme_changed.emit()

        return super().event(event)

    def mousePressEvent(self, event):

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            event.accept()
            self.clicked.emit()

            return

        super().mousePressEvent(event)


def bell_tooltip_counts(model):
    """The bell's counts in words, e.g. "2 need attention · 3 new"."""
    parts = []

    if model.bell_attention:
        verb = "needs" if model.bell_attention == 1 else "need"
        parts.append(f"{model.bell_attention} {verb} attention")

    if model.bell_new:
        parts.append(f"{model.bell_new} new")

    return " \u00b7 ".join(parts) or "nothing new"


class NotificationBellIndicator(HasTraits):
    """Keeps the bell in step with the model's bell count."""

    pane_model = Instance(NotificationsPaneModel)

    widget = Instance(NotificationBellIcon)

    #: The count shown, to ring only when it goes up.
    _shown = Int(0)

    #: Whether a refresh is queued.
    _refresh_queued = Bool(False)

    def _widget_default(self):
        widget = NotificationBellIcon()
        widget.theme_changed.connect(self._queue_refresh)

        # Its first paint shows what was posted before it was built.
        self._queue_refresh()

        return widget

    @observe("pane_model.[bell_count, bell_severity, bell_attention, bell_new]")
    @observe("pane_model:toasts:quiet")
    def _queue_refresh(self, event=None):
        """Show the count once the current changes are done, never in the
        middle of a chain of them (#1134)."""

        if not self._refresh_queued:
            self._refresh_queued = True
            QtCore.QTimer.singleShot(0, self.refresh)

    def refresh(self):
        """Show the count, its colour and the quiet mark; ring when the
        count went up."""
        self._refresh_queued = False

        if self.pane_model is None:
            return

        model = self.pane_model
        count = model.bell_count
        quiet = model.toasts.quiet

        self.widget.show_count(count, self._color(), quiet)

        if count > self._shown:
            self.widget.ring()

        self._shown = count

        tooltip = f"Notifications: {bell_tooltip_counts(model)}. Click to show them."

        if quiet:
            tooltip += (
                "\nQuiet while the protocol runs: only errors and actions pop up."
            )

        self.widget.setToolTip(tooltip)

    def _color(self):
        palette = theme_palette()
        severity = self.pane_model.bell_severity

        if severity == ALERT_SEVERITY and self.pane_model.bell_accent:
            return accent_of(self.pane_model.bell_accent, palette).name()

        if severity in colour_roles.SEVERITY:
            return role_color(palette, colour_roles.SEVERITY[severity]).name()

        return None
