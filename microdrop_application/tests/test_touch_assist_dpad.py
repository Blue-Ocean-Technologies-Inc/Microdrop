# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The virtual D-pad's sticky latches: chords while on, key-ups when off."""

# Standard library imports.
from types import SimpleNamespace

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Microdrop package imports.
from microdrop_application.touch_assist import input_pads
from microdrop_application.touch_assist.input_pads import VirtualDpad

Qt = QtCore.Qt
KeyPress = QtCore.QEvent.Type.KeyPress
KeyRelease = QtCore.QEvent.Type.KeyRelease
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


class KeyRecorder(QtWidgets.QWidget):
    """Stands in for the focused device view."""

    def __init__(self):
        super().__init__()
        self.events = []

    def event(self, event):
        if event.type() in (KeyPress, KeyRelease):
            self.events.append((event.type(), event.key(), event.modifiers()))

        return super().event(event)

    def take(self):
        QtCore.QCoreApplication.sendPostedEvents(self)
        events, self.events = self.events, []

        return events


def _tap(pad, label):
    next(
        button
        for button in pad.findChildren(QtWidgets.QPushButton)
        if button.text() == label
    ).click()


def _right(modifiers):
    return [
        (KeyPress, Qt.Key.Key_Right, modifiers),
        (KeyRelease, Qt.Key.Key_Right, modifiers),
    ]


def test_sticky_latches_hold_the_chord_until_tapped_off(qapp, monkeypatch):
    dpad = VirtualDpad()
    target = KeyRecorder()

    # Real focus is unreliable offscreen; the pad only asks for the target.
    monkeypatch.setattr(
        input_pads, "QApplication", SimpleNamespace(focusWidget=lambda: target)
    )

    _tap(dpad, "ctrl")
    _tap(dpad, "⇧")
    _tap(dpad, "▶")
    _tap(dpad, "▶")

    assert target.take() == _right(CTRL | SHIFT) * 2

    _tap(dpad, "⇧")

    assert target.take() == [
        (KeyRelease, Qt.Key.Key_Shift, Qt.KeyboardModifier.NoModifier)
    ]

    _tap(dpad, "▶")

    assert target.take() == _right(CTRL)
