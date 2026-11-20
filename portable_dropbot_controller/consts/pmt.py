# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PMT constants and the PMT capture, stream and acquire message
contracts."""

# Third-party imports.
from pydantic import BaseModel, Field

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# Local imports.
from .topics import (
    PMT_ACQUIRE,
    PMT_ACQUIRE_DONE,
    PMT_ADC_UPDATED,
    PMT_CAPTURE,
    PMT_CAPTURE_DONE,
    PMT_CAPTURE_PROGRESS,
    PMT_SPOTS_UPDATED,
    PMT_STREAM_START,
    PMT_STREAM_UPDATED,
)

#: PMT gain is the MCP41010 wiper position (one byte).
PMT_GAIN_BOUNDS = (0, 255)
DEFAULT_PMT_GAIN = 128

#: The PMT motor's firmware locations are 1..PMT_SPOT_SLOTS
#: (MotorBoardProxy.pmt_ctrl), and the most spots any firmware offers.
#: From motor firmware PMT_PRESET_PARK_MOTOR_FIRMWARE every location is a
#: measurement preset, spot n is location n, and park is the axis's own
#: `_dp_park` position, reached with MOTOR_CONTROL action MOTOR_ACTION_PARK.
PMT_SPOT_SLOTS = 6
PMT_PRESET_PARK_MOTOR_FIRMWARE = (1, 0, 0, 25)
MOTOR_ACTION_PARK = 6
#: Older motor firmware parks at location PMT_LEGACY_PARK_LOCATION (homing
#: ends there), so spot n is location n + PMT_LEGACY_PARK_LOCATION and it
#: offers one spot fewer.
PMT_LEGACY_PARK_LOCATION = 1
#: PMT_CTRL reply location of a PMT still moving (a fault reads
#: MECHANISM_STATE_FAULT, like the other mechanisms).
PMT_LOCATION_MOVING = 0xF2
#: Stream averaging / oversampling, the driver bench UI's defaults (avg=16
#: boxcar samples per value; osr index 6 = 64x). Measured ~23 ms per value.
PMT_STREAM_AVG = 16
PMT_STREAM_OSR = 6
#: Firmware boxcar averaging: each streamed value is the mean of N raw 1 kHz
#: samples (value rate 1000/N Hz, ~16/N packets per second).
PMT_STREAM_AVG_CHOICES = (1, 2, 4, 8, 16, 32, 64, 128)
#: ADS70x6 on-chip oversampling as the firmware's index: 0 = off, n = 2**n
#: conversions per value. A no-op on the old ADC128S052.
PMT_STREAM_OSR_CHOICES = tuple(range(8))
#: Command code of the unsolicited PMT live-stream data frames the signal
#: board sends after a PMT_STREAM request (the driver names only the request).
PMT_STREAM_DATA_CMD = 0x123F
#: How often the live stream's collected samples are published to the pane.
PMT_STREAM_PUBLISH_INTERVAL_S = 0.25
#: Abort/deadline polling slice while a capture stream is open.
PMT_STREAM_WAIT_SLICE_S = 0.05
#: Exposure per spot in seconds — the stream duration. At avg=16 the board
#: emits ~1 packet of 62 values per second, so the lower bound is set to
#: guarantee at least a few packets (a sub-second exposure would reliably
#: come back with "no stream frames received").
PMT_EXPOSURE_S_BOUNDS = (1.0, 600.0)
DEFAULT_PMT_EXPOSURE_S = 10.0
#: Counts -> volts -> amps, per the driver's PMT tab (2026-07-30 TIA rework):
#: ADS7076 16-bit, nominal 4.98 V reference (untrimmed, a known hardware
#: issue), Rf 499 kΩ. Gain is deliberately NOT folded in — the MCP41010
#: wiper changes the tube's real output current, it is not a scale factor.
PMT_ADC_FULL_SCALE = 65536
PMT_VREF_V = 4.98
PMT_RF_OHMS = 499_000.0
#: Rf is a per-board hardware value the firmware cannot report, so the pane
#: lets the operator enter the measured one.
PMT_RF_OHMS_BOUNDS = (1.0, 10_000_000.0)
#: spi_adc_diag adc_type -> (name, full-scale counts); type 0 is no ADC. Until
#: a query answers, PMT_ADC_FULL_SCALE (the ADS7076) is assumed.
PMT_ADC_TYPES = {
    1: ("ADC128S052 (12-bit)", 4096),
    2: ("ADS7076 (16-bit)", 65536),
}
#: The buffered acquire samples at a fixed 1 kHz (10240 samples, ~10.3 s).
PMT_ACQUIRE_SAMPLE_RATE_HZ = 1000
#: Capture output folder under the experiment directory.
PMT_CAPTURE_SUBDIR = "captures/pmt"
#: A capture label goes into CSV file names, so only filename-safe characters
#: (a regex character-class body) and a bounded length.
PMT_CAPTURE_LABEL_CHARS = "A-Za-z0-9._-"
PMT_CAPTURE_LABEL_PATTERN = rf"^[{PMT_CAPTURE_LABEL_CHARS}]*$"
PMT_CAPTURE_LABEL_MAX_LENGTH = 64
#: A protocol step waits for its capture for the summed exposures plus this
#: much per spot (PMT move up to 30 s, gain, stream start/stop and CSV write)
#: plus a fixed margin, before the step fails as unacknowledged.
PMT_STEP_PER_SPOT_OVERHEAD_S = 35.0
PMT_STEP_TIMEOUT_MARGIN_S = 15.0
#: A step's capture stops a running live stream first; how long to wait for
#: the stream's teardown (stream stop + power off) before refusing anyway.
PMT_STREAM_PREEMPT_TIMEOUT_S = 10.0

# --------------------------------------------------------------------- #
# PMT capture message contracts (topic + schema, one importable unit)    #
# --------------------------------------------------------------------- #


class PmtSpot(BaseModel):
    """One configured PMT motor slot and its Y-axis position."""

    slot: int = Field(ge=1, le=PMT_SPOT_SLOTS)
    position_um: int


class PmtSpotsUpdated(BaseModel):
    """The configured slots, ascending; empty when the table has none."""

    spots: list[PmtSpot]


class PmtCaptureEntry(BaseModel):
    """One spot to capture: where, at what gain, for how long."""

    slot: int = Field(ge=1, le=PMT_SPOT_SLOTS)
    gain: int = Field(ge=PMT_GAIN_BOUNDS[0], le=PMT_GAIN_BOUNDS[1])
    exposure_s: float = Field(ge=PMT_EXPOSURE_S_BOUNDS[0], le=PMT_EXPOSURE_S_BOUNDS[1])


class CaptureParkOption(BaseModel):
    """A capture request's (and step cell's) park option: when set, the
    capture's teardown moves its motor to its parking position — the PMT to
    park (spot 0: its `_dp_park` position, or location
    PMT_LEGACY_PARK_LOCATION on older motor firmware), the filter wheel to
    FLUORESCENCE_PARK_FILTER."""

    park_motor: bool = False


class PmtStreamSettings(BaseModel):
    """Stream averaging, oversampling index and the Rf used for conversion."""

    avg: int = Field(default=PMT_STREAM_AVG, ge=1, le=PMT_STREAM_AVG_CHOICES[-1])
    osr: int = Field(default=PMT_STREAM_OSR, ge=0, le=PMT_STREAM_OSR_CHOICES[-1])
    rf_ohms: float = Field(
        default=PMT_RF_OHMS, ge=PMT_RF_OHMS_BOUNDS[0], le=PMT_RF_OHMS_BOUNDS[1]
    )


class PmtCaptureRequest(PmtStreamSettings, CaptureParkOption):
    """Capture order is list order; only ticked spots are sent."""

    entries: list[PmtCaptureEntry]
    #: Echoed on PmtCaptureDone so a protocol step waits for its own capture
    #: only; empty for pane-initiated captures.
    request_id: str = ""
    #: Filename-safe tag prefixed onto the CSV names (e.g. "step1.2-end").
    label: str = Field(
        default="",
        pattern=PMT_CAPTURE_LABEL_PATTERN,
        max_length=PMT_CAPTURE_LABEL_MAX_LENGTH,
    )
    #: Stop a running live stream and capture, instead of refusing — protocol
    #: steps set it; the pane keeps the refusal.
    stop_live_stream: bool = False


class PmtStepCaptureEntry(PmtCaptureEntry):
    """One spot of a protocol step's PMT setup: captured at the step's start,
    its end, or both. An entry with neither tick is dropped on write."""

    at_start: bool = False
    at_end: bool = False


class PmtStepCapture(PmtStreamSettings, CaptureParkOption):
    """The value of a step's PMT capture cell; list order is capture order."""

    entries: list[PmtStepCaptureEntry] = []


