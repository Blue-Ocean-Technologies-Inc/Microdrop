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

# Standard library imports.
import importlib.util
from pathlib import Path

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from pyface.qt.QtSvg import QSvgRenderer
from pyface.tasks.api import DockPane
from traits.api import Callable

# Microdrop style imports.
from microdrop_style.colors import BLACK, GREY, WHITE

#: The chip the device viewer stand-in pictures: the 90-pin array the real
#: device viewer opens by default. Located, not imported: importing
#: ``device_viewer`` would bring the real viewer's models with it.
DEVICE_SVG_PATH = (
    Path(importlib.util.find_spec("device_viewer").submodule_search_locations[0])
    / "resources"
    / "devices"
    / "90_pin_array.svg"
)

#: Space (px) kept around the chip picture.
DEVICE_MARGIN = 24

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


class DevicePicture(QtWidgets.QWidget):
    """A device SVG, scaled to fit with its aspect kept and centred, its
    electrodes drawn in the theme's electrode grey on the viewer's canvas
    colour. Static: drawn again only on resize or a theme change."""

    def __init__(self, svg_path, parent=None):
        super().__init__(parent)

        self._renderer = QSvgRenderer(str(svg_path), self)

        #: The tinted picture, and the (size, dark) it was drawn for.
        self._picture = None
        self._picture_key = None

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        dark = self.palette().color(QtGui.QPalette.ColorRole.Window).lightness() < 128
        painter.fillRect(self.rect(), QtGui.QColor(BLACK if dark else WHITE))

        if not self._renderer.isValid():
            return

        target = self._fitted_rect()
        key = (target.size(), dark)

        if key != self._picture_key:
            self._picture = self._tinted_picture(target.size(), dark)
            self._picture_key = key

        painter.drawImage(target.topLeft(), self._picture)

    def _fitted_rect(self):
        """The largest rectangle of the SVG's aspect inside the margins,
        centred."""
        room = self.rect().adjusted(
            DEVICE_MARGIN, DEVICE_MARGIN, -DEVICE_MARGIN, -DEVICE_MARGIN
        )
        size = self._renderer.defaultSize().scaled(
            room.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio
        )
        rect = QtCore.QRect(QtCore.QPoint(), size)
        rect.moveCenter(room.center())

        return rect

    def _tinted_picture(self, size, dark):
        """The SVG at ``size``, its (black) electrodes recoloured."""
        image = QtGui.QImage(
            size.expandedTo(QtCore.QSize(1, 1)),
            QtGui.QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._renderer.render(painter)

        # Keep the drawn shapes, in the electrode colour.
        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
        )
        painter.fillRect(image.rect(), QtGui.QColor(GREY["dark" if dark else "light"]))
        painter.end()

        return image


def device_viewer(parent):
    """The device viewer stand-in: a strip over a picture of the chip."""
    widget = QtWidgets.QWidget(parent)
    layout = QtWidgets.QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    strip = QtWidgets.QLabel("  90-pin chip · Free mode", widget)
    strip.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(strip)
    layout.addWidget(DevicePicture(DEVICE_SVG_PATH, widget), 1)

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
