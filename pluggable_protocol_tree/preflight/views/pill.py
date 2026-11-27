# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The readiness pill in the status bar, and the status colours shared with
the card."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style import colour_roles
from microdrop_style.palette_helpers import css, icon_font, with_alpha
from microdrop_style.panel_theme import (
    chip_text,
    chip_tint,
    muted_text,
    readable_accent,
    role_color,
    theme_palette,
)
from microdrop_style.typography import CHIP, role_font

# Local imports.
from ..controller import PreflightController
from ..models import PreflightReport, RunInfo
from .view_consts import (
    FLASH_MS,
    ICON_RUNNING,
    RING_FADE_MS,
    RING_MIN_MS,
    RING_TURN_MS,
    STATUS_BADGES,
)

#: How far the face dims while the ring shows.
RING_DIM = 0.3

#: The ring's pen width, px, and the arc's span, degrees.
RING_WIDTH = 1.5
RING_SPAN = 100

#: Severity colour role per check / overall status; others are muted.
STATUS_SEVERITY = {
    "pass": "success",
    "warn": "warning",
    "fail": "error",
    "running": "info",
}


def status_color(status, palette, on_card=True):
    """The accent for ``status``: severity colours, or muted text."""
    severity = STATUS_SEVERITY.get(status)

    if severity is None:
        return muted_text(palette)

    color = role_color(palette, colour_roles.SEVERITY[severity])

    return readable_accent(color, palette) if on_card else color


def pill_face(report, run_info):
    """The pill's ``(glyph, text, status)`` for the report or the run."""
    if run_info.active:
        return ICON_RUNNING, run_info.progress_line, "running"

    overall = report.overall

    if overall == "fail":
        return STATUS_BADGES["fail"], str(report.blocking_count), "fail"

    if overall == "warn":
        return STATUS_BADGES["warn"], str(report.warning_count), "warn"

    return STATUS_BADGES["pass"], "Ready", "pass"


class _Ring(QtWidgets.QWidget):
    """A thin arc turning around the status glyph; see-through to the mouse."""

    def __init__(self, parent):
        super().__init__(parent)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.color = QtGui.QColor()
        self.angle = 0
        self.opacity = 0.0

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        color = QtGui.QColor(self.color)
        color.setAlphaF(self.opacity * 0.7)

        inset = RING_WIDTH
        rect = QtCore.QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)

        pen = QtGui.QPen(color, RING_WIDTH)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)

        painter.setPen(pen)
        painter.drawArc(rect, -self.angle * 16, RING_SPAN * 16)