class PmtStreamRequest(PmtStreamSettings):
    """Start, or live-update, the pane's stream at this gain."""

    gain: int = Field(ge=PMT_GAIN_BOUNDS[0], le=PMT_GAIN_BOUNDS[1])


class PmtStreamUpdated(BaseModel):
    """Stream state; while streaming, the raw counts collected since the last
    publish. `error` is set when a start was refused or failed."""

    streaming: bool
    avg: int = PMT_STREAM_AVG
    osr: int = PMT_STREAM_OSR
    samples: list[int] = []
    packets: int = 0
    error: str = ""


class PmtAdcUpdated(BaseModel):
    """The detected ADC; `full_scale` is 0 when the type is unknown or the
    query failed (`error`), and the pane keeps its previous full scale."""

    adc_type: int
    name: str
    full_scale: int
    error: str = ""


class PmtAcquireRequest(BaseModel):
    """A buffered acquire at this gain, saved with this Rf in its preamble."""

    gain: int = Field(ge=PMT_GAIN_BOUNDS[0], le=PMT_GAIN_BOUNDS[1])
    rf_ohms: float = Field(
        default=PMT_RF_OHMS, ge=PMT_RF_OHMS_BOUNDS[0], le=PMT_RF_OHMS_BOUNDS[1]
    )


