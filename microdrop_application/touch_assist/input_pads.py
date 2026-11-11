# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The virtual numpad, keyboard and D-pad: frameless, always-on-top pads
whose keys are posted to whatever widget currently has focus — the
field the user last tapped. The pads never take focus themselves
(``WindowDoesNotAcceptFocus``), so tapping a key cannot steal the
caret from its target. No per-widget wiring: synthesized QKeyEvents
work with TraitsUI editors, plugin panes and dialogs alike."""

# Third-party imports.
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Microdrop style imports.
from microdrop_style.colors import BLACK, GREY, PRIMARY_COLOR, WHITE

# Local imports.
from .consts import (
    PAD_KEY_REPEAT_DELAY_MS,
    PAD_KEY_REPEAT_INTERVAL_MS,
    PAD_KEY_SIZE_PX,
    PAD_KEY_SPACING_PX,
)

#: (label, Qt key, text) rows of the numpad. Text is what lands in
#: the field; the key code is what spinboxes and shortcuts read.
_NUMPAD_ROWS = (
    (
        ("7", Qt.Key_7, "7"),
        ("8", Qt.Key_8, "8"),
        ("9", Qt.Key_9, "9"),
        ("⌫", Qt.Key_Backspace, ""),
    ),
    (
        ("4", Qt.Key_4, "4"),
        ("5", Qt.Key_5, "5"),
        ("6", Qt.Key_6, "6"),
        ("▲", Qt.Key_Up, ""),
    ),
    (
        ("1", Qt.Key_1, "1"),
        ("2", Qt.Key_2, "2"),
        ("3", Qt.Key_3, "3"),
        ("▼", Qt.Key_Down, ""),
    ),
    (
        ("-", Qt.Key_Minus, "-"),
        ("0", Qt.Key_0, "0"),
        (".", Qt.Key_Period, "."),
        ("⏎", Qt.Key_Return, "\r"),
    ),
)

#: Keyboard letter rows; digits get their own row above.
_KEYBOARD_LETTER_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")

#: What the digit row types while Shift is latched.
_SHIFTED_DIGITS = str.maketrans("1234567890", "!@#$%^&*()")

#: (label, Qt key, row, column) of the D-pad's arrow cross.
_DPAD_ARROWS = (
    ("▲", Qt.Key_Up, 0, 1),
    ("◀", Qt.Key_Left, 1, 0),
    ("▶", Qt.Key_Right, 1, 2),
    ("▼", Qt.Key_Down, 2, 1),
)

#: The key a latched modifier flag stands for, so the D-pad can post
#: its key-up when the latch is tapped off.
_MODIFIER_KEYS = {
    Qt.KeyboardModifier.ShiftModifier: Qt.Key_Shift,
    Qt.KeyboardModifier.ControlModifier: Qt.Key_Control,
    Qt.KeyboardModifier.AltModifier: Qt.Key_Alt,
}

_PAD_STYLE = f"""
    QWidget#touch_pad {{
        background: {GREY["dark"]};
        border: 1px solid {PRIMARY_COLOR};
        border-radius: 6px;
    }}
    QLabel {{ color: {WHITE}; font-weight: bold; }}
    QPushButton {{
        background: {WHITE};
        color: {BLACK};
        border: 1px solid #999;
        border-radius: 4px;
        font-size: 15px;
    }}
    QPushButton:pressed, QPushButton:checked {{
        background: {PRIMARY_COLOR};
        color: {WHITE};
    }}
