# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Small pieces of a notification card: its meta line, its text cut to two
lines, and its "new" marker."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop package imports.
from notifications.views.formatting import format_time

# Microdrop style imports.
from microdrop_style.colors import INFO_COLOR

# Local imports.
from .ux_consts import CARD_BODY_LINES

#: Diameter (px) of the "new" marker.
NEW_DOT_SIZE = 8

_ELIDE = QtCore.Qt.TextElideMode.ElideRight

LINE_SEPARATOR = "\u2028"


def source_label(entry):
    """Who posted ``entry``, readable: "device_viewer.models" -> "Device
    viewer"."""
    source = entry.source or entry.category
    head = source.split(".")[0].replace("_", " ").strip()

    return head[:1].upper() + head[1:]


def meta_text(entry):
    """The line under the title: "Source · 3 min ago · ×2"."""
    parts = [source_label(entry), format_time(entry.last_seen)]

    if entry.count > 1:
        parts.append(f"×{entry.count}")

    return " · ".join(part for part in parts if part)


class ClampedLabel(QtWidgets.QLabel):
    """Word-wrapped text cut to ``lines`` lines with an ellipsis; 0 lines
    shows it all. ``overflowed`` says whether anything was cut."""

    overflow_changed = QtCore.Signal(bool)

    def __init__(self, parent=None, lines=CARD_BODY_LINES):
        super().__init__(parent)

        self.lines = lines
        self.overflowed = False
        self._full_text = ""

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed
        )
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.NoTextInteraction)

    def set_full_text(self, text, lines=None):
        """Show ``text``, cut to ``lines`` (default: as before)."""
        self._full_text = text
        self.lines = self.lines if lines is None else lines
        self._clamp()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self._clamp()

    def _clamp(self):
        width = max(self.width(), 40)
        metrics = QtGui.QFontMetrics(self.font())
        # QTextLayout breaks lines only at the Unicode line separator.
        laid_out = self._full_text.replace("\n", LINE_SEPARATOR)
        layout = QtGui.QTextLayout(laid_out, self.font())
        option = QtGui.QTextOption()
        option.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)

        shown = []
        layout.beginLayout()

        while True:
            line = layout.createLine()

            if not line.isValid():
                break

            line.setLineWidth(width)
            shown.append((line.textStart(), line.textLength()))

        layout.endLayout()

        overflowed = bool(self.lines) and len(shown) > self.lines
        kept = shown[: self.lines] if overflowed else shown
        texts = [
            self._full_text[start : start + length].rstrip() for start, length in kept
        ]

        if overflowed and texts:
            last = self._full_text[kept[-1][0] :].replace("\n", " ")
            texts[-1] = metrics.elidedText(last, _ELIDE, width)

        self.setText("\n".join(texts))
        self.setFixedHeight(max(len(kept), 1) * metrics.lineSpacing() + 1)

        if overflowed != self.overflowed:
            self.overflowed = overflowed
            self.overflow_changed.emit(overflowed)


class NewDot(QtWidgets.QWidget):
    """The "new" marker: a small filled circle."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(NEW_DOT_SIZE + 4, NEW_DOT_SIZE + 4)
        self.setToolTip("New since you last opened notifications")

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(INFO_COLOR))
        painter.drawEllipse(QtCore.QRectF(2, 2, NEW_DOT_SIZE, NEW_DOT_SIZE))
