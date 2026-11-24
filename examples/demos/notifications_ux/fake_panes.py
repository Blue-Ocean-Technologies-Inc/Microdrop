# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Stand-in dock panes for the prototype: a device viewer, a protocol and a
DropBot status panel, with the real panes' ids so the MicroDrop task's
default layout places them where the real ones go. They only look the part.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from pyface.tasks.api import DockPane
from traits.api import Callable

# Microdrop style imports.
from microdrop_style.colors import GREY, PRIMARY_SHADE, SECONDARY_SHADE

#: The electrode array drawn by the device viewer stand-in.
GRID_COLUMNS = 16
GRID_ROWS = 7
ELECTRODE_GAP = 4

#: Milliseconds between the droplet's steps.
DROPLET_STEP_MS = 450

#: The droplet's route, as (column, row) electrodes.
DROPLET_ROUTE = [(column, 3) for column in range(2, 14)] + [(13, row) for row in (2, 1)]

#: The protocol stand-in's steps: (name, duration s, voltage V, frequency Hz,
#: electrodes, video).
PROTOCOL_STEPS = [
    ("Load sample", 2.0, 100, 10000, "R1 → 4", "on"),
    ("Merge with reagent", 1.5, 100, 10000, "4, 5, 6", ""),
    ("Mix (×6)", 6.0, 110, 10000, "6 ↔ 9", "on"),
    ("Incubate", 120.0, 0, 0, "—", ""),
    ("Split", 1.0, 120, 5000, "9 | 10", "on"),
    ("Move to detection", 3.0, 100, 10000, "10 → D1", ""),
    ("Read fluorescence", 4.0, 0, 0, "D1", "on"),
    ("Dispose", 2.5, 100, 10000, "D1 → W", ""),
]


class StandInPane(DockPane):
    """A dock pane showing whatever ``factory(parent)`` makes."""

    factory = Callable()

    def create_contents(self, parent):
        return self.factory(parent)


class _ElectrodeArray(QtWidgets.QWidget):
    """An electrode grid with reservoirs and a droplet stepping along a
    route, on the device viewer's canvas colours."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._step = 0

        timer = QtCore.QTimer(self)
        timer.timeout.connect(self._advance)
        timer.start(DROPLET_STEP_MS)

    def _advance(self):
        self._step = (self._step + 1) % len(DROPLET_ROUTE)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        dark = self.palette().color(QtGui.QPalette.ColorRole.Window).lightness() < 128
        painter.fillRect(
            self.rect(), QtGui.QColor(GREY["darkest"] if dark else "#FAFAFA")
        )

        size = min(
            (self.width() - 80) / (GRID_COLUMNS + 2), (self.height() - 60) / GRID_ROWS
        )
        size = max(size, 8)
        width = size * (GRID_COLUMNS + 2)
        left = (self.width() - width) / 2 + size
        top = (self.height() - size * GRID_ROWS) / 2
        electrode = QtGui.QColor(GREY["dark"] if dark else GREY["light"])
        actuated = QtGui.QColor(PRIMARY_SHADE[400] if dark else PRIMARY_SHADE[300])
        column, row = DROPLET_ROUTE[self._step]

        painter.setPen(
            QtGui.QPen(QtGui.QColor(GREY["darker"] if dark else GREY["lighter"]), 1)
        )

        for x in range(GRID_COLUMNS):
            for y in range(GRID_ROWS):
                on = (x, y) == (column, row) or (x, y) == (column + 1, row)
                painter.setBrush(actuated if on else electrode)
                cell = QtCore.QRectF(
                    left + x * size,
                    top + y * size,
                    size - ELECTRODE_GAP,
                    size - ELECTRODE_GAP,
                )
                painter.drawRoundedRect(cell, 3, 3)

        # Reservoirs either side.
        painter.setBrush(electrode)

        for y in (1, 4):
            painter.drawRoundedRect(
                QtCore.QRectF(
                    left - size * 1.6,
                    top + y * size,
                    size * 1.3,
                    size * 2 - ELECTRODE_GAP,
                ),
                6,
                6,
            )
            painter.drawRoundedRect(
                QtCore.QRectF(
                    left + GRID_COLUMNS * size + size * 0.3,
                    top + y * size,
                    size * 1.3,
                    size * 2 - ELECTRODE_GAP,
                ),
                6,
                6,
            )

        # The droplet.
        droplet = QtCore.QRectF(
            left + column * size - size * 0.15,
            top + row * size - size * 0.15,
            size * 1.2,
            size * 1.2,
        )
        color = QtGui.QColor(SECONDARY_SHADE[300])
        color.setAlpha(190)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(droplet)


def device_viewer(parent):
    """The device viewer stand-in: a toolbar strip over the array."""
    widget = QtWidgets.QWidget(parent)
    layout = QtWidgets.QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    strip = QtWidgets.QLabel("  90-pin chip · Free mode · 2 electrodes on", widget)
    strip.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(strip)
    layout.addWidget(_ElectrodeArray(widget), 1)

    return widget


def protocol(parent):
    """The protocol stand-in: a step table."""
    tree = QtWidgets.QTreeWidget(parent)
    tree.setHeaderLabels(
        ["Step", "Duration (s)", "Voltage (V)", "Frequency (Hz)", "Electrodes", "Video"]
    )
    tree.setRootIsDecorated(False)
    tree.setAlternatingRowColors(True)

    for number, (name, duration, voltage, frequency, electrodes, video) in enumerate(
        PROTOCOL_STEPS, 1
    ):
        QtWidgets.QTreeWidgetItem(
            tree,
            [
                f"{number}. {name}",
                f"{duration:g}",
                str(voltage or "—"),
                str(frequency or "—"),
                electrodes,
                video,
            ],
        )

    for column in range(tree.columnCount()):
        tree.resizeColumnToContents(column)

    tree.setCurrentItem(tree.topLevelItem(2))

    return tree


def dropbot_status(parent):
    """The DropBot status stand-in: a read-out form."""
    widget = QtWidgets.QWidget(parent)
    form = QtWidgets.QFormLayout(widget)
    form.setContentsMargins(12, 10, 12, 10)
    form.setHorizontalSpacing(18)

    rows = [
        ("Connection", "● Not connected (demo)"),
        ("Chip", "90-pin (inserted)"),
        ("Voltage", "100 V"),
        ("Frequency", "10 000 Hz"),
        ("Capacitance", "1.82 pF"),
        ("Temperature", "24.6 °C"),
    ]

    for label, value in rows:
        form.addRow(f"{label}:", QtWidgets.QLabel(value, widget))

    # Compact, as the real panel: the protocol below takes the room.
    widget.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Maximum
    )

    return widget
