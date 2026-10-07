# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure display helpers for the 16-bit image viewer (hardware/Qt-light,
testable): loading QImages into numpy and window/level stretching."""

# Standard library imports.
import math

# Third-party imports.
import numpy as np
from PySide6.QtGui import QImage

# Local imports.
from .analysis.perspective import warp_frame
from .analysis.roi_compute import subtract_rolling_ball

#: Percentiles used by auto-contrast (ignores hot pixels / dark borders).
AUTO_CONTRAST_PERCENTILES = (0.1, 99.9)

#: Most pixels auto-contrast reads its percentiles from: larger frames
#: are sampled on an even grid (a 4K frame on every 3rd row and column),
#: still ~1M pixels, ample for a 0.1/99.9 percentile.
AUTO_CONTRAST_SAMPLE_PIXELS = 1 << 20

#: Widest integer dtype windowed through a lookup table (one uint8 entry
#: per possible value); anything wider takes the float path.
MAX_LOOKUP_TABLE_BYTES = 2


def qimage_to_array(image: QImage) -> np.ndarray:
    """A numpy copy of a loaded image: (H, W) uint16 for 16-bit grayscale,
    (H, W) uint8 for 8-bit grayscale, (H, W, 3) uint8 otherwise."""
    if image.format() == QImage.Format_Grayscale16:
        image = image.copy()
        array = np.frombuffer(image.constBits(), dtype=np.uint16)
        stride = image.bytesPerLine() // 2
        return array.reshape(image.height(), stride)[:, : image.width()].copy()
    if image.format() == QImage.Format_Grayscale8:
        image = image.copy()
        array = np.frombuffer(image.constBits(), dtype=np.uint8)
        return array.reshape(image.height(), image.bytesPerLine())[
            :, : image.width()
        ].copy()
    rgb = image.convertToFormat(QImage.Format_RGB888)
    array = np.frombuffer(rgb.constBits(), dtype=np.uint8)
    return (
        array.reshape(rgb.height(), rgb.bytesPerLine())[:, : rgb.width() * 3]
        .reshape(rgb.height(), rgb.width(), 3)
        .copy()
    )


def frame_to_qimage(img: np.ndarray) -> QImage:
    """A display QImage from an 8-bit grayscale (H, W) or RGB (H, W, 3)
    frame. Copies, so the QImage outlives the source buffer."""
    frame = np.ascontiguousarray(img)
    height, width = frame.shape[:2]
    image_format = QImage.Format_Grayscale8 if frame.ndim == 2 else QImage.Format_RGB888

    return QImage(frame.data, width, height, frame.strides[0], image_format).copy()


def load_image_array(path) -> np.ndarray:
    """Pixel data for an image file via :func:`qimage_to_array`, or None
    when the file is missing/unreadable."""
    image = QImage(str(path))
    if image.isNull():
        return None
    return qimage_to_array(image)


def stretch_to_8bit(
    array: np.ndarray, auto_contrast: bool = True, window=None
) -> np.ndarray:
    """Window a grayscale frame into displayable 8-bit.

    auto_contrast maps the (0.1, 99.9) percentile window onto 0..255 —
    without it a typical fluorescence frame (small bright signal on a dark
    field) renders nearly black. Off = the manual ``window`` (low, high)
    when given, else the full dtype range, linearly.

    Integer frames go through a per-value lookup table, so a 4K 16-bit
    frame costs one indexing pass rather than several float64 copies.
    """
    if array.ndim != 2:
        return array if array.dtype == np.uint8 else (array >> 8).astype(np.uint8)

    if auto_contrast:
        low, high = np.percentile(_contrast_sample(array), AUTO_CONTRAST_PERCENTILES)

        if high <= low:
            low, high = float(array.min()), float(array.max() or 1)
    elif window is not None:
        low, high = float(window[0]), float(window[1])
    else:
        low, high = 0.0, float(np.iinfo(array.dtype).max)

    if high <= low:
        return np.zeros(array.shape, dtype=np.uint8)

    if array.dtype.kind == "u" and array.dtype.itemsize <= MAX_LOOKUP_TABLE_BYTES:
        values = np.arange(np.iinfo(array.dtype).max + 1, dtype=np.float64)

        return np.take(_window_to_8bit(values, low, high), array)

    return _window_to_8bit(array.astype(np.float64), low, high)


def _contrast_sample(array):
    """The pixels auto-contrast reads: the whole frame up to
    AUTO_CONTRAST_SAMPLE_PIXELS, an even strided grid beyond."""
    stride = math.ceil(math.sqrt(array.size / AUTO_CONTRAST_SAMPLE_PIXELS))

    return array[::stride, ::stride] if stride > 1 else array


def _window_to_8bit(values, low, high):
    """``values`` (float64) mapped linearly from ``low``..``high`` onto
    0..255, clipped."""
    return np.clip((values - low) / (high - low) * 255.0, 0, 255).astype(np.uint8)


def render_display_frame(array, auto_contrast, window, ball_radius_px, perspective):
    """What the canvas shows for ``array``: perspective-warped, then
    rolling-ball corrected while those corrections are on — the canvas
    shows what is measured rather than what was on disk — and windowed
    to 8-bit.

    Returns ``(corrected, display)``: the corrected frame at its true
    values (``array`` itself when no correction is on; the hover readout
    reads it) and the 8-bit frame to draw. Pure numpy/cv2, so the
    controller runs it on its loader thread.
    """
    corrected = warp_frame(array, perspective)

    if ball_radius_px:
        corrected = subtract_rolling_ball(corrected, ball_radius_px)

    return corrected, stretch_to_8bit(corrected, auto_contrast, window=window)
