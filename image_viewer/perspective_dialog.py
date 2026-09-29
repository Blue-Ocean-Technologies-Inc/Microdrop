# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The perspective-definition window: the device viewer's camera-alignment
interaction over a captured frame. Click four points on the image (e.g. the
chip's corners), then drag each corner to where it belongs — the frame
re-warps live. Reset starts over; the rotate buttons turn the result.

Scene coordinates are image pixels, so the quads it returns are exactly
what PerspectiveCorrection stores and warp_frame applies.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR, GREY, WARNING_COLOR

# Local imports.
from .analysis.perspective import rotated_quad
from .analysis.roi_model import PerspectiveCorrection
from .display import frame_to_qimage, stretch_to_8bit

#: Corner handle radius and outline width, in screen pixels (the view
#: keeps them a constant size whatever the zoom).
HANDLE_RADIUS_PX = 6
OUTLINE_WIDTH_PX = 2

#: Wheel-zoom factor per notch.
ZOOM_STEP = 1.25

PLACE_HINT = "Click the four points to correct (e.g. the chip's corners)."
EDIT_HINT = (
    "Drag each corner to where it belongs — the image re-warps live. "
    "Reset to pick new points."
)


def to_qtransform(matrix):
    """The flattened row-major homography as a QTransform (Qt multiplies
    row vectors, so the matrix goes in transposed)."""
    m = matrix

    return QtGui.QTransform(m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8])


class _QuadView(QtWidgets.QGraphicsView):
    """The frame plus the quad being defined; mouse input drives the
    placement and corner drags against ``correction``."""

    #: Emitted whenever the quads change (the dialog refreshes its hint
    #: and buttons).
    changed = QtCore.Signal()

    def __init__(self, array, correction, parent=None):
        super().__init__(parent)
        self.correction = correction

        #: Points clicked so far while placing (source space).
        self._placed = []

        #: Index of the target corner being dragged, -1 for none.
        self._dragging = -1

        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor(GREY["dark"]))

        display = stretch_to_8bit(array, auto_contrast=True)
        self._pixmap = self.scene().addPixmap(
            QtGui.QPixmap.fromImage(frame_to_qimage(display))
        )
        height, width = array.shape[:2]
        self._bounds = QtCore.QRectF(0, 0, width, height)

        # The output frame: the warp keeps the image's size, so anything
        # dragged outside this outline is cropped away.
        frame_pen = QtGui.QPen(QtGui.QColor(GREY["lighter"]), 0, QtCore.Qt.DashLine)
        self.scene().addRect(self._bounds, frame_pen)
        self.scene().setSceneRect(
            self._bounds.adjusted(-width / 4, -height / 4, width / 4, height / 4)
        )

        self._outline = self.scene().addPath(QtGui.QPainterPath())
        self._handles = []
        self._redraw()

    # ------------------------------------------------------------------ #
    # Mouse interaction                                                    #
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            super().mousePressEvent(event)
            return

        point = self.mapToScene(event.position().toPoint())

        if self.correction.is_defined():
            self._dragging = self._nearest_corner(point)
            self._move_corner(point)
            return

        self._placed.append((point.x(), point.y()))

        if len(self._placed) == 4:
            self.correction.trait_set(
                source_quad=list(self._placed), target_quad=list(self._placed)
            )
            self._placed = []

        self._redraw()

    def mouseMoveEvent(self, event):
        if self._dragging < 0:
            super().mouseMoveEvent(event)
            return

        self._move_corner(self.mapToScene(event.position().toPoint()))

    def mouseReleaseEvent(self, event):
        self._dragging = -1
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        factor = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
        self.scale(factor, factor)
        self._redraw()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def fit(self):
        self.fitInView(self.scene().sceneRect(), QtCore.Qt.KeepAspectRatio)
        self._redraw()

    def _nearest_corner(self, point):
        distances = [
            (x - point.x()) ** 2 + (y - point.y()) ** 2
            for x, y in self.correction.target_quad
        ]

        return distances.index(min(distances))

    def _move_corner(self, point):
        target = list(self.correction.target_quad)
        target[self._dragging] = (point.x(), point.y())
        candidate = PerspectiveCorrection(
            source_quad=self.correction.source_quad, target_quad=target
        )

        # A drag that would fold the quad over itself has no inverse:
        # keep the last valid corner rather than a broken frame.
        if candidate.is_defined():
            self.correction.target_quad = target
            self._redraw()

    # ------------------------------------------------------------------ #
    # Drawing                                                              #
    # ------------------------------------------------------------------ #
    def reset(self):
        self.correction.trait_set(source_quad=[], target_quad=[])
        self._placed = []
        self._redraw()

    def rotate(self, degrees):
        if self.correction.is_defined():
            self.correction.target_quad = rotated_quad(
                self.correction.target_quad, degrees
            )
            self._redraw()

    def _redraw(self):
        defined = self.correction.is_defined()
        matrix = self.correction.matrix
        self._pixmap.setTransform(
            to_qtransform(matrix) if defined else QtGui.QTransform()
        )

        points = self.correction.target_quad if defined else self._placed
        colour = QtGui.QColor(ERROR_COLOR if defined else WARNING_COLOR)
        path = QtGui.QPainterPath()

        if points:
            path.moveTo(*points[0])

            for x, y in points[1:]:
                path.lineTo(x, y)

            if len(points) == 4:
                path.closeSubpath()

        # Cosmetic pens and an ignore-transformations handle keep the
        # overlay a constant on-screen size at any zoom.
        pen = QtGui.QPen(colour, OUTLINE_WIDTH_PX)
        pen.setCosmetic(True)
        self._outline.setPath(path)
        self._outline.setPen(pen)

        for handle in self._handles:
            self.scene().removeItem(handle)

        self._handles = []

        for x, y in points:
            handle = self.scene().addEllipse(
                -HANDLE_RADIUS_PX,
                -HANDLE_RADIUS_PX,
                2 * HANDLE_RADIUS_PX,
                2 * HANDLE_RADIUS_PX,
                pen,
                QtGui.QBrush(colour),
            )
            handle.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            handle.setPos(x, y)
            self._handles.append(handle)

        self.changed.emit()


