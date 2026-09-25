# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json
from pathlib import Path

# Enthought library imports.
from pyface.qt.QtCore import QObject, Signal
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem

# Microdrop package imports.
from device_viewer.consts import RECORDING_TRANSFORM_SIDECAR_SUFFIX
from device_viewer.models.media import MediaType
from device_viewer.views.camera_control_view.utils import _cache_media_capture

# Local imports.
from ..qt_geometry_serialization import qtransform_serialize

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class VideoRecorderBase(QObject):
    """Common surface of the interchangeable video recorders
    (NativeVideoRecorder, RawFFMPEGVideoRecorder), so call sites can swap
    implementations without touching anything but construction:

    - ``start(output_path, resolution, fps)`` / ``stop()``
    - ``is_recording`` property
    - ``current_image`` (always None — screenshots fall back to the live
      sink)
    - ``recording_started`` / ``recording_stopped`` / ``error_occurred``
      signals

    Subclasses call ``_finalize_recording`` when a recording lands on disk;
    it performs the shared stop-side bookkeeping (alignment-transform
    sidecar, capture cache, ``recording_stopped``).
    """

    recording_started = Signal(str)  # Emits path when started
    recording_stopped = Signal(str)  # Emits output path
    error_occurred = Signal(str)

    def __init__(self, video_item: "QGraphicsVideoItem", parent=None):
        super().__init__(parent)
        self._video_item = video_item
        self.current_image = None  # screenshots fall back to the live sink

    @property
    def is_recording(self) -> bool:
        raise NotImplementedError

    def start(self, output_path, resolution, fps):
        """Start recording to ``output_path``. ``resolution`` is the
        selected camera format's size; ``fps`` its nominal frame rate."""
        raise NotImplementedError

    def stop(self):
        """Stop recording; ``recording_stopped`` fires once the file is
        finalized."""
        raise NotImplementedError

    def _finalize_recording(self, output_path):
        """Shared stop-side bookkeeping: persist the alignment geometry
        sidecar, cache the capture, announce the recording."""
        write_transform_sidecar(self._video_item, output_path)
        _cache_media_capture.send(MediaType.VIDEO, output_path)
        self.recording_stopped.emit(output_path)


def write_transform_sidecar(video_item, video_path):
    """Persist the alignment geometry needed to reproduce the
    device-aligned (warped) view offline — the same parameters the
    legacy pipeline fed to get_transformed_frame for every frame."""
    sidecar = {
        "transform": json.loads(qtransform_serialize(video_item.transform())),
        "scene_bounding_rect": list(video_item.sceneBoundingRect().getRect()),
        "bounding_rect": list(video_item.boundingRect().getRect()),
    }
    sidecar_path = Path(video_path).with_suffix(RECORDING_TRANSFORM_SIDECAR_SUFFIX)
    try:
        sidecar_path.write_text(json.dumps(sidecar, indent=2))
        logger.info(f"Wrote recording transform sidecar: {sidecar_path}")
    except Exception as e:
        logger.warning(f"Could not write transform sidecar: {e}")
