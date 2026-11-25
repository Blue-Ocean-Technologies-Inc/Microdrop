# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Labels that fit their text to their room: ``ClampedLabel`` cuts wrapped
text to a number of lines, ``ElidedLabel`` one line with an ellipsis."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

_ELIDE = QtCore.Qt.TextElideMode.ElideRight

#: QTextLayout breaks lines only at the Unicode line separator.
LINE_SEPARATOR = " "

#: Narrowest width (px) text is laid out for, before the label is sized.
MIN_LAYOUT_WIDTH = 40


def wrapped_line_spans(text, font, width):
    """``(start, length)`` of each line ``text`` wraps to in ``width`` px."""
    layout = QtGui.QTextLayout(text.replace("\n", LINE_SEPARATOR), font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)

    spans = []
    layout.beginLayout()

    while True:
        line = layout.createLine()

        if not line.isValid():
            break

        line.setLineWidth(width)
        spans.append((line.textStart(), line.textLength()))

    layout.endLayout()

    return spans


class ClampedLabel(QtWidgets.QLabel):
    """Word-wrapped text cut to ``lines`` lines with an ellipsis; 0 lines
    shows it all. ``overflowed`` says whether anything was cut, and
    ``overflow_changed`` when that changes."""

    overflow_changed = QtCore.Signal(bool)

    def __init__(self, parent=None, lines=2):
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
        width = max(self.width(), MIN_LAYOUT_WIDTH)
        metrics = QtGui.QFontMetrics(self.font())
        spans = wrapped_line_spans(self._full_text, self.font(), width)

        overflowed = bool(self.lines) and len(spans) > self.lines
        kept = spans[: self.lines] if overflowed else spans
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


class ElidedLabel(QtWidgets.QLabel):
    """One line cut with an ellipsis when short of room. A detail label
    (right-aligned, the default) takes only spare room, so it is cut first;
    a ``title`` label asks for its whole width and is cut only when the
    detail has none left."""

    def __init__(self, text, parent=None, title=False):
        super().__init__(text, parent)

        horizontal = (
            QtCore.Qt.AlignmentFlag.AlignLeft
            if title
            else QtCore.Qt.AlignmentFlag.AlignRight
        )
        self._alignment = horizontal | QtCore.Qt.AlignmentFlag.AlignVCenter

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred
            if title
            else QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

    def minimumSizeHint(self):
        metrics = QtGui.QFontMetrics(self.font())

        return QtCore.QSize(metrics.horizontalAdvance("W…"), metrics.height())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        metrics = QtGui.QFontMetrics(self.font())
        text = metrics.elidedText(self.text(), _ELIDE, self.width())

        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), self._alignment, text)