class PerspectiveDialog(QtWidgets.QDialog):
    """Define a perspective correction over ``array``, starting from the
    stored quads (placement when there are none)."""

    def __init__(self, array, source_quad, target_quad, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Define Perspective Correction")
        self.resize(900, 700)

        self.correction = PerspectiveCorrection(
            source_quad=list(source_quad), target_quad=list(target_quad)
        )
        self.view = _QuadView(array, self.correction, self)
        self.hint = QtWidgets.QLabel()

        reset = QtWidgets.QPushButton("Reset")
        reset.clicked.connect(self.view.reset)
        self.rotate_left = QtWidgets.QPushButton("Rotate -90°")
        self.rotate_left.clicked.connect(lambda: self.view.rotate(-90))
        self.rotate_right = QtWidgets.QPushButton("Rotate +90°")
        self.rotate_right.clicked.connect(lambda: self.view.rotate(90))
        fit = QtWidgets.QPushButton("Fit")
        fit.clicked.connect(self.view.fit)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        tools = QtWidgets.QHBoxLayout()

        for button in (reset, self.rotate_left, self.rotate_right, fit):
            tools.addWidget(button)

        tools.addStretch()
        tools.addWidget(self.buttons)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.hint)
        layout.addWidget(self.view, stretch=1)
        layout.addLayout(tools)

        self.view.changed.connect(self._sync)
        self._sync()

    def _sync(self):
        defined = self.correction.is_defined()
        self.hint.setText(EDIT_HINT if defined else PLACE_HINT)
        self.rotate_left.setEnabled(defined)
        self.rotate_right.setEnabled(defined)
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(defined)


def define_perspective(array, source_quad, target_quad, parent=None):
    """Run the definition window over ``array``; (source_quad,
    target_quad) on OK, None on cancel."""
    dialog = PerspectiveDialog(array, source_quad, target_quad, parent)

    if dialog.exec() != QtWidgets.QDialog.Accepted:
        return None

    return (
        list(dialog.correction.source_quad),
        list(dialog.correction.target_quad),
    )
