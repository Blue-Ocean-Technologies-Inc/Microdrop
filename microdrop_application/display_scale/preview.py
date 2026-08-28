# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Display Scale dialog's preview: a frame standing in for the
physical screen, with a screenshot of the running app drawn inside it
at the scale under the slider — a static mock of what a relaunch would
produce, since Qt cannot rescale the live interface (see startup.py).

A custom Qt widget because TraitsUI has no editor that paints one
image inside another at a ratio; raw Qt goes through pyface.qt per
the repo convention.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Property
from traitsui.basic_editor_factory import BasicEditorFactory
from traitsui.qt.editor import Editor as QtEditor

# Microdrop style imports.
from microdrop_style.helpers import is_dark_mode

#: The preview frame's height; its width follows the screen's aspect.
PREVIEW_HEIGHT_PX = 190

#: Fallback screen when there is none to ask (offscreen tests) — the
#: portable rig's panel.
FALLBACK_SCREEN_SIZE = QtCore.QSize(1280, 800)


class _ScalePreview(QtWidgets.QWidget):
    """The paintable frame: screen bezel, hatched free space, and the
    app screenshot at the chosen ratio, anchored top-left and clipped
    when it overflows."""

    def __init__(self, screenshot, screen_physical_size, parent=None):
        super().__init__(parent)
        self._screenshot = screenshot
        self._screen_size = screen_physical_size
        self._ratio = 1.0

        aspect = screen_physical_size.width() / screen_physical_size.height()
        self.setFixedSize(round(PREVIEW_HEIGHT_PX * aspect), PREVIEW_HEIGHT_PX)

    def set_ratio(self, ratio):
        self._ratio = ratio
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        dark = is_dark_mode()

        # The physical screen, drawn edge to edge with a bezel border.
        screen_rect = self.rect().adjusted(1, 1, -2, -2)

        # Space the shrunken app no longer covers: hatched, so it reads
        # as "room freed up" rather than as part of the interface.
        hatch = QtGui.QBrush(
            QtGui.QColor("#3a3a3a" if dark else "#d9d9d9"),
            QtCore.Qt.BrushStyle.BDiagPattern,
        )
        painter.fillRect(screen_rect, QtGui.QColor("#1e1e1e" if dark else "#f5f5f5"))
        painter.fillRect(screen_rect, hatch)

        # The app: its current physical footprint mapped into the frame,
        # then scaled by chosen/active — exactly what a relaunch does.
        frame_scale = screen_rect.width() / self._screen_size.width()
        target = QtCore.QRectF(
            screen_rect.x(),
            screen_rect.y(),
            self._screenshot.width() * frame_scale * self._ratio,
            self._screenshot.height() * frame_scale * self._ratio,
        )
        painter.save()
        painter.setClipRect(screen_rect)
        painter.drawPixmap(
            target, self._screenshot, QtCore.QRectF(self._screenshot.rect())
        )
        painter.restore()

        # Outline the app so the freed space beyond it stays legible.
        painter.setPen(QtGui.QPen(QtGui.QColor("#888888"), 1))
        painter.drawRect(target.intersected(QtCore.QRectF(screen_rect)))

        # The bezel, drawn last so nothing paints over it.
        painter.setPen(QtGui.QPen(QtGui.QColor("#000000" if dark else "#555555"), 2))
        painter.drawRect(screen_rect)


class _ScalePreviewEditor(QtEditor):
    """Binds the preview to ``scale_percent``: grabs the app window once
    at dialog build, repaints at each slider move."""

    def init(self, parent):
        screen_size = self._screen_physical_size()
        screenshot = self._grab_app_window() or _placeholder_screenshot(screen_size)
        self.control = _ScalePreview(screenshot, screen_size)

    def update_editor(self):
        active = self.object.active_scale_percent or 100
        self.control.set_ratio(self.value / active)

    def _grab_app_window(self):
        """Screenshot the largest visible window that is not this dialog."""
        own_window = self.control.window() if self.control else None
        best = None
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if not widget.isVisible() or widget is own_window:
                continue
            area = widget.width() * widget.height()
            if isinstance(widget, QtWidgets.QMainWindow):
                # The main window is what the user means by "the app",
                # even with a large floating tool on screen.
                area *= 1000
            if best is None or area > best[0]:
                best = (area, widget)
        return best[1].grab() if best else None

    def _screen_physical_size(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return FALLBACK_SCREEN_SIZE
        return screen.geometry().size() * screen.devicePixelRatio()


class ScalePreviewEditor(BasicEditorFactory):
    """The factory class passed into the Item's editor parameter."""

    klass = Property

    def _get_klass(self):
        return _ScalePreviewEditor


def _placeholder_screenshot(screen_size):
    """A fake maximized app — menu strip, device pane, side panes — so
    the view stays prototypable standalone, with nothing real to grab."""
    pixmap = QtGui.QPixmap(screen_size)
    painter = QtGui.QPainter(pixmap)
    w, h = screen_size.width(), screen_size.height()

    painter.fillRect(pixmap.rect(), QtGui.QColor("#eceff1"))
    painter.fillRect(0, 0, w, round(h * 0.05), QtGui.QColor("#cfd8dc"))

    device_pane = QtCore.QRect(
        round(w * 0.01), round(h * 0.07), round(w * 0.60), round(h * 0.90)
    )
    painter.fillRect(device_pane, QtGui.QColor("#ffffff"))
    painter.setPen(QtGui.QColor("#90a4ae"))
    for row in range(4):
        for col in range(6):
            painter.fillRect(
                device_pane.x() + round(device_pane.width() * (0.08 + col * 0.15)),
                device_pane.y() + round(device_pane.height() * (0.15 + row * 0.20)),
                round(device_pane.width() * 0.11),
                round(device_pane.height() * 0.13),
                QtGui.QColor("#b0bec5"),
            )

    for top, bottom in ((0.07, 0.42), (0.46, 0.97)):
        painter.fillRect(
            QtCore.QRect(
                round(w * 0.63),
                round(h * top),
                round(w * 0.36),
                round(h * (bottom - top)),
            ),
            QtGui.QColor("#ffffff"),
        )
    painter.end()
    return pixmap
