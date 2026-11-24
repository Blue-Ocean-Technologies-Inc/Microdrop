# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A drawer section: a designed header that collapses and expands its
contents with a short animation, and a handle under the contents that drags
their height::

    (◉) Section title  [ 3 new ]                         ⌄
        …contents…
                       ━━━━

The header's glyph and colour come from the section's SectionStyle, like the
colour-coded sections of a phone's news app. The section model is the
product's NotificationSection; its ``expanded``, ``title`` and ``summary``
drive the header. Runs standalone against a section::

    DrawerSection(NotificationSection(title="Plugins", factory=QLabel)).show()
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, HasTraits, Instance, observe
from traits.observation.api import trait

# Microdrop package imports.
from notifications.consts import NotificationSection

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_EXPAND_MORE

# Local imports.
from .ux_consts import (
    DEFAULT_SECTION_STYLE,
    SECTION_ANIMATION_MS,
    SECTION_GRIP_HEIGHT,
    SECTION_MIN_HEIGHT,
    SECTION_STYLES,
)
from .view_styles import (
    icon_font,
    muted_text,
    readable_accent,
    text_font,
    with_alpha,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Height (px) of a section header, and of its glyph's disc.
HEADER_HEIGHT = 40
DISC_SIZE = 26

#: Most height (px) a dragged section takes.
SECTION_MAX_HEIGHT = 900

#: The largest widget height Qt allows.
_UNBOUNDED = 16_777_215

_ALIGN = QtCore.Qt.AlignmentFlag
_LEFT_MIDDLE = _ALIGN.AlignLeft | _ALIGN.AlignVCenter


class SectionHeader(QtWidgets.QAbstractButton):
    """Glyph disc, title, summary chip and a chevron that turns as the
    section opens. Painted, so it costs one widget."""

    def __init__(self, style, parent=None):
        super().__init__(parent)

        self.style_ = style
        self.title = ""
        self.summary = ""

        #: 0 collapsed, 1 expanded; animated between.
        self._openness = 1.0

        self.setFixedHeight(HEADER_HEIGHT)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed
        )

        self._turn = QtCore.QVariantAnimation(self)
        self._turn.setDuration(SECTION_ANIMATION_MS)
        self._turn.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._turn.valueChanged.connect(self._set_openness)

    def show_section(self, title, summary, expanded, animate):
        """Show ``title`` and ``summary``, the chevron turned for
        ``expanded``."""
        self.title, self.summary = title, summary
        target = 1.0 if expanded else 0.0
        self.setToolTip(f"{'Collapse' if expanded else 'Expand'} {title.lower()}")

        if animate and target != self._openness:
            self._turn.stop()
            self._turn.setStartValue(self._openness)
            self._turn.setEndValue(target)
            self._turn.start()

        else:
            self._openness = target

        self.update()

    def _set_openness(self, value):
        self._openness = value
        self.update()

    def sizeHint(self):
        return QtCore.QSize(200, HEADER_HEIGHT)

    def paintEvent(self, event):
        palette = self.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        text_color = palette.color(QtGui.QPalette.ColorRole.Text)
        accent = QtGui.QColor(self.style_.accent)
        readable = readable_accent(accent, palette)
        rect = self.rect().adjusted(0, 3, 0, -3)

        if self.underMouse():
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(with_alpha(text_color, 0.06))
            painter.drawRoundedRect(QtCore.QRectF(rect), 7, 7)

        # The glyph on a tinted disc.
        disc = QtCore.QRectF(6, (self.height() - DISC_SIZE) / 2, DISC_SIZE, DISC_SIZE)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(accent, 0.18))
        painter.drawEllipse(disc)
        painter.setFont(icon_font(17))
        painter.setPen(readable)
        painter.drawText(disc, _ALIGN.AlignCenter, self.style_.glyph)

        # The chevron, turned from pointing right (collapsed) to down.
        chevron = QtCore.QRectF(self.width() - 30, 0, 24, self.height())
        painter.save()
        painter.translate(chevron.center())
        painter.rotate(-90 * (1 - self._openness))
        painter.setFont(icon_font(20))
        painter.setPen(muted_text(palette))
        painter.drawText(
            QtCore.QRectF(-12, -12, 24, 24), _ALIGN.AlignCenter, ICON_EXPAND_MORE
        )
        painter.restore()

        # The title, then the summary chip as room allows.
        title_font = text_font(self.font(), 1.0, QtGui.QFont.Weight.Bold)
        metrics = QtGui.QFontMetrics(title_font)
        left = int(disc.right()) + 10
        room = int(chevron.left()) - 8 - left
        title = metrics.elidedText(self.title, QtCore.Qt.TextElideMode.ElideRight, room)
        title_width = metrics.horizontalAdvance(title)

        painter.setFont(title_font)
        painter.setPen(text_color)
        painter.drawText(
            QtCore.QRect(left, 0, title_width + 2, self.height()), _LEFT_MIDDLE, title
        )

        chip_room = room - title_width - 10

        if self.summary and chip_room > 28:
            self._paint_chip(
                painter, left + title_width + 10, chip_room, accent, readable
            )

    def _paint_chip(self, painter, left, room, accent, readable):
        font = text_font(self.font(), -1.0, QtGui.QFont.Weight.DemiBold)
        metrics = QtGui.QFontMetrics(font)
        text = metrics.elidedText(
            self.summary, QtCore.Qt.TextElideMode.ElideRight, room - 16
        )
        width = metrics.horizontalAdvance(text) + 16
        height = metrics.height() + 4
        chip = QtCore.QRectF(left, (self.height() - height) / 2, width, height)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(accent, 0.16))
        painter.drawRoundedRect(chip, height / 2, height / 2)
        painter.setFont(font)
        painter.setPen(readable)
        painter.drawText(chip, _ALIGN.AlignCenter, text)


