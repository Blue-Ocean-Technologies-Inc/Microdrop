# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Image viewer dock pane (thin MVC shell).

Displays captured images — 16-bit raw sensor frames included — with
auto-contrast/manual windowing,
wheel-zoom/drag-pan, and a live pixel-value readout. The pane discovers
the current experiment's raw captures itself, follows new ones as they
land, and can step/cycle through them like a slideshow.

State lives in :class:`ImageViewerModel` (Qt-free), behavior
in :class:`ImageViewerController`, widgets in ``view.py``.
This pane only assembles them, owns the Qt timers (the view-injected
schedulers), and binds the persisted display-window preferences.
"""

# Standard library imports.
import threading
from pathlib import Path

# Third-party imports.
from PySide6.QtCore import QTimer

# Enthought library imports.
from pyface.tasks.api import TraitsDockPane
from traits.api import Any, Instance, observe

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME, media_capture_event_model

# Local imports.
from .analysis.ai_controller import AiRoiController
from .analysis.consts import ANALYSIS_RESULT_DRAIN_INTERVAL_MS
from .analysis.roi_batch import _shared_executor
from .analysis.roi_controller import RoiAnalysisController
from .consts import (
    DISCOVERY_POLL_INTERVAL_MS,
    IMAGE_FILTERS,
    PKG,
    SLIDESHOW_INTERVAL_MS,
)
from .controller import ImageViewerController
from .model import ImageViewerModel
from .view import ImageViewerView

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

_dock_pane_name = "Image Viewer"


def _title_for(browsed_directory: str, info_text: str) -> str:
    """The pane title for the browsed folder — "Name - folder", the
    device-viewer dock pane's convention — plus the loaded image's
    summary (the model's ``info_text``). The default captures dir would
    just read "captures", so its parent (the experiment folder) names it
    instead; '' (nothing resolved yet) keeps the bare name."""
    title = _dock_pane_name
    if browsed_directory:
        folder = Path(browsed_directory)
        display = (
            folder.parent.name
            if folder.name == CAPTURES_DIR_NAME and folder.parent.name
            else folder.name
        )
        title += "\t-\t" + display
    if info_text:
        title += "\t-\t" + info_text
    return title


class ImageViewerDockPane(TraitsDockPane):
    """Viewer for captured images (16-bit aware)."""

    id = PKG + ".dock_pane"
    name = _dock_pane_name

    view = ImageViewerView

    model = Instance(ImageViewerModel)
    controller = Instance(ImageViewerController)
    analysis_controller = Instance(RoiAnalysisController)
    ai_controller = Instance(AiRoiController)
    _poll_timer = Any()
    _play_timer = Any()
    _drain_timer = Any()

    def traits_init(self):
        self.model = ImageViewerModel()
        self.controller = ImageViewerController(model=self.model)
        self.analysis_controller = RoiAnalysisController(
            viewer_model=self.model, analysis_model=self.model.roi_analysis
        )
        self.ai_controller = AiRoiController(
            viewer_model=self.model, analysis_model=self.model.roi_analysis
        )
        # Warm the process pool off-thread so the first Calculate does
        # not pay the Windows spawn cost (~seconds for cv2 workers).
        threading.Thread(target=_shared_executor, daemon=True).start()
        # Event-driven refresh: the device viewer fires this the moment a
        # capture file finishes writing, so new images appear immediately
        # instead of on the next poll tick (the poll below stays only to
        # follow experiment-folder switches).
        media_capture_event_model.observe(self._on_media_captured, "captured")

    def trait_context(self):
        """The pane's model and the analysis model.

        TraitsUI checks every ``enabled_when`` when a trait changes on
        an object IN THE CONTEXT, and not for nested traits reached
        through one. The rolling-ball controls are enabled by a trait
        on the analysis model, which is nested under the viewer model —
        so without this the toolbar toggle left them stale until some
        unrelated edit to the viewer model (hovering the image, which
        writes the pixel readout) happened to trigger the check.
        """
        context = super().trait_context()
        context["analysis"] = self.model.roi_analysis
        return context

    def destroy(self):
        media_capture_event_model.observe(
            self._on_media_captured, "captured", remove=True
        )
        super().destroy()

    def _on_media_captured(self, event):
        self.controller.capture_saved(event.new)

    def create_contents(self, parent):
        self.ui = self.edit_traits(
            kind="subpanel", parent=parent, handler=self.controller
        )
        control = self.ui.control
        # Qt schedulers are view-owned: the slideshow tick and the
        # experiment-folder-switch poll (new captures arrive event-driven
        # via media_capture_event_model above).
        self._play_timer = QTimer(control)
        self._play_timer.setInterval(SLIDESHOW_INTERVAL_MS)
        self._play_timer.timeout.connect(lambda: self.controller.step(1))
        self._poll_timer = QTimer(control)
        self._poll_timer.setInterval(DISCOVERY_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self.controller.rescan)
        self._poll_timer.start()
        self._drain_timer = QTimer(control)
        self._drain_timer.setInterval(ANALYSIS_RESULT_DRAIN_INTERVAL_MS)
        self._drain_timer.timeout.connect(self._drain_tick)
        self._drain_timer.start()

        if self.task is not None:
            application = self.task.window.application
            self.controller.image_filters_source = lambda: application.get_extensions(
                IMAGE_FILTERS
            )

        self.controller.rescan()

        return control

    def _drain_tick(self):
        self.controller.drain_loaded()
        # ai_controller first: its TRACK_FRAME handling marks
        # tracked-override config dirty, and analysis_controller's
        # drain_results/flush_stats should flush that in the same tick
        # it was marked, not a tick behind.
        self.ai_controller.drain_results()
        self.analysis_controller.drain_results()
        self.analysis_controller.flush_stats()

    @observe("model:browsed_directory, model:info_text")
    def _update_title(self, event):
        self.name = _title_for(self.model.browsed_directory, self.model.info_text)

    @observe("model:playing")
    def _sync_slideshow_timer(self, event):
        if self._play_timer is None:
            return
        if event.new:
            self._play_timer.start()
        else:
            self._play_timer.stop()
