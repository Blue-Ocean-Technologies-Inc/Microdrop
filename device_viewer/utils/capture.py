# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Still-image capture: the aligned frame grab, capture file names, and the
background PNG writer."""

# Enthought library imports.
from pyface.qt.QtCore import QObject, QRectF, QRunnable, Qt, Signal
from pyface.qt.QtGui import QImage, QPainter, QTransform

# Microdrop utils imports.
from microdrop_utils.datetime_helpers import get_current_utc_datetime

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def get_transformed_frame(
    src_image: QImage,
    src_rect: QRectF,
    target_rect: QRectF,
    transform: QTransform,
    target_resolution: tuple[int, int],
):
    tw, th = target_resolution

    # Create the output image at the FINAL resolution immediately
    output_image = QImage(tw, th, QImage.Format_RGBA8888)
    output_image.fill(Qt.black)  # Black bars for aspect ratio mismatch

    painter = QPainter(output_image)

    # 1. Enable High-Quality Scaling inside the painter
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    # 2. Calculate the scale factor between 'canvas' and 'target resolution'
    scale_x = tw / src_rect.width()
    scale_y = th / src_rect.height()

    # 3. Apply scaling globally so everything drawn fits the target res
    painter.scale(scale_x, scale_y)

    # 4. Same coordinate logic as before
    painter.translate(-src_rect.x(), -src_rect.y())
    painter.setTransform(transform, combine=True)

    # Draw the source (NV12 to RGB conversion happens here automatically)
    painter.drawImage(target_rect, src_image)

    painter.end()
    return output_image


def media_filename(
    step_description=None, step_id=None, file_extension=".png", timestamp=None
):
    """The capture/recording file name for a step (description + id), an
    id alone, a description alone (a requester's own tag, e.g. the
    fluorescence capture's ``flu_<label>_f<position>``), or free mode.
    Only alphanumerics, '-' and '_' survive from the description."""
    stamp = timestamp or get_current_utc_datetime()

    if step_description:
        clean_desc = "".join(
            c for c in step_description if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        clean_desc = clean_desc.replace(" ", "_")

        if step_id:
            return f"{clean_desc}_{step_id}_{stamp}{file_extension}"

        return f"{clean_desc}_{stamp}{file_extension}"

    if step_id:
        return f"step_{step_id}_{stamp}{file_extension}"

    return f"free_mode_{stamp}{file_extension}"


class SaveSignals(QObject):
    # Both signals send the save_path.
    save_complete = Signal(str)
    save_failed = Signal(str)


class ImageSaver(QRunnable):
    """PNG-encode + write ``image`` to ``save_path``; run it on a QThreadPool
    (encoding a full-resolution frame takes long enough to visibly freeze the
    GUI when run inline). Callers must hand over an image they will not paint
    into afterwards (pass ``image.copy()`` if unsure) — QImage is implicitly
    shared, so holding the reference is enough and copying here would put a
    second full-frame memcpy on the caller's (GUI) thread."""

    def __init__(self, image, save_path):
        super().__init__()
        self.image = image
        self.save_path = save_path
        self.signals = SaveSignals()

    def run(self):
        try:
            # 1. Heavy PNG encode + disk I/O happens here.
            if self.image.save(self.save_path, "PNG"):
                logger.info(f"Saved image to: {self.save_path}")
                # 2. Tell the UI we are done (queued back to the GUI thread).
                self.signals.save_complete.emit(self.save_path)
            else:
                logger.error(f"Failed to save image: {self.save_path}")
                self.signals.save_failed.emit(self.save_path)
        except Exception as e:
            logger.error(f"Failed to save image {self.save_path}: {e}")
            self.signals.save_failed.emit(self.save_path)
