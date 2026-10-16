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
from pyface.qt import QtCore, QtWidgets
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


def _scroll_area_around(control):
    """Return the nearest ``QScrollArea`` enclosing ``control``."""
    while not isinstance(control, QtWidgets.QScrollArea):
        control = control.parentWidget()

    return control


def _make_scroll_strip(scroll_area, orientation):
    """Turn a scrollable group into a strip that scrolls along ``orientation``.

    TraitsUI wraps a scrollable group in a scroll area that expands both
    ways, so a strip would take stretch from the canvas. Its cross size
    is pinned instead to the content's size hint, plus the scrollbar's
    thickness while that bar is shown.
    """
    content = scroll_area.widget()
    horizontal = orientation == QtCore.Qt.Orientation.Horizontal
    always_off = QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    as_needed = QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
    expanding = QtWidgets.QSizePolicy.Policy.Expanding
    fixed = QtWidgets.QSizePolicy.Policy.Fixed

    # The scroll area's content widget would add the style's 9 px layout
    # margins around the buttons, on top of the enclosing group's own.
    content.layout().setContentsMargins(0, 0, 0, 0)

    if horizontal:
        bar = scroll_area.horizontalScrollBar()
        scroll_area.setHorizontalScrollBarPolicy(as_needed)
        scroll_area.setVerticalScrollBarPolicy(always_off)
        scroll_area.setSizePolicy(expanding, fixed)
    else:
        bar = scroll_area.verticalScrollBar()
        scroll_area.setHorizontalScrollBarPolicy(always_off)
        scroll_area.setVerticalScrollBarPolicy(as_needed)
        scroll_area.setSizePolicy(fixed, expanding)

    # The bar shows exactly when its range is non-empty, so its range
    # change is the moment to add or drop the bar's thickness.
    def pin_cross_size(_minimum, maximum):
        hint = content.sizeHint()
        bar_hint = bar.sizeHint()

        if horizontal:
            extra = bar_hint.height() if maximum > 0 else 0
            scroll_area.setFixedHeight(hint.height() + extra)
        else:
            extra = bar_hint.width() if maximum > 0 else 0
            scroll_area.setFixedWidth(hint.width() + extra)

    bar.rangeChanged.connect(pin_cross_size)
    pin_cross_size(bar.minimum(), bar.maximum())


