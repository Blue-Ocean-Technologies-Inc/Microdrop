# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state for the Fluorescence Capture pane: one row per filter-wheel
position (Capture tick, auto focus, LED %, exposure, focus) on the shared
capture-pane state (see capture_pane_model.py), keyed by filter_position.
Trait mutations are safe from any thread — attach_step/detach_step are
called from the message handler's Dramatiq worker thread; only Qt object
creation needs the GUI thread (see the controller)."""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import Bool, Enum, Event, HasTraits, Int, Range, Str

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    FILTER_POSITIONS,
    FLUORESCENCE_DEFAULT_EXPOSURE_MS,
    FLUORESCENCE_DEFAULT_LED_PERCENT,
    FLUORESCENCE_EXPOSURE_MS_BOUNDS,
    FLUORESCENCE_LED_PERCENT_BOUNDS,
    FluorescenceStepCapture,
)

# Local imports.
from ..consts import (
    DEFAULT_FLUORESCENCE_EXPOSURE_RANGE,
    FLUORESCENCE_EXPOSURE_RANGES,
    PORTABLE_DROPBOT_IMAGE,
)
from .capture_pane_model import CapturePaneModel, CaptureRow


class FluorescenceRow(CaptureRow):
    """One filter-wheel position as a table row."""

    KEY_NAME = "filter_position"

    #: Filter-wheel position (FILTER_POSITIONS) — the identity of the row.
    filter_position = Int
    led_percent = Range(
        *FLUORESCENCE_LED_PERCENT_BOUNDS,
        FLUORESCENCE_DEFAULT_LED_PERCENT,
        desc="Fluorescence LED level, percent of full scale",
        setting=True,
    )
    exposure_ms = Range(
        *FLUORESCENCE_EXPOSURE_MS_BOUNDS,
        FLUORESCENCE_DEFAULT_EXPOSURE_MS,
        desc="Camera exposure for this filter position, milliseconds",
        setting=True,
    )
    #: True = continuous auto focus; False = the fixed focus_distance below.
    auto_focus = Bool(True, desc="Continuous auto focus", setting=True)
    focus_distance = Range(
        0.0,
        1.0,
        0.5,
        desc="Manual focus distance (QCamera scale, 0.0 near - 1.0 far)",
        setting=True,
    )

    def capture_entry(self):
        return {
            "filter_position": self.filter_position,
            "led_percent": int(self.led_percent),
            "exposure_ms": float(self.exposure_ms),
            "focus_distance": None if self.auto_focus else float(self.focus_distance),
        }

    def load_step_entry(self, entry):
        self.led_percent = entry.led_percent
        self.exposure_ms = entry.exposure_ms
        self.auto_focus = entry.focus_distance is None

        if entry.focus_distance is not None:
            self.focus_distance = entry.focus_distance


class FluorescenceResultRow(HasTraits):
    """One saved frame: the filter it was taken through and a file link."""

    #: Filter-wheel position the frame was captured through.
    filter_position = Int
    path = Str
    #: `path`'s file name, for the table; `path` is what open_file uses.
    file = Str
    #: Fired by the File column's link; the controller opens `path`.
    open_file = Event


class PortableDropbotFluorescenceCaptureModel(CapturePaneModel):
    """One row per filter-wheel position on the shared capture-pane state
    (see CapturePaneModel)."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE
    ROW_CLASS = FluorescenceRow
    STEP_CAPTURE_MODEL = FluorescenceStepCapture
    STEP_CELL_NAME = "fluorescence_capture"
    EXPOSURE_RANGES = FLUORESCENCE_EXPOSURE_RANGES

    #: Which span the exposure sliders cover: a narrow range makes the
    #: 0.1 ms notches easy to hit, a wide one reaches long exposures.
    exposure_range = Enum(
        DEFAULT_FLUORESCENCE_EXPOSURE_RANGE, tuple(FLUORESCENCE_EXPOSURE_RANGES)
    )

    def _rows_default(self):
        # A default never notifies, so _apply_exposure_range misses these.
        exposure_max = self.EXPOSURE_RANGES[self.exposure_range]

        return [
            FluorescenceRow(filter_position=position, exposure_max=exposure_max)
            for position in FILTER_POSITIONS
        ]

    def capture_request(self, request_id="", label=""):
        """Ticked filters as a FluorescenceCaptureRequest payload; an empty
        directory means the current experiment directory."""
        return {
            "entries": self.capture_entries(),
            "request_id": request_id,
            "label": label,
            "directory": "",
        }

    def add_result_frame(self, done):
        """Append a capture's saved frames as a new results frame and show
        it."""
        rows = [
            FluorescenceResultRow(
                filter_position=frame.filter_position,
                path=frame.path,
                file=Path(frame.path).name,
            )
            for frame in done.frames
        ]

        self.append_result_frame(rows, label=done.label)
