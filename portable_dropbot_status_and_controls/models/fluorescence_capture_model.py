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
position (Capture tick, LED %, auto exposure, exposure) on the shared
capture-pane state (see capture_pane_model.py), keyed by filter_position —
plus the Manual controls: the wheel and camera exposure set directly
(applied live; the LED is the status pane's Light control) and a single
frame grabbed on demand, with the camera's readback on show.
Trait mutations are safe from any thread — attach_step/detach_step are
called from the message handler's Dramatiq worker thread; only Qt object
creation needs the GUI thread (see the controller)."""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Enum,
    Event,
    Float,
    HasTraits,
    Int,
    Property,
    Range,
    Str,
)

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

#: request_ids of the Manual controls' camera requests: a plain exposure
#: change, and leaving auto exposure at the exposure auto chose.
MANUAL_CAMERA_REQUEST_ID = "manual"
MANUAL_HOLD_EXPOSURE_REQUEST_ID = "manual-hold-exposure"


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
    #: True = the camera's auto exposure; exposure_ms is then unused.
    auto_exposure = Bool(False, desc="Camera auto exposure", setting=True)

    def capture_entry(self):
        return {
            "filter_position": self.filter_position,
            "led_percent": int(self.led_percent),
            "exposure_ms": None if self.auto_exposure else float(self.exposure_ms),
            # The camera (the Pi's DH Camera) has no software focus control;
            # None leaves it on its own focus.
            "focus_distance": None,
        }

    def load_step_entry(self, entry):
        self.led_percent = entry.led_percent
        self.auto_exposure = entry.exposure_ms is None

        if entry.exposure_ms is not None:
            self.exposure_ms = entry.exposure_ms


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

    # ---- Manual controls ------------------------------------------------
    #: Chevron toggle for the Manual controls group.
    show_manual = Bool(False)
    #: Moves the wheel as soon as it changes.
    manual_filter_position = Enum(FILTER_POSITIONS)
    #: The camera settings below are applied as soon as any of them changes.
    manual_auto_exposure = Bool(False, desc="Camera auto exposure")
    manual_exposure_ms = Range(
        *FLUORESCENCE_EXPOSURE_MS_BOUNDS, FLUORESCENCE_DEFAULT_EXPOSURE_MS
    )
    #: The manual exposure slider's upper bound, from the exposure range.
    manual_exposure_max = Property(Float, observe="exposure_range")
    manual_capture_button = Button("Capture frame")
    #: request_id of the manual frame in flight; empty when none is.
    manual_capture_request_id = Str("")
    #: The camera's last readback of any exposure request (manual or a
    #: capture's) — what the camera actually took, or why it refused.
    camera_readback = Str("-", desc="The camera's last exposure readback")

    def _get_manual_exposure_max(self):
        return self.EXPOSURE_RANGES[self.exposure_range]

    def manual_camera_request(self, hold_auto_exposure=False):
        """The manual exposure as a CameraControlsRequest payload; None
        means auto, and focus always stays the camera's own.
        `hold_auto_exposure` leaves auto at the exposure auto last chose."""
        request_id = (
            MANUAL_HOLD_EXPOSURE_REQUEST_ID
            if hold_auto_exposure
            else MANUAL_CAMERA_REQUEST_ID
        )

        return {
            "request_id": request_id,
            "exposure_ms": (
                None if self.manual_auto_exposure else float(self.manual_exposure_ms)
            ),
            "hold_auto_exposure": hold_auto_exposure,
            "focus_distance": None,
        }

    def show_camera_readback(self, applied):
        """Show a CameraControlsApplied readback on the readback line."""
        if not applied.ok:
            self.camera_readback = f"FAILED: {applied.error or 'not applied'}"

            return

        exposure = (
            "" if applied.exposure_ms is None else f"{applied.exposure_ms:.1f} ms"
        )

        if applied.exposure_auto:
            exposure = f"auto ({exposure})" if exposure else "auto"

        self.camera_readback = f"exposure {exposure or 'unknown'}"

        # Leaving auto: the slider takes the exposure auto had chosen, so the
        # operator sees it and carries on from there.
        if (
            applied.request_id == MANUAL_HOLD_EXPOSURE_REQUEST_ID
            and applied.exposure_ms is not None
        ):
            low, high = FLUORESCENCE_EXPOSURE_MS_BOUNDS
            exposure_ms = min(max(applied.exposure_ms, low), high)

            self.widen_exposure_range_to(exposure_ms)
            self.manual_exposure_ms = exposure_ms

    def widen_exposure_range_to(self, exposure_ms):
        """Switch to the narrowest exposure range reaching `exposure_ms`, if
        the current one stops short of it (the slider pins at its end
        otherwise)."""
        if exposure_ms <= self.EXPOSURE_RANGES[self.exposure_range]:
            return

        self.exposure_range = min(
            (
                label
                for label, top in self.EXPOSURE_RANGES.items()
                if top >= exposure_ms
            ),
            key=self.EXPOSURE_RANGES.get,
            default=max(self.EXPOSURE_RANGES, key=self.EXPOSURE_RANGES.get),
        )

    def add_manual_frame(self, path):
        """Add a manual frame grab as its own results run."""
        row = FluorescenceResultRow(
            filter_position=self.manual_filter_position,
            path=str(path),
            file=Path(path).name,
        )

        self.append_result_frame([row], label="manual")

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