class _AdvancedSplit(QtCore.QObject):
    """Size the divider between the canvas and the Advanced block.

    Advanced first opens at its content height and the canvas takes the
    rest, plus every later gain in pane height. While Advanced is
    collapsed its pane is pinned to the header row, so the divider cannot
    move; reopening restores the height the user last dragged it to.
    """

    def __init__(self, splitter, advanced):
        super().__init__(splitter)
        self._splitter = splitter
        self._advanced = advanced
        self._lower = splitter.widget(1)
        self._unbounded_height = self._lower.maximumHeight()
        self._open_height = None
        #: None until the first sync, then whether Advanced is folded.
        self._folded = None

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        # A collapsed pane would take the Advanced chevron with it.
        splitter.setChildrenCollapsible(False)
        splitter.installEventFilter(self)

    def eventFilter(self, watched, event):
        # TraitsUI's splitter sets its own sizes as it is first shown;
        # ours apply on the next event-loop pass, once, after that.
        if event.type() == QtCore.QEvent.Type.Show:
            self._splitter.removeEventFilter(self)
            QtCore.QTimer.singleShot(0, self.sync)

        return False

    def sync(self):
        """Fit the split to whether Advanced is shown (its visible_when)."""
        splitter = self._splitter
        lower = self._lower
        sizes = splitter.sizes()
        total = sum(sizes)

        if self._advanced.isHidden():
            if self._folded is False:
                self._open_height = sizes[1]

            self._folded = True
            lower.setMaximumHeight(lower.minimumSizeHint().height())
            splitter.setSizes([total, 0])

            return

        self._folded = False
        lower.setMaximumHeight(self._unbounded_height)
        height = self._open_height or self._content_height()
        splitter.setSizes([max(total - height, 0), height])

    def _content_height(self):
        """Height showing all of Advanced: header row plus its content."""
        advanced = self._advanced
        content = advanced.widget()
        bar = advanced.horizontalScrollBar()
        overflows = content.minimumSizeHint().width() > advanced.viewport().width()
        bar_height = bar.sizeHint().height() if overflows else 0
        header_height = self._lower.sizeHint().height() - advanced.sizeHint().height()

        return header_height + content.sizeHint().height() + bar_height


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
    _advanced_split = Any()

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
        self.controller.close_metadata_window()
        super().destroy()

    def _on_media_captured(self, event):
        self.controller.capture_saved(event.new)

    def create_contents(self, parent):
        self.ui = self.edit_traits(
            kind="subpanel", parent=parent, handler=self.controller
        )
        control = self.ui.control

        # TraitsUI's HSplit defaults to rubber-band resizing, so the
        # columns and the canvas only re-lay out on release. Opaque resize
        # makes the drag continuous; the canvas refit on each move is a
        # cheap view transform.
        for splitter in control.findChildren(QtWidgets.QSplitter):
            splitter.setOpaqueResize(True)

        # TraitsUI's scrollable View, groups and editors wrap in a framed
        # QScrollArea; the pane wants a flat look. Only plain scroll areas
        # are touched, so tables and text editors keep their own frames.
        scroll_areas = control.findChildren(QtWidgets.QScrollArea)

        if isinstance(control, QtWidgets.QScrollArea):
            scroll_areas.append(control)

        for scroll_area in scroll_areas:
            scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        # The icon row above the image scrolls sideways and the analysis
        # toolbar beside it scrolls down, each on its own: neither sets
        # a minimum on the canvas, which takes all the remaining space.
        icon_row = self.ui.get_editors("fit_button")[0].control
        _make_scroll_strip(
            _scroll_area_around(icon_row), QtCore.Qt.Orientation.Horizontal
        )
        toolbar_button = self.ui.get_editors("draw_ellipse_button")[0].control
        _make_scroll_strip(
            _scroll_area_around(toolbar_button), QtCore.Qt.Orientation.Vertical
        )

        # The Advanced block scrolls both ways under the canvas, below a
        # divider the user drags (see _AdvancedSplit).
        scale_readout = self.ui.get_editors("scale_text")[0].control
        advanced = _scroll_area_around(scale_readout)
        advanced.widget().layout().setContentsMargins(0, 0, 0, 0)
        advanced_splitter = advanced

        while not isinstance(advanced_splitter, QtWidgets.QSplitter):
            advanced_splitter = advanced_splitter.parentWidget()

        self._advanced_split = _AdvancedSplit(advanced_splitter, advanced)

        # The sidebar reveal column sits flush with the pane's left edge,
        # 2 px from the splitter: the default 6 px item spacing would
        # more than double the slim button's width. The other three edges
        # keep a 9 px gap, so the analysis toolbar does not touch the dock
        # border (the unscrolled View's panel has no margins of its own).
        reveal_button = self.ui.get_editors("toggle_sidebar_button")[0].control
        top_layout = reveal_button.parentWidget().layout()
        top_layout.setContentsMargins(0, 9, 9, 9)
        top_layout.setSpacing(2)

        # Qt schedulers are view-owned: the slideshow tick and the
        # experiment-folder-switch poll (new captures arrive event-driven
        # via media_capture_event_model above).
        self._play_timer = QTimer(control)
        self._play_timer.setInterval(SLIDESHOW_INTERVAL_MS)
        self._play_timer.timeout.connect(lambda: self.controller.step(1))
        self._poll_timer = QTimer(control)
        self._poll_timer.setInterval(DISCOVERY_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self.controller.request_rescan)
        self._poll_timer.start()
        self._drain_timer = QTimer(control)
        self._drain_timer.setInterval(ANALYSIS_RESULT_DRAIN_INTERVAL_MS)
        self._drain_timer.timeout.connect(self._drain_tick)
        self._drain_timer.start()

        if self.task is not None:
            application = self.task.window.application
            self.controller.application = application
            self.controller.image_filters_source = lambda: application.get_extensions(
                IMAGE_FILTERS
            )

        self.controller.request_rescan()

        return control

    def _drain_tick(self):
        self.controller.drain_loaded()
        self.controller.drain_discovered()
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

    @observe("model:show_advanced_settings")
    def _fold_advanced_split(self, event):
        # Deferred: the chevron's visible_when hides the block in the same
        # change notification, and the split reads that visibility.
        if self._advanced_split is not None:
            QTimer.singleShot(0, self._advanced_split.sync)

    @observe("model:playing")
    def _sync_slideshow_timer(self, event):
        if self._play_timer is None:
            return
        if event.new:
            self._play_timer.start()
        else:
            self._play_timer.stop()
