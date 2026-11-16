# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The number pad: a calculator-style popup that edits one number.

It is a ``Qt.Popup``: it takes the keyboard and mouse while open and closes
on a tap outside it, yet never becomes the active window, so an item view's
inline editor keeps focus underneath and is not committed and closed by the
delegate's focus-out handling. It knows nothing of spin boxes: it emits
``accepted`` with the value or ``cancelled``, and the caller applies it.
"""

# Standard library imports.
from html import escape

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from pyface.qt.QtCore import QPoint, QRect, QSize, Qt

# Microdrop style imports.
from microdrop_style.colors import PRIMARY_SHADE, WHITE
from microdrop_style.helpers import is_dark_mode
from microdrop_style.touch_style import (
    TOUCH_TARGET_PX,
    get_touch_colors,
    touch_glyph_path,
)

# Local imports.
from .consts import (
    NUMBER_PAD_CLOSE_ICON_PX,
    NUMBER_PAD_DISPLAY_POINT_SIZE,
    NUMBER_PAD_DISPLAY_PX,
    NUMBER_PAD_FIELD_GAP_PX,
    NUMBER_PAD_KEY_POINT_SIZE,
    NUMBER_PAD_KEY_PX,
    NUMBER_PAD_MARGIN_PX,
    NUMBER_PAD_SPACING_PX,
)

#: Key label -> (row, column) on the pad's grid; OK spans the last two rows.
_DIGIT_KEYS = {
    "7": (0, 0),
    "8": (0, 1),
    "9": (0, 2),
    "4": (1, 0),
    "5": (1, 1),
    "6": (1, 2),
    "1": (2, 0),
    "2": (2, 1),
    "3": (2, 2),
    "0": (3, 1),
}

_BACKSPACE_LABEL = "⌫"
_CLEAR_LABEL = "C"
_SIGN_LABEL = "±"
_POINT_LABEL = "."
_OK_LABEL = "OK"


def place_beside(size, field, area, gap):
    """Return the top-left for a popup of ``size`` next to the ``field`` rect.

    Below the field is tried first, then right of it, above and left, each
    slid along the field's edge to stay inside ``area``. When none fits
    without covering the field, the popup goes below, pushed inside ``area``.
    """
    width, height = size.width(), size.height()

    def clamp_x(x):
        return min(max(x, area.left()), area.right() + 1 - width)

    def clamp_y(y):
        return min(max(y, area.top()), area.bottom() + 1 - height)

    candidates = (
        QPoint(clamp_x(field.left()), field.bottom() + 1 + gap),
        QPoint(field.right() + 1 + gap, clamp_y(field.top())),
        QPoint(clamp_x(field.left()), field.top() - gap - height),
        QPoint(field.left() - gap - width, clamp_y(field.top())),
    )

    for top_left in candidates:
        popup = QRect(top_left, size)

        if area.contains(popup) and not popup.intersects(field):
            return top_left

    return QPoint(clamp_x(field.left()), clamp_y(field.bottom() + 1 + gap))


class NumberPad(QtWidgets.QFrame):
    """Keypad popup over a NumberEntry; instantiable on its own."""

    #: The value the user confirmed with OK or Enter.
    accepted = QtCore.Signal(float)

    #: Closed without a value: ✕, Esc, or a tap outside the pad.
    cancelled = QtCore.Signal()

    def __init__(self, entry, title="", prefix="", suffix="", parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # The tap that dismisses the pad must not also press whatever lies
        # under it.
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        self.setObjectName("number_pad")

        self.entry = entry
        self._prefix = prefix
        self._suffix = suffix
        self._resolved = False
        self._colors = get_touch_colors(
            QtWidgets.QApplication.palette(), is_dark_mode()
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(*[NUMBER_PAD_MARGIN_PX] * 4)
        layout.setSpacing(NUMBER_PAD_SPACING_PX)

        layout.addLayout(self._build_header(title))

        self._display = QtWidgets.QLabel()
        self._display.setObjectName("number_pad_display")
        self._display.setTextFormat(Qt.TextFormat.RichText)
        self._display.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._display.setMinimumHeight(NUMBER_PAD_DISPLAY_PX)
        self._set_point_size(self._display, NUMBER_PAD_DISPLAY_POINT_SIZE)
        layout.addWidget(self._display)

        layout.addLayout(self._build_keys())

        self.setStyleSheet(self._style_sheet())
        self._render()

    def popup_beside(self, field_rect):
        """Show the pad next to ``field_rect`` (global), on the field's screen."""
        screen = QtGui.QGuiApplication.screenAt(field_rect.center())

        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()

        self.adjustSize()
        self.move(
            place_beside(
                self.size(),
                field_rect,
                screen.availableGeometry(),
                NUMBER_PAD_FIELD_GAP_PX,
            )
        )
        self.show()

    #### Building #############################################################

    def _build_header(self, title):
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(NUMBER_PAD_SPACING_PX)

        # Parented up front: showing a parentless label makes it a window.
        self._title = QtWidgets.QLabel(title, self)
        self._title.setObjectName("number_pad_title")
        self._title.setVisible(bool(title))
        header.addWidget(self._title)

        header.addStretch(1)

        self._range = QtWidgets.QLabel()
        self._range.setObjectName("number_pad_range")
        header.addWidget(self._range)

        close_button = QtWidgets.QPushButton()
        close_button.setObjectName("number_pad_close")
        close_button.setIcon(
            QtGui.QIcon(touch_glyph_path("close", self._colors["window_text"]))
        )
        close_button.setIconSize(
            QSize(NUMBER_PAD_CLOSE_ICON_PX, NUMBER_PAD_CLOSE_ICON_PX)
        )
        close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_button.setFixedSize(TOUCH_TARGET_PX, TOUCH_TARGET_PX)
        close_button.clicked.connect(self.cancel)
        header.addWidget(close_button)

        return header

    def _build_keys(self):
        keys = QtWidgets.QGridLayout()
        keys.setSpacing(NUMBER_PAD_SPACING_PX)

        for digit, (row, column) in _DIGIT_KEYS.items():
            self._add_key(
                keys, digit, row, column, lambda d=digit: self.entry.type_digit(d)
            )

        self._add_key(keys, _BACKSPACE_LABEL, 0, 3, self.entry.backspace, "function")
        self._add_key(keys, _CLEAR_LABEL, 1, 3, self.entry.clear, "function")
        self._sign_key = self._add_key(keys, _SIGN_LABEL, 3, 0, self.entry.toggle_sign)
        self._point_key = self._add_key(keys, _POINT_LABEL, 3, 2, self.entry.type_point)

        self._ok_key = QtWidgets.QPushButton(_OK_LABEL)
        self._ok_key.setObjectName("number_pad_ok")
        self._style_key(self._ok_key)
        self._ok_key.clicked.connect(self.accept)
        keys.addWidget(self._ok_key, 2, 3, 2, 1)

        return keys

    def _add_key(self, keys, label, row, column, action, role="digit"):
        key = QtWidgets.QPushButton(label)
        key.setProperty("role", role)
        self._style_key(key)
        key.clicked.connect(lambda: self._press(action))
        keys.addWidget(key, row, column)

        return key

    def _style_key(self, key):
        key.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        key.setMinimumSize(NUMBER_PAD_KEY_PX, NUMBER_PAD_KEY_PX)
        key.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._set_point_size(key, NUMBER_PAD_KEY_POINT_SIZE)

    @staticmethod
    def _set_point_size(widget, point_size):
        font = widget.font()
        font.setPointSize(point_size)
        widget.setFont(font)

    def _style_sheet(self):
        colors = self._colors

        return f"""
QFrame#number_pad {{
    background-color: {colors["window"]};
    border: 1px solid {colors["frame"]};
}}
QLabel {{
    color: {colors["window_text"]};
    background: transparent;
}}
QLabel#number_pad_title {{
    font-weight: bold;
}}
QPushButton {{
    padding: 0px;
    border: 1px solid {colors["frame"]};
    border-radius: 8px;
    background-color: {colors["button"]};
    color: {colors["text"]};
}}
QPushButton[role="function"] {{
    background-color: {colors["window"]};
}}
QPushButton:pressed {{
    background-color: {colors["pressed"]};
    border-color: {colors["accent"]};
}}
QPushButton:disabled {{
    color: {colors["disabled_text"]};
    background-color: {colors["window"]};
}}
QPushButton#number_pad_close {{
    border: none;
    background: transparent;
}}
QPushButton#number_pad_ok {{
    border: none;
    background-color: {PRIMARY_SHADE[600]};
    color: {WHITE};
    font-weight: bold;
}}
QPushButton#number_pad_ok:pressed {{
    background-color: {PRIMARY_SHADE[800]};
}}
QPushButton#number_pad_ok:disabled {{
    border: 1px solid {colors["frame"]};
    background-color: {colors["window"]};
    color: {colors["disabled_text"]};
}}
"""

    #### Input ################################################################

    def _press(self, action):
        action()
        self._render()

    def keyPressEvent(self, event):
        """Physical keys: digits, point, minus, Backspace, Delete, Enter, Esc."""
        key = event.key()
        text = event.text()
        actions = {
            Qt.Key.Key_Backspace: self.entry.backspace,
            Qt.Key.Key_Delete: self.entry.clear,
            Qt.Key.Key_Period: self.entry.type_point,
            Qt.Key.Key_Comma: self.entry.type_point,
            Qt.Key.Key_Minus: self.entry.toggle_sign,
        }

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()

        elif key == Qt.Key.Key_Escape:
            self.cancel()

        elif len(text) == 1 and text in _DIGIT_KEYS:
            self._press(lambda: self.entry.type_digit(text))

        elif key in actions:
            self._press(actions[key])

        else:
            super().keyPressEvent(event)

    def accept(self):
        """Close and emit the value, when it fits the range."""

        if not self.entry.in_range:
            return

        self._resolved = True
        self.close()
        self.accepted.emit(self.entry.value)

    def cancel(self):
        """Close without a value."""
        self._resolved = True
        self.close()
        self.cancelled.emit()

    def hideEvent(self, event):
        """A tap outside closes the popup without a decision: a cancel."""
        super().hideEvent(event)

        if not self._resolved:
            self._resolved = True
            self.cancelled.emit()

    #### Rendering ############################################################

    def _render(self):
        entry = self.entry
        colors = self._colors
        text = escape(entry.text)

        if entry.replace_pending and text:
            text = (
                f'<span style="background-color: {colors["highlight"]}; '
                f'color: {colors["highlighted_text"]};">&nbsp;{text}&nbsp;</span>'
            )

        affix_style = f'style="color: {colors["disabled_text"]};"'
        prefix = f"<span {affix_style}>{escape(self._prefix)}</span>"
        suffix = f"<span {affix_style}>{escape(self._suffix)}</span>"
        self._display.setText(f"{prefix}{text}{suffix}&nbsp;")

        border = colors["error"] if entry.out_of_range else colors["frame"]
        background = colors["error_tint"] if entry.out_of_range else colors["base"]
        self._display.setStyleSheet(
            f"background-color: {background}; color: {colors['text']}; "
            f"border: 2px solid {border}; border-radius: 8px;"
        )

        range_color = colors["error"] if entry.out_of_range else colors["window_text"]
        self._range.setText(entry.range_text(self._prefix, self._suffix))
        self._range.setStyleSheet(f"color: {range_color};")

        self._ok_key.setEnabled(entry.in_range)
        self._point_key.setEnabled(entry.allows_point)
        self._sign_key.setEnabled(entry.allows_negative)
