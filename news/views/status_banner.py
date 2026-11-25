# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The News section's status line as an inline banner: an editor on the
feed controller's ``status_text``."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Bool, Str, observe
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY

# Local imports.
from .card_style import CORNER_RADIUS, GRID

#: Pixel size of the status line's glyph.
STATUS_GLYPH_SIZE = 18

#: Size (px) of the short rule under a feed group header's title.
HEADER_RULE_SIZE = (4 * GRID, 3)

_ROLE = QtGui.QPalette.ColorRole
_ALIGN = QtCore.Qt.AlignmentFlag


def _glyph_label(glyph, pixel_size, color, parent):
    label = QtWidgets.QLabel(glyph, parent)
    font = QtGui.QFont(ICON_FONT_FAMILY)
    font.setPixelSize(pixel_size)
    label.setFont(font)
    label.setStyleSheet(f"QLabel {{ color: {color}; }}")

    return label


class _StatusBanner(QtWidgets.QFrame):
    """A rounded, tinted strip: the error colour on error, else muted."""

    def __init__(self):
        super().__init__()

        self.is_error = False

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        fill = QtGui.QColor(ERROR_COLOR) if self.is_error else palette.color(_ROLE.Mid)
        fill.setAlpha(28 if self.is_error else 60)
        edge = QtGui.QColor(fill)
        edge.setAlpha(110)

        painter.setPen(edge)
        painter.setBrush(fill)
        painter.drawRoundedRect(
            QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            CORNER_RADIUS,
            CORNER_RADIUS,
        )


class _StatusBannerEditor(Editor):
    """The status line as an inline banner with a glyph and a dismiss."""

    #: Whether the status reports a problem.
    is_error = Bool(False)

    #: The tinted strip, and its glyph and text labels.
    _banner = Any()
    _glyph = Any()
    _text = Any()

    def init(self, parent):
        self.control = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(self.control)
        outer.setContentsMargins(GRID, GRID, GRID, 0)

        self._banner = banner = _StatusBanner()
        outer.addWidget(banner)
        layout = QtWidgets.QHBoxLayout(banner)
        layout.setContentsMargins(GRID + GRID // 2, GRID, GRID, GRID)
        layout.setSpacing(GRID)

        self._glyph = _glyph_label("info", STATUS_GLYPH_SIZE, "", banner)
        layout.addWidget(self._glyph, 0, _ALIGN.AlignTop)

        self._text = QtWidgets.QLabel(banner)
        self._text.setWordWrap(True)
        self._text.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._text.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(self._text, 1)

        dismiss = QtWidgets.QToolButton(banner)
        dismiss.setText("✕")
        dismiss.setAutoRaise(True)
        dismiss.setToolTip("Dismiss")
        dismiss.clicked.connect(self._dismiss)
        layout.addWidget(dismiss, 0, _ALIGN.AlignTop)

        self.sync_value(self.factory.error_name, "is_error", "from")

    def update_editor(self):
        self._text.setText(self.str_value)

    @observe("is_error")
    def _show_error_state(self, event):
        if self.control is None:
            return

        muted = self.control.palette().color(_ROLE.PlaceholderText).name()
        color = ERROR_COLOR if self.is_error else muted

        self._banner.is_error = self.is_error
        self._glyph.setText("error" if self.is_error else "info")
        self._glyph.setStyleSheet(f"QLabel {{ color: {color}; }}")
        self._banner.update()

    def _dismiss(self):
        handler = self.ui.handler

        if hasattr(handler, "dismiss_status"):
            handler.dismiss_status()


class StatusBannerEditor(BasicEditorFactory):
    """Show a status Str as an inline banner; error-tinted on error."""

    klass = _StatusBannerEditor

    #: The extended name of the Bool saying the status is an error.
    error_name = Str()
