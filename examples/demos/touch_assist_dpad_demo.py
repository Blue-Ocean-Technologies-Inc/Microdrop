# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Standalone demo of the Touch Assist virtual D-pad.

A focusable panel stands in for the device view: it prints every key
press the D-pad posts to it (the chord the keyboard-shortcut service
would dispatch), plus the Shift/Ctrl/Alt key-ups that follow a latched
chord and end a Ctrl+Shift split session.

Run:
    pixi run python -m examples.demos.touch_assist_dpad_demo

Pass ``--smoke`` to quit after one second (a construction check).
"""

# Standard library imports.
import sys

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop package imports.
from microdrop_application.touch_assist.input_pads import VirtualDpad

Qt = QtCore.Qt

_MODIFIER_KEYS = (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt)


class KeyEchoPanel(QtWidgets.QLabel):
    """A focus target that prints the keys it receives."""

    def __init__(self):
        super().__init__("Tap the D-pad; keys print to stdout.")
        self.setAlignment(Qt.AlignCenter)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(360, 200)

    def keyPressEvent(self, event):
        chord = QtGui.QKeySequence(event.keyCombination()).toString()
        print(f"press   {chord}", flush=True)

    def keyReleaseEvent(self, event):
        if event.key() in _MODIFIER_KEYS:
            print(f"release {Qt.Key(event.key()).name}", flush=True)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    panel = KeyEchoPanel()
    panel.setWindowTitle("D-pad demo")
    panel.show()
    panel.activateWindow()
    panel.setFocus()

    dpad = VirtualDpad()
    dpad.show()

    if "--smoke" in sys.argv:
        QtCore.QTimer.singleShot(1000, app.quit)

    app.exec()


if __name__ == "__main__":
    main()
