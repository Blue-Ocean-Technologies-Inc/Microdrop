# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Render the image canvas — the displayed frame and the overlays drawn
over it — to a QImage at the frame's native resolution. Rendering the
scene rather than grabbing the viewport makes the copy independent of
the zoom, the pan and the pane's size."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui

# Local imports.
from .analysis.roi_handles import (
    CornerRadiusHandle,
    NodeHandle,
    ResizeHandle,
    RotateHandle,
)

#: Edit grips: shown on the selected ROI while editing it, never part of
#: what the image shows.
EDIT_GRIP_TYPES = (CornerRadiusHandle, NodeHandle, ResizeHandle, RotateHandle)


def render_image_with_annotations(scene, image_item):
    """Render ``scene`` over ``image_item``'s bounds, one scene unit per
    pixel: the frame as displayed (windowed / false-coloured) plus every
    overlay on it, minus the edit grips.

    Returns
    -------
    QImage or None
        None when ``image_item`` holds no image.
    """
    source = image_item.sceneBoundingRect()

    if source.isEmpty():
        return None

    image = QtGui.QImage(source.size().toSize(), QtGui.QImage.Format.Format_RGB32)
    image.fill(QtCore.Qt.GlobalColor.black)

    # Hidden for the render only: exactly the grips showing now come back.
    grips = [
        item
        for item in scene.items()
        if isinstance(item, EDIT_GRIP_TYPES) and item.isVisible()
    ]

    for grip in grips:
        grip.setVisible(False)

    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)

    try:
        scene.render(painter, QtCore.QRectF(image.rect()), source)

    finally:
        painter.end()

        for grip in grips:
            grip.setVisible(True)

    return image
