# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A live camera frame's centre as a small greyscale array, for measuring
its sharpness on the GUI thread."""

# Standard library imports.
import math

# Third-party imports.
import numpy as np

# Enthought library imports.
from pyface.qt.QtCore import QRect, Qt
from pyface.qt.QtGui import QImage
from pyface.qt.QtMultimedia import QVideoFrame, QVideoFrameFormat

# Local imports.
from ..consts import AUTOFOCUS_SAMPLE_WIDTH_PX

#: 8-bit pixel formats whose first plane is the luma (greyscale) image.
LUMA_PLANE_PIXEL_FORMATS = (
    QVideoFrameFormat.PixelFormat.Format_NV12,
    QVideoFrameFormat.PixelFormat.Format_NV21,
    QVideoFrameFormat.PixelFormat.Format_YUV420P,
    QVideoFrameFormat.PixelFormat.Format_YV12,
    QVideoFrameFormat.PixelFormat.Format_YUV422P,
    QVideoFrameFormat.PixelFormat.Format_Y8,
)


def frame_centre_luma(frame, max_width=AUTOFOCUS_SAMPLE_WIDTH_PX):
    """The centre half of ``frame`` (a QVideoFrame) as a 2-D uint8 luma
    array at most ``max_width`` wide, or None when it cannot be read.

    Planar YUV frames are subsampled straight from their luma plane; any
    other format goes through a QImage conversion.
    """

    if not frame.isValid():
        return None

    width, height = frame.width(), frame.height()

    if frame.pixelFormat() not in LUMA_PLANE_PIXEL_FORMATS:
        return _image_centre_luma(frame.toImage(), max_width)

    if not frame.map(QVideoFrame.MapMode.ReadOnly):
        return None

    try:
        stride = frame.bytesPerLine(0)
        plane = np.frombuffer(frame.bits(0), np.uint8, stride * height)
        step = max(1, math.ceil(width / 2 / max_width))
        luma = plane.reshape(height, stride)[
            height // 4 : 3 * height // 4 : step, width // 4 : 3 * width // 4 : step
        ]

        # The copy outlives the mapped buffer.
        return luma.copy()
    finally:
        frame.unmap()


def _image_centre_luma(image, max_width):
    if image.isNull():
        return None

    width, height = image.width(), image.height()
    centre = image.copy(QRect(width // 4, height // 4, width // 2, height // 2))

    if centre.width() > max_width:
        centre = centre.scaledToWidth(
            max_width, Qt.TransformationMode.FastTransformation
        )

    grey = centre.convertToFormat(QImage.Format.Format_Grayscale8)
    rows = np.frombuffer(
        grey.constBits(), np.uint8, grey.height() * grey.bytesPerLine()
    )

    return rows.reshape(grey.height(), grey.bytesPerLine())[:, : grey.width()].copy()