class PmtAcquireDone(BaseModel):
    """Outcome of a buffered acquire; csv_path empty when nothing was saved."""

    ok: bool
    gain: int
    n_samples: int = 0
    mean_counts: float = 0.0
    sd_counts: float = 0.0
    min_counts: int = 0
    max_counts: int = 0
    packets_received: int = 0
    packets_expected: int = 0
    adc_full_scale: int = PMT_ADC_FULL_SCALE
    rf_ohms: float = PMT_RF_OHMS
    csv_path: str = ""
    error: str = ""


class PmtCaptureProgress(BaseModel):
    """Per-stage progress of the running capture."""

    index: int
    total: int
    slot: int
    #: "move" | "gain" | "stream" | "saved" | "failed"
    stage: str
    detail: str = ""
    #: On the "stream" stage, the exposure about to run, so the pane can
    #: count it down; 0 on every other stage.
    exposure_s: float = 0.0


class PmtSpotResult(BaseModel):
    """Summary of one spot's capture; csv_path empty when nothing was saved."""

    slot: int
    gain: int
    exposure_s: float
    n_samples: int
    mean_counts: float
    sd_counts: float
    min_counts: int
    max_counts: int
    csv_path: str = ""
    error: str = ""


class PmtCaptureDone(BaseModel):
    """Outcome of a capture request; `error` is request-level (refused)."""

    ok: bool
    aborted: bool
    directory: str
    results: list[PmtSpotResult]
    #: The conversion the CSVs were written with, so the pane shows the same
    #: current the files carry.
    adc_full_scale: int = PMT_ADC_FULL_SCALE
    rf_ohms: float = PMT_RF_OHMS
    #: The request's request_id and label, echoed on success and refusal alike.
    request_id: str = ""
    label: str = ""
    error: str = ""


pmt_spots_updated_publisher = ValidatedTopicPublisher(
    topic=PMT_SPOTS_UPDATED, validator_class=PmtSpotsUpdated
)
pmt_capture_publisher = ValidatedTopicPublisher(
    topic=PMT_CAPTURE, validator_class=PmtCaptureRequest
)
pmt_capture_progress_publisher = ValidatedTopicPublisher(
    topic=PMT_CAPTURE_PROGRESS, validator_class=PmtCaptureProgress
)
pmt_capture_done_publisher = ValidatedTopicPublisher(
    topic=PMT_CAPTURE_DONE, validator_class=PmtCaptureDone
)
pmt_stream_start_publisher = ValidatedTopicPublisher(
    topic=PMT_STREAM_START, validator_class=PmtStreamRequest
)
pmt_stream_updated_publisher = ValidatedTopicPublisher(
    topic=PMT_STREAM_UPDATED, validator_class=PmtStreamUpdated
)
pmt_adc_updated_publisher = ValidatedTopicPublisher(
    topic=PMT_ADC_UPDATED, validator_class=PmtAdcUpdated
)
pmt_acquire_publisher = ValidatedTopicPublisher(
    topic=PMT_ACQUIRE, validator_class=PmtAcquireRequest
)
pmt_acquire_done_publisher = ValidatedTopicPublisher(
    topic=PMT_ACQUIRE_DONE, validator_class=PmtAcquireDone
)