class SectionGrip(QtWidgets.QWidget):
    """The drag handle under a section's contents; ``dragged`` carries the
    pixels moved since the press."""

    pressed = QtCore.Signal()
    dragged = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._press_y = None

        self.setFixedHeight(SECTION_GRIP_HEIGHT)
        self.setCursor(QtCore.Qt.CursorShape.SplitVCursor)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip("Drag to resize this section")

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        text = self.palette().color(QtGui.QPalette.ColorRole.Text)
        active = self.underMouse() or self._press_y is not None
        middle = self.height() / 2

        painter.setPen(QtGui.QPen(with_alpha(text, 0.08), 1))
        painter.drawLine(
            QtCore.QPointF(8, middle), QtCore.QPointF(self.width() - 8, middle)
        )

        bar = QtCore.QRectF(self.width() / 2 - 18, middle - 2, 36, 4)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(text, 0.45 if active else 0.2))
        painter.drawRoundedRect(bar, 2, 2)

    def mousePressEvent(self, event):
        self._press_y = event.globalPosition().y()
        self.pressed.emit()
        event.accept()

    def mouseMoveEvent(self, event):

        if self._press_y is not None:
            self.dragged.emit(int(event.globalPosition().y() - self._press_y))

        event.accept()

    def mouseReleaseEvent(self, event):
        self._press_y = None
        self.update()
        event.accept()


class _SectionBody(QtWidgets.QWidget):
    """Holds a section's contents at a preferred height it may shrink from."""

    def __init__(self, height, springy, parent=None):
        super().__init__(parent)

        self.preferred_height = height
        self.springy = springy

        #: Contents that say how high they need to be (a card list) get no
        #: more than that, up to ``preferred_height``, until dragged.
        self.fits_contents = True
        self.contents = None

        vertical = (
            QtWidgets.QSizePolicy.Policy.Expanding
            if springy
            else QtWidgets.QSizePolicy.Policy.Maximum
        )
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, vertical)
        self.setMinimumHeight(0 if springy else SECTION_MIN_HEIGHT)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

    def sizeHint(self):
        height = self.preferred_height or 240
        needed = getattr(self.contents, "content_height", None)

        if self.fits_contents and needed is not None and not self.springy:
            height = max(min(needed(), height), SECTION_MIN_HEIGHT)

        return QtCore.QSize(200, height)


class _SectionBinding(HasTraits):
    """Shows the section model's changes in its view."""

    section = Instance(NotificationSection)

    view = Any()

    @observe("section:[title, summary, expanded]")
    def _show_header(self, event):
        self.view.show_header(animate=event.name == "expanded")

    @observe("section:expanded")
    def _show_expanded(self, event):
        self.view.show_expanded(animate=True)

    # Only the prototype's own sections have ``available``.
    @observe(trait("section", notify=False).trait("available", optional=True))
    def _show_available(self, event):
        self.view.setVisible(event.new)


