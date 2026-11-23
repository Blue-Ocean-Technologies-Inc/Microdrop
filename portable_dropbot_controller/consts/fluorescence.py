# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Filter wheel and fluorescence LED constants, and the fluorescence
capture message contracts."""

# Third-party imports.
from pydantic import BaseModel, Field, field_validator

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# Local imports.
from .pmt import (
    PMT_CAPTURE_LABEL_MAX_LENGTH,
    PMT_CAPTURE_LABEL_PATTERN,
    CaptureParkOption,
)
from .topics import (
    FLUORESCENCE_CAPTURE,
    FLUORESCENCE_CAPTURE_DONE,
    FLUORESCENCE_CAPTURE_PROGRESS,
)

#: The fluorescence LED's raw 16-bit brightness ceiling (the panel
#: exposes it as a %).
FLUORESCENCE_LED_RAW_MAX = 65_535

#: Fluorescence filter wheel positions the hardware knows — 1-based; the
#: firmware faults on position 0.
FILTER_POSITIONS = (1, 2, 3, 4, 5)
#: What sits at each filter position, confirmed against the vendor UI.
FILTER_NAMES = {1: "HEX", 2: "CY5", 3: "White", 4: "FAM", 5: "Empty"}
#: Where a capture with park_motor set leaves the filter wheel.
FLUORESCENCE_PARK_FILTER = 3


def filter_label(position):
    """A filter position for display: its dye ("FAM"), or the bare
    position number when unnamed."""
    return FILTER_NAMES.get(position, str(position))


def frame_description(label, filter_position):
    """The step_description a frame request carries, naming the filter's dye;
    the device viewer names the file ``<description>_<timestamp>.png``
    (dropping the label's dots)."""
    name = FILTER_NAMES.get(filter_position, "")

    return f"flu_{label or 'manual'}_f{filter_position}_{name}".rstrip("_")


#: Fluorescence capture (#695), per filter position: LED level in % of
#: FLUORESCENCE_LED_RAW_MAX and camera exposure. The exposure bound caps at
#: what the Pi's DH Camera can do (0.3-204.7 ms, no gain); below 0.3 ms the
#: camera clamps.
FLUORESCENCE_LED_PERCENT_BOUNDS = (0, 100)
FLUORESCENCE_EXPOSURE_MS_BOUNDS = (0.1, 200.0)
FLUORESCENCE_DEFAULT_LED_PERCENT = 50
FLUORESCENCE_DEFAULT_EXPOSURE_MS = 50.0
#: Settle after the LED and a new exposure, before the frame grab — longer
#: under auto exposure, which must converge on the new filter's light.
FLUORESCENCE_SETTLE_S = 0.5
FLUORESCENCE_AUTO_EXPOSURE_SETTLE_S = 2.0
#: How long the routine waits on the frontend for the camera's controls
#: readback, and for the saved frame.
FLUORESCENCE_CAMERA_CONTROLS_TIMEOUT_S = 5.0
FLUORESCENCE_FRAME_TIMEOUT_S = 15.0
#: Abort polling slice while the routine waits on the frontend.
FLUORESCENCE_WAIT_SLICE_S = 0.05
#: A protocol step waits for its capture this long per entry (filter move up
#: to 60 s, plus the camera round trips) plus a fixed margin, before the
#: step fails as unacknowledged.
FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S = 70.0
FLUORESCENCE_STEP_TIMEOUT_MARGIN_S = 15.0

# --------------------------------------------------------------------- #
# Fluorescence capture message contracts (topic + schema, one unit)      #
# --------------------------------------------------------------------- #


class FluorescenceCaptureEntry(BaseModel):
    """One filter position to image, with its LED level, exposure and focus."""

    filter_position: int
    led_percent: int = Field(
        ge=FLUORESCENCE_LED_PERCENT_BOUNDS[0], le=FLUORESCENCE_LED_PERCENT_BOUNDS[1]
    )
    #: None = the camera's auto exposure.
    exposure_ms: float | None = Field(
        ge=FLUORESCENCE_EXPOSURE_MS_BOUNDS[0], le=FLUORESCENCE_EXPOSURE_MS_BOUNDS[1]
    )
    #: QCamera's 0.0 (near) to 1.0 (far) scale, so the contract stays
    #: camera-agnostic; None = continuous auto focus.
    focus_distance: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("filter_position")
    @classmethod
    def _filter_position_known(cls, value):
        if value not in FILTER_POSITIONS:
            raise ValueError(
                f"filter position {value} is not one of {FILTER_POSITIONS}"
            )

        return value


class FluorescenceCaptureRequest(CaptureParkOption):
    """Capture order is list order; only ticked filter positions are sent."""

    entries: list[FluorescenceCaptureEntry]
    #: Echoed on progress and done, so a protocol step waits for its own
    #: capture only; empty for pane-initiated captures.
    request_id: str = ""
    #: Filename-safe tag in the frame names (e.g. "step1.2-end", "manual").
    label: str = Field(
        default="",
        pattern=PMT_CAPTURE_LABEL_PATTERN,
        max_length=PMT_CAPTURE_LABEL_MAX_LENGTH,
    )
    #: Experiment folder the frames go under (in its captures/); empty = the
    #: current experiment directory.
    directory: str = ""


class FluorescenceStepCaptureEntry(FluorescenceCaptureEntry):
    """One filter position of a protocol step's fluorescence setup: captured
    at the step's start, its end, or both. An entry with neither tick is
    dropped on write."""

    at_start: bool = False
    at_end: bool = False


class FluorescenceStepCapture(CaptureParkOption):
    """The value of a step's fluorescence capture cell; list order is
    capture order."""

    entries: list[FluorescenceStepCaptureEntry] = []


class FluorescenceCaptureProgress(BaseModel):
    """Per-stage progress of the running capture."""

    request_id: str
    index: int
    total: int
    filter_position: int
    #: "filter" | "led" | "camera" | "frame" | "teardown"
    stage: str
    detail: str = ""


class FluorescenceCapturedFrame(BaseModel):
    """One saved frame and the filter-wheel position it was taken through."""

    filter_position: int
    path: str


class FluorescenceCaptureDone(BaseModel):
    """Outcome of a capture request; the frames saved before any failure or
    abort are still listed."""

    request_id: str
    ok: bool
    label: str = ""
    #: The captures folder the frames were saved in.
    directory: str = ""
    #: Saved PNGs, in capture order.
    frames: list[FluorescenceCapturedFrame] = []
    #: The wheel's actual resting position once teardown finishes — the last
    #: filter successfully moved to, FLUORESCENCE_PARK_FILTER when park_motor
    #: parked it there; None when nothing moved (e.g. a refusal). The pane's
    #: manual Filter pick follows this so it never shows a stale value.
    final_filter_position: int | None = None
    #: The failing stage and why, "aborted", or "busy" for a refusal.
    error: str = ""

    @field_validator("final_filter_position")
    @classmethod
    def _final_filter_position_known(cls, value):
        if value is not None and value not in FILTER_POSITIONS:
            raise ValueError(
                f"filter position {value} is not one of {FILTER_POSITIONS}"
            )

        return value


fluorescence_capture_publisher = ValidatedTopicPublisher(
    topic=FLUORESCENCE_CAPTURE, validator_class=FluorescenceCaptureRequest
)
fluorescence_capture_progress_publisher = ValidatedTopicPublisher(
    topic=FLUORESCENCE_CAPTURE_PROGRESS, validator_class=FluorescenceCaptureProgress
)
fluorescence_capture_done_publisher = ValidatedTopicPublisher(
    topic=FLUORESCENCE_CAPTURE_DONE, validator_class=FluorescenceCaptureDone
)