class ReadinessPill(QtWidgets.QFrame):
    """A small rounded chip: a status shape and a count."""

    #: Pressed.
    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("preflightPill")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 1, 10, 1)
        layout.setSpacing(4)

        self._glyph = QtWidgets.QLabel()
        self._glyph.setFont(icon_font(14))

        self._text = QtWidgets.QLabel()
        self._text.setFont(role_font(CHIP))

        layout.addWidget(self._glyph)
        layout.addWidget(self._text)

        self._flashing = False
        self._face = ("", "", "pass")

        self._ring = _Ring(self)
        self._ring.hide()

        # The face dims through effects, off while the ring is not showing.
        self._dims = []

        for label in (self._glyph, self._text):
            effect = QtWidgets.QGraphicsOpacityEffect(label)
            effect.setEnabled(False)
            label.setGraphicsEffect(effect)
            self._dims.append(effect)

        self._checking = False
        self._shown_at = QtCore.QElapsedTimer()

        self._fade = QtCore.QVariantAnimation(self, duration=RING_FADE_MS)
        self._fade.valueChanged.connect(self._apply_ring_level)
        self._fade.finished.connect(self._on_fade_finished)

        self._spin = QtCore.QVariantAnimation(
            self, duration=RING_TURN_MS, startValue=0, endValue=360, loopCount=-1
        )
        self._spin.valueChanged.connect(self._turn_ring)

    def set_checking(self, checking):
        """Show the re-checking ring (faded in) or let it go (faded out,
        once it has shown RING_MIN_MS)."""
        if checking == self._checking:
            return

        self._checking = checking

        if checking:
            self._shown_at.start()
            self._fade_to(1.0)

            return

        wait = max(RING_MIN_MS - self._shown_at.elapsed(), 0)
        QtCore.QTimer.singleShot(wait, self._release_ring)

    def stop_ring(self):
        """Stop the ring at once, as before the pill is deleted."""
        self._checking = False
        self._fade.stop()
        self._spin.stop()
        self._ring.hide()

    def _release_ring(self):
        if not self._checking:
            self._fade_to(0.0)

    def _fade_to(self, level):
        if level > 0.0:
            self._ring.setGeometry(self._glyph.geometry())
            self._ring.show()
            self._spin.start()

            for effect in self._dims:
                effect.setEnabled(True)

        self._fade.stop()
        self._fade.setStartValue(self._ring.opacity)
        self._fade.setEndValue(level)
        self._fade.start()

    def _apply_ring_level(self, level):
        self._ring.opacity = level
        self._ring.update()

        for effect in self._dims:
            effect.setOpacity(1.0 - RING_DIM * level)

    def _on_fade_finished(self):
        if self._ring.opacity > 0.0:
            return

        self._spin.stop()
        self._ring.hide()

        for effect in self._dims:
            effect.setEnabled(False)

    def _turn_ring(self, angle):
        self._ring.angle = angle
        self._ring.update()

    def resizeEvent(self, event):
        self._ring.setGeometry(self._glyph.geometry())
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def show_face(self, glyph, text, status):
        """Show ``glyph`` and ``text`` tinted for ``status`` (unless a flash
        is up)."""
        self._face = (glyph, text, status)

        if not self._flashing:
            self._paint(glyph, text, status)

    def flash_all_clear(self):
        """Show "All clear" briefly, then the normal face again."""
        self._flashing = True
        self._paint(STATUS_BADGES["pass"], "All clear", "pass", strong=True)

        QtCore.QTimer.singleShot(FLASH_MS, self._end_flash)

    def _end_flash(self):
        self._flashing = False
        self._paint(*self._face)

    def _paint(self, glyph, text, status, strong=False):
        palette = theme_palette()
        accent = status_color(status, palette, on_card=False)
        tint = chip_tint(palette) * (1.8 if strong else 1.0)
        color = css(chip_text(accent, palette))

        self._ring.color = chip_text(accent, palette)
        self._glyph.setText(glyph)
        self._text.setText(text)
        self._glyph.setStyleSheet(f"color: {color};")
        self._text.setStyleSheet(f"color: {color};")
        self.setStyleSheet(
            "#preflightPill {"
            f" background: {css(with_alpha(accent, tint))};"
            " border: none; border-radius: 10px; }"
            " #preflightPill:hover {"
            f" background: {css(with_alpha(accent, tint + 0.1))}; }}"
        )


class PillController(HasTraits):
    """Keeps a pill in step with the report and the run."""

    #: The pre-flight report.
    report = Instance(PreflightReport)

    #: The run in progress, if any.
    run_info = Instance(RunInfo)

    #: The pill drawn.
    pill = Instance(ReadinessPill)

    #: The controller whose ``checking`` flag the ring follows.
    controller = Instance(PreflightController)

    @observe("controller.checking, run_info.active, pill")
    def _update_ring(self, event):
        if None in (self.pill, self.controller, self.run_info):
            return

        self.pill.set_checking(self.controller.checking and not self.run_info.active)

    @observe(
        "report.[overall, warning_count, blocking_count, summary, scope_line, "
        "stats_line], run_info.[active, progress_line], pill"
    )
    def _update_pill(self, event):
        if None in (self.pill, self.report, self.run_info):
            return

        self.pill.show_face(*pill_face(self.report, self.run_info))

        if self.run_info.active:
            self.pill.setToolTip(f"Running · {self.run_info.progress_line}")

        else:
            report = self.report
            self.pill.setToolTip(
                f"{report.summary}\n{report.scope_line}\n{report.stats_line}"
            )