class DrawerSection(QtWidgets.QWidget):
    """A section's header, its contents, and their height handle.

    ``heights`` (a dict) remembers dragged heights by section id, for the
    session.
    """

    #: The section opened or closed: whether it takes the remaining height
    #: may have changed.
    springiness_changed = QtCore.Signal()

    def __init__(self, section, heights=None, parent=None):
        super().__init__(parent)

        self.section = section
        self.style_ = SECTION_STYLES.get(section.id, DEFAULT_SECTION_STYLE)
        self._heights = {} if heights is None else heights

        #: What the factory built: a QWidget, or a TraitsUI UI around one.
        self._contents = None
        self._grip_start = 0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = SectionHeader(self.style_, self)
        self.header.clicked.connect(self._toggle)
        layout.addWidget(self.header)

        height = self._heights.get(section.id, self.style_.height)
        self.body = _SectionBody(height, self.style_.springy, self)
        self.body.fits_contents = section.id not in self._heights
        layout.addWidget(self.body, 1 if self.style_.springy else 0)

        self.grip = SectionGrip(self)
        self.grip.pressed.connect(self._start_drag)
        self.grip.dragged.connect(self._drag)
        layout.addWidget(self.grip)

        self._fold = QtCore.QPropertyAnimation(self.body, b"maximumHeight", self)
        self._fold.setDuration(SECTION_ANIMATION_MS)
        self._fold.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._fold.finished.connect(self._fold_finished)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Expanding
            if self.style_.springy
            else QtWidgets.QSizePolicy.Policy.Maximum,
        )

        self._binding = _SectionBinding(section=section, view=self)
        self.setVisible(getattr(section, "available", True))
        self.show_header(animate=False)
        self.show_expanded(animate=False)

    @property
    def springy(self):
        """Whether the section takes the drawer's remaining height, open."""
        return self.style_.springy and self.section.expanded

    # ------------------------------------------------------------------ #
    # Header and folding                                                  #
    # ------------------------------------------------------------------ #

    def show_header(self, animate):
        section = self.section

        self.header.show_section(
            section.title, section.summary, section.expanded, animate
        )

    def show_expanded(self, animate):
        expanded = self.section.expanded

        if expanded and self._contents is None:
            self._build_contents()

        self.grip.setVisible(expanded and not self.style_.springy)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Expanding
            if self.springy
            else QtWidgets.QSizePolicy.Policy.Maximum,
        )
        self.springiness_changed.emit()

        if not animate or not self.isVisible():
            self._fold.stop()
            self.body.setMaximumHeight(_UNBOUNDED)
            self.body.setVisible(expanded)
            self.updateGeometry()

            return

        self._fold.stop()

        if expanded:
            # The springy section opens towards half the drawer; the layout
            # then gives it all that is left.
            if self.style_.springy:
                target = max(self.parentWidget().height() // 2, 200)

            else:
                target = self.body.sizeHint().height()

            self.body.setMinimumHeight(0)
            self.body.setMaximumHeight(0)
            self.body.show()
            self._fold.setStartValue(0)
            self._fold.setEndValue(target)

        else:
            self.body.setMinimumHeight(0)
            self._fold.setStartValue(self.body.height())
            self._fold.setEndValue(0)

        self._fold.start()

    def _fold_finished(self):
        expanded = self.section.expanded

        self.body.setVisible(expanded)
        self.body.setMaximumHeight(_UNBOUNDED)
        self.body.setMinimumHeight(0 if self.style_.springy else SECTION_MIN_HEIGHT)
        self.updateGeometry()

    def _toggle(self):
        self.section.expanded = not self.section.expanded

    # ------------------------------------------------------------------ #
    # Height                                                              #
    # ------------------------------------------------------------------ #

    def _start_drag(self):
        self._grip_start = self.body.height()

    def _drag(self, moved):
        height = min(
            max(self._grip_start + moved, SECTION_MIN_HEIGHT), SECTION_MAX_HEIGHT
        )

        self.body.fits_contents = False
        self.body.preferred_height = height
        self._heights[self.section.id] = height
        self.body.updateGeometry()

    # ------------------------------------------------------------------ #
    # Contents                                                            #
    # ------------------------------------------------------------------ #

    def _build_contents(self):
        """Run the section's factory; a failure shows in place of it."""

        try:
            self._contents = self.section.factory(self.body)

        except Exception as error:
            logger.exception(f"Notification section {self.section.id} failed")
            self._contents = QtWidgets.QLabel(f"Could not show this: {error}")

        widget = getattr(self._contents, "control", self._contents)
        self.body.contents = widget
        self.body.layout().addWidget(widget)

        if hasattr(widget, "content_changed"):
            widget.content_changed.connect(self.body.updateGeometry)

    def dispose(self):
        """Dispose the contents' TraitsUI UI or list, and stop following the
        section."""
        self._binding.section = None
        dispose = getattr(self._contents, "dispose", None)

        if dispose is not None:
            dispose()

        self._contents = None