"""


def main_window_parent():
    """Parent for the floating pads: the application's main window, so
    the pads are its transients. A parentless stay-on-top window stacks
    BELOW a focused fullscreen window (the rig's kiosk mode) on X11;
    a transient stacks above it."""
    app = QApplication.instance()
    return app.activeWindow() if app is not None else None


class FloatingPad(QWidget):
    """A frameless, always-on-top, finger-draggable pad with a title
    strip and close button. Subclasses fill ``self.body``, and may
    add latching modifiers (``_add_modifier``) that join the next
    key's chord — one-shot unless the subclass overrides
    ``_after_chord``."""

    #: Set by the manager: called when the user closes the pad from
    #: its own ✕, so the menu checkbox can follow.
    closed_by_user = None

    def __init__(self, title):
        super().__init__(
            main_window_parent(),
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("touch_pad")
        self.setStyleSheet(_PAD_STYLE)
        self._drag_offset = None
        self._modifier_buttons = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 6)
        handle = QHBoxLayout()
        handle.addWidget(QLabel(title))
        handle.addStretch(1)
        close = QPushButton("✕")
        close.setFixedSize(28, 28)
        close.setFocusPolicy(Qt.NoFocus)
        close.clicked.connect(self._close_from_button)
        handle.addWidget(close)
        outer.addLayout(handle)
        self.body = QGridLayout()
        self.body.setSpacing(PAD_KEY_SPACING_PX)
        outer.addLayout(self.body)

    def _close_from_button(self):
        self.hide()
        if self.closed_by_user is not None:
            self.closed_by_user()

    # -- finger drag anywhere on the pad's chrome moves it ----------
    def mousePressEvent(self, event):
        self._drag_offset = (
            event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        )

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def showEvent(self, event):
        super().showEvent(event)
        if (
            not event.spontaneous()
            and self._drag_offset is None
            and not self.property("placed")
        ):
            # First show: bottom-right of the screen, out of the way.
            self.setProperty("placed", True)
            area = self.screen().availableGeometry()
            self.adjustSize()
            self.move(
                area.right() - self.width() - 40, area.bottom() - self.height() - 60
            )

    # -- key delivery ------------------------------------------------
    def add_key(
        self,
        label,
        key,
        text,
        row,
        column,
        *,
        width=1,
        modifiers=Qt.KeyboardModifier.NoModifier,
        span_px=None,
        repeat=False,
    ):
        button = QPushButton(label)
        button.setFocusPolicy(Qt.NoFocus)
        button.setFixedHeight(PAD_KEY_SIZE_PX)
        button.setMinimumWidth(span_px or PAD_KEY_SIZE_PX)
        if repeat:  # a held key keeps firing
            button.setAutoRepeat(True)
            button.setAutoRepeatDelay(PAD_KEY_REPEAT_DELAY_MS)
            button.setAutoRepeatInterval(PAD_KEY_REPEAT_INTERVAL_MS)
        button.clicked.connect(lambda *_: self.send_key(key, text, modifiers))
        self.body.addWidget(button, row, column, 1, width)
        return button

    def _add_modifier(self, label, flag, row, column):
        """A latching key: checked arms the flag for the next real
        key, which consumes it (see send_key)."""
        button = self.add_key(label, Qt.Key_unknown, "", row, column)
        button.clicked.disconnect()
        button.setCheckable(True)
        button.clicked.connect(self._on_modifiers_changed)
        self._modifier_buttons[flag] = button

        return button

    def _latched_modifiers(self):
        latched = Qt.KeyboardModifier.NoModifier

        for flag, button in self._modifier_buttons.items():
            if button.isChecked():
                latched |= flag

        return latched

    def _on_modifiers_changed(self, *_):
        """Hook: a latch was tapped or released. No-op here."""

    def send_key(self, key, text, modifiers=None):
        """Every key passes through here: latched modifiers join the
        chord (a Ctrl/Alt shortcut types no text), then
        ``_after_chord`` runs."""
        latched = self._latched_modifiers()
        combined = (
            modifiers if modifiers is not None else Qt.KeyboardModifier.NoModifier
        ) | latched

        if combined & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
        ):
            text = ""  # a chord types nothing

        self.post_key(key, text, combined)

        if latched:
            self._after_chord()

    def _after_chord(self):
        """One-shot, like a touch keyboard: a chord consumes the
        latches."""
        self._release_latches()

    def _release_latches(self):
        for button in self._modifier_buttons.values():
            button.setChecked(False)

        self._on_modifiers_changed()

    def post_key(self, key, text, modifiers):
        """Post press+release to the focused widget; no focus, no-op."""
        target = QApplication.focusWidget()

        if target is None:
            return

        QCoreApplication.postEvent(
            target, QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)
        )
        QCoreApplication.postEvent(
            target, QKeyEvent(QEvent.Type.KeyRelease, key, modifiers, text)
        )


class VirtualNumpad(FloatingPad):
    """Digits, sign, decimal point, Backspace, spinbox stepping
    (▲/▼) and Enter."""

    def __init__(self):
        super().__init__("Numpad")
        for row, keys in enumerate(_NUMPAD_ROWS):
            for column, (label, key, text) in enumerate(keys):
                self.add_key(
                    label,
                    key,
                    text,
                    row,
                    column,
                    repeat=key in (Qt.Key_Up, Qt.Key_Down),
                )


class VirtualKeyboard(FloatingPad):
    """Compact QWERTY with a digit row and one-shot latching
    modifiers: Shift, Ctrl and Alt each arm the NEXT key (uppercase
    or symbol for Shift, a shortcut chord like Ctrl+A for the
    others), then release — the usual touch-keyboard behaviour."""

    def __init__(self):
        super().__init__("Keyboard")
        self._letter_buttons = []
        for column, digit in enumerate("1234567890"):
            self.add_key(digit, getattr(Qt, f"Key_{digit}"), digit, 0, column)
        for row, letters in enumerate(_KEYBOARD_LETTER_ROWS, start=1):
            offset = row - 1  # stagger like a real keyboard
            for column, letter in enumerate(letters):
                self._letter_buttons.append(
                    self.add_key(
                        letter,
                        getattr(Qt, f"Key_{letter.upper()}"),
                        letter,
                        row,
                        column + offset,
                    )
                )
        self._shift = self._add_modifier("⇧", Qt.KeyboardModifier.ShiftModifier, 3, 9)
        self.add_key("⌫", Qt.Key_Backspace, "", 1, 10)
        self.add_key("⏎", Qt.Key_Return, "\r", 2, 10)
        self._add_modifier("ctrl", Qt.KeyboardModifier.ControlModifier, 4, 0)
        self._add_modifier("alt", Qt.KeyboardModifier.AltModifier, 4, 1)
        self.add_key("space", Qt.Key_Space, " ", 4, 2, width=5)
        self.add_key(".", Qt.Key_Period, ".", 4, 7)
        self.add_key(
            "_",
            Qt.Key_Underscore,
            "_",
            4,
            8,
            modifiers=Qt.KeyboardModifier.ShiftModifier,
        )

    def send_key(self, key, text, modifiers=None):
        """Latched Shift types uppercase/symbols; the base adds the
        chord (and blanks the text for a Ctrl/Alt shortcut)."""
        if self._shift.isChecked() and text:
            text = text.upper().translate(_SHIFTED_DIGITS)
        super().send_key(key, text, modifiers)

    def _on_modifiers_changed(self, *_):
        """Letter labels follow the Shift latch."""
        shifted = self._shift.isChecked()
        for button in self._letter_buttons:
            text = button.text()
            button.setText(text.upper() if shifted else text.lower())


class VirtualDpad(FloatingPad):
    """Arrow keys for the device viewer's shortcuts: a held arrow
    keeps stepping, and the sticky Shift/Ctrl/Alt latches (any
    combination) turn every tap into grow, shrink, split step or
    route drawing until tapped off. Esc leaves route drawing;
    Backspace erases its tail."""

    def __init__(self):
        super().__init__("D-pad")

        #: Latches whose key-up has not been posted yet.
        self._held_modifiers = Qt.KeyboardModifier.NoModifier

        for label, key, row, column in _DPAD_ARROWS:
            button = self.add_key(label, key, "", row, column, repeat=True)
            button.setFixedSize(PAD_KEY_SIZE_PX, PAD_KEY_SIZE_PX)
            self.body.setAlignment(button, Qt.AlignCenter)

        self._add_modifier("⇧", Qt.KeyboardModifier.ShiftModifier, 3, 0)
        self._add_modifier("ctrl", Qt.KeyboardModifier.ControlModifier, 3, 1)
        self._add_modifier("alt", Qt.KeyboardModifier.AltModifier, 3, 2)

        self.add_key("Esc", Qt.Key_Escape, "", 4, 0)
        self.add_key("⌫", Qt.Key_Backspace, "", 4, 2)

    def _after_chord(self):
        """Sticky: latches stay on across taps and auto-repeat ticks,
        like physical modifiers held down."""

    def _on_modifiers_changed(self, *_):
        """Post the key-up of each latch just tapped off: the device
        view ends a Ctrl+Shift split session on a Ctrl or Shift
        release, as it does when physical keys are let go."""
        latched = self._latched_modifiers()

        for flag, modifier_key in _MODIFIER_KEYS.items():
            if self._held_modifiers & flag and not latched & flag:
                self.post_release(modifier_key, flag)

        self._held_modifiers = latched

    def hideEvent(self, event):
        # Hidden or closed with latches on: let them go, so no split
        # session is left waiting for a key-up that never comes.
        super().hideEvent(event)
        self._release_latches()

    def post_release(self, key, flag):
        """Post a modifier key-up to the focused widget; no focus,
        no-op. Built with its own flag, as a physical key-up is:
        QKeyEvent.modifiers() toggles it off for a modifier key."""
        target = QApplication.focusWidget()

        if target is None:
            return

        QCoreApplication.postEvent(
            target, QKeyEvent(QEvent.Type.KeyRelease, key, flag, "")
        )
