"""Corner detection on a captured camera frame — the snap targets
for the Select Device Outline picker.

The SVG side gets its snap corners for free from the electrode path
vertices; a photographed device has no such geometry, so corners are
detected on the image itself: Shi-Tomasi (cv2.goodFeaturesToTrack)
finds the strong corner features — device outline corners, electrode
grid intersections — and cornerSubPix refines each to sub-pixel
accuracy so a snapped dot lands exactly on the physical corner.
"""

import numpy as np
from PySide6.QtGui import QImage

# OpenCV is an optional dependency here — snapping is an assist, so
# the picker must still open without it.
try:
    import cv2
except ImportError:
    cv2 = None

from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Detection caps: plenty of candidates for a whole frame while the
#: minimum spacing keeps clusters from crowding one physical corner.
MAX_CORNERS = 600
QUALITY_LEVEL = 0.02
MIN_DISTANCE_PX = 10


def _grayscale_array(image: QImage) -> np.ndarray:
    gray = image.convertToFormat(QImage.Format_Grayscale8)
    width, height = gray.width(), gray.height()
    rows = np.frombuffer(gray.constBits(), np.uint8).reshape(
        height, gray.bytesPerLine()
    )
    # .copy(), never ascontiguousarray: when bytesPerLine == width
    # the slice is already contiguous and ascontiguousarray returns
    # a VIEW into the temporary QImage's buffer, which is freed on
    # return — OpenCV then reads freed memory.
    return rows[:, :width].copy()


def detect_corner_points(image: QImage) -> list:
    """Sub-pixel corner features of ``image`` as [[x, y], ...] in
    image-pixel coordinates; [] when nothing is detected or OpenCV
    is unavailable."""
    if cv2 is None:
        logger.warning(
            "OpenCV not available — corner snapping in "
            "the outline picker is disabled"
        )
        return []
    if image.isNull():
        return []
    try:
        gray = _grayscale_array(image)
        corners = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=MAX_CORNERS,
            qualityLevel=QUALITY_LEVEL,
            minDistance=MIN_DISTANCE_PX,
        )
        if corners is None:
            return []
        cv2.cornerSubPix(
            gray,
            corners,
            winSize=(5, 5),
            zeroZone=(-1, -1),
            criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01),
        )
    except cv2.error as exc:
        # Snapping is an assist — a detection failure must never
        # keep the picker from opening.
        logger.warning(
            f"corner detection failed; snapping disabled " f"for this frame: {exc}"
        )
        return []
    return [[float(x), float(y)] for x, y in corners.reshape(-1, 2)]
