# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state for the PMT Capture pane: the multi-spot capture table
(capture tick, gain, exposure) in capture order, the live stream + buffered
acquire settings shared by both, and the per-spot results of the last
capture. Mutated only on the GUI thread."""

# Standard library imports.
import time
from datetime import datetime
from pathlib import Path

# Third-party imports.
import numpy as np

# Enthought library imports.
from traits.api import (
    Array,
    Bool,
    Button,
    Enum,
    Event,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Range,
    Str,
)

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    DEFAULT_PMT_EXPOSURE_S,
    DEFAULT_PMT_GAIN,
    PMT_ADC_FULL_SCALE,
    PMT_EXPOSURE_S_BOUNDS,
    PMT_GAIN_BOUNDS,
    PMT_RF_OHMS,
    PMT_RF_OHMS_BOUNDS,
    PMT_STREAM_AVG,
    PMT_STREAM_AVG_CHOICES,
    PMT_STREAM_OSR,
    PMT_STREAM_OSR_CHOICES,
    PMT_VREF_V,
)
from template_status_and_controls.base_model import BaseStatusModel

# Microdrop utils imports.
from microdrop_utils.ureg_helpers import ureg

# Local imports.
from ..consts import PMT_LIVE_WINDOW_SAMPLES, PORTABLE_DROPBOT_IMAGE


class PmtSpotRow(HasTraits):
    """One PMT motor slot as a table row."""

    #: Motor slot, 1-based — the identity of the row.
    slot = Int
    #: The slot's position on the PMT Y axis, from the board.
    position_um = Int
    #: Read-only ID column: "Spot 3 · 24.50 mm".
    label = Property(Str, observe="slot, position_um")
    #: The spot the running capture is on; the table highlights its row.
    active = Bool(False)
    capture = Bool(True, desc="Capture this spot")
    gain = Range(
        *PMT_GAIN_BOUNDS, DEFAULT_PMT_GAIN, desc="PMT gain (MCP41010 wiper position)"
    )
    exposure_s = Range(
        *PMT_EXPOSURE_S_BOUNDS,
        DEFAULT_PMT_EXPOSURE_S,
        desc="Stream duration for this spot, seconds",
    )

    def _get_label(self):
        return f"Spot {self.slot} · {self.position_um / 1000:.2f} mm"


class PmtSpotResultRow(HasTraits):
    """One completed spot's outcome, converted with the CAPTURE'S own
    adc_full_scale/rf_ohms (not whatever the pane's settings are now)."""

    slot = Int
    gain = Int
    exposure_s = Float
    n_samples = Int
    mean_counts = Float
    sd_counts = Float
    mean_voltage = Str
    mean_current = Str
    #: Full path of the spot's CSV; `file` is its name for the table.
    csv_path = Str
    file = Str
    error = Str
    #: Fired by the File column's link; the controller opens `csv_path`.
    open_file = Event


class PmtResultFrame(HasTraits):
    """One capture run's per-spot results: a page of the Results table."""

    #: Time the run's results arrived, "HH:MM:SS".
    taken = Str
    rows = List(Instance(PmtSpotResultRow))


class PortableDropbotPmtCaptureModel(BaseStatusModel):
    """Spot rows in capture order, the running capture's state, the live
    stream + buffered acquire (sharing gain/avg/osr/rf_ohms with capture),
    and the last capture's per-spot results."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- Chevron-collapsed group toggles ------------------------------
    show_results = Bool(False)
    show_live = Bool(True)
    show_conversion = Bool(False)

    # ---- Spot table -----------------------------------------------------
    #: Table rows; list order is capture order.
    rows = List(Instance(PmtSpotRow))
    selected_row = Instance(PmtSpotRow)
    #: True between Start and the backend's done message.
    capturing = Bool(False)
    progress = Str("-", desc="Current stage / last outcome")
    #: Monotonic time the current spot's exposure ends; 0 when nothing is
    #: counting down. The controller ticks update_countdown() meanwhile.
    exposure_deadline = Float(0.0)
    #: The stage text the countdown is appended to.
    _countdown_prefix = Str()
    results_directory = Str("", desc="Folder the last capture wrote to")

    start_button = Button("Start capture")
    abort_button = Button("Abort")
    refresh_button = Button("Refresh spots")

    # ---- Results ----------------------------------------------------------
    #: Every capture run's results since the pane opened, oldest first; the
    #: Results table pages through them one run at a time.
    result_frames = List(Instance(PmtResultFrame))
    #: Index of the frame on show; -1 before the first capture.
    frame_index = Int(-1)
    #: The shown frame's rows, in capture order.
    results = Property(
        List(Instance(PmtSpotResultRow)), observe="result_frames.items, frame_index"
    )
    #: "Run 2 / 3 · 14:05:09", or a hint before the first capture.
    frame_label = Property(Str, observe="result_frames.items, frame_index")
    #: Top-level flags so the arrows' enabled_when reacts.
    has_previous_frame = Property(Bool, observe="frame_index")
    has_next_frame = Property(Bool, observe="result_frames.items, frame_index")
    previous_frame_button = Button("Previous run")
    next_frame_button = Button("Next run")

    # ---- Shared live-stream / acquire settings --------------------------
    #: PMT gain (MCP41010 wiper), used by both the live stream and acquire.
    gain = Range(*PMT_GAIN_BOUNDS, DEFAULT_PMT_GAIN)
    stream_avg = Enum(
        PMT_STREAM_AVG,
        PMT_STREAM_AVG_CHOICES,
        desc="Stream boxcar averaging (samples per value)",
    )
    stream_osr = Enum(
        PMT_STREAM_OSR,
        PMT_STREAM_OSR_CHOICES,
        desc="ADS70x6 on-chip oversampling index; 0 = off",
    )
    rf_ohms = Range(
        *PMT_RF_OHMS_BOUNDS,
        PMT_RF_OHMS,
        desc="Transimpedance feedback resistor (Ω), for counts -> current",
    )
    adc_full_scale = Int(
        PMT_ADC_FULL_SCALE, desc="Full-scale ADC counts for counts -> volts"
    )
    adc_display = Str("ADS7076 (16-bit), assumed", desc="Detected PMT ADC")
    #: Nominal, untrimmed — see conversion_note.
    vref_display = Str()
    conversion_note = Str(
        "Gain is not folded into the current — it already changes the "
        "tube's own output current. Vref is a nominal, untrimmed value "
        "(known hardware limitation), not a calibrated one."
    )

    # ---- Run state --------------------------------------------------------
    streaming = Bool(False)
    acquiring = Bool(False)
    #: Top-level (not nested) so enabled_when reacts to it — TraitsUI's
    #: enabled_when ignores changes nested inside a Property's dependencies.
    busy = Property(Bool, observe="capturing, streaming, acquiring")

    # ---- Live stream --------------------------------------------------
    stream_start_button = Button("Start live")
    stream_stop_button = Button("Stop live")
    acquire_button = Button("Buffered acquire")
    live_units = Enum("Current", "Volts", "Counts")
    #: Rolling window of raw counts, trimmed to PMT_LIVE_WINDOW_SAMPLES.
    live_counts = Array
    live_packets = Int(0)
    live_values = Property(observe="live_counts, live_units, adc_full_scale, rf_ohms")
    live_axis_label = Property(observe="live_units")
    live_summary = Property(
        Str, observe="live_counts, live_units, live_packets, adc_full_scale, rf_ohms"
    )
    acquire_summary = Str("-", desc="Last buffered acquire outcome")

    def _live_counts_default(self):
        return np.array([], dtype=int)

    def _vref_display_default(self):
        return f"{PMT_VREF_V:.2f} V (nominal, untrimmed)"

    def _get_busy(self):
        return self.capturing or self.streaming or self.acquiring

    def _get_results(self):
        if 0 <= self.frame_index < len(self.result_frames):
            return self.result_frames[self.frame_index].rows

        return []

    def _get_frame_label(self):
        if not self.result_frames:
            return "no captures yet"

        frame = self.result_frames[self.frame_index]

        return f"Run {self.frame_index + 1} / {len(self.result_frames)} · {frame.taken}"

    def _get_has_previous_frame(self):
        return self.frame_index > 0

    def _get_has_next_frame(self):
        return self.frame_index < len(self.result_frames) - 1

    def _get_live_axis_label(self):
        return {"Current": "A", "Volts": "V", "Counts": "counts"}[self.live_units]

    def _get_live_values(self):
        if self.live_units == "Counts":
            return self.live_counts

        if self.live_units == "Volts":
            return self.counts_to_volts(self.live_counts, self.adc_full_scale)

        return self.counts_to_amps(self.live_counts, self.adc_full_scale, self.rf_ohms)

    def _get_live_summary(self):
        if self.live_counts.size == 0:
            return "no data"

        values = self.live_values
        packets = f"{self.live_packets} packets"

        if self.live_units == "Counts":
            return (
                f"mean {values.mean():.1f}  min {values.min():.0f}  "
                f"max {values.max():.0f} counts  ({packets})"
            )

        if self.live_units == "Volts":
            return (
                f"mean {values.mean():.4g} V  min {values.min():.4g} V  "
                f"max {values.max():.4g} V  ({packets})"
            )

        return (
            f"mean {self.format_quantity(values.mean(), 'A')}  "
            f"min {self.format_quantity(values.min(), 'A')}  "
            f"max {self.format_quantity(values.max(), 'A')}  ({packets})"
        )

    def append_live(self, samples, packets):
        """Extend the rolling live-stream window with a batch of raw counts,
        trimmed to PMT_LIVE_WINDOW_SAMPLES."""
        combined = np.concatenate([self.live_counts, np.asarray(samples, dtype=int)])
        self.live_counts = combined[-PMT_LIVE_WINDOW_SAMPLES:]
        self.live_packets += packets

    def clear_live(self):
        """Reset the live-stream window, e.g. on a fresh Start Live."""
        self.live_counts = np.array([], dtype=int)
        self.live_packets = 0

    @staticmethod
    def counts_to_volts(counts, full_scale):
        """Raw ADC counts -> volts at the (nominal, untrimmed) reference."""
        if full_scale <= 0:
            return 0.0 * np.asarray(counts, dtype=float)

        return np.asarray(counts, dtype=float) * PMT_VREF_V / full_scale

    @staticmethod
    def counts_to_amps(counts, full_scale, rf_ohms):
        """Raw ADC counts -> TIA input current (amps).

        Gain is deliberately NOT folded in: the MCP41010 wiper changes the
        tube's own output current upstream of the TIA, so it is already
        reflected in the counts — dividing it back out here would fabricate
        a correction with no calibration basis.
        """

        if rf_ohms <= 0:
            return 0.0 * np.asarray(counts, dtype=float)

        volts = PortableDropbotPmtCaptureModel.counts_to_volts(counts, full_scale)

        return volts / rf_ohms

    @staticmethod
    def format_quantity(value, unit):
        """A value in `unit` (e.g. "A", "V") with a compact prefix (µA, mV)."""
        return f"{ureg.Quantity(float(value), unit).to_compact():.4g~P}"

    def merge_spots(self, spots):
        """Adopt a fresh (slot, position_um) list without losing settings.

        Rows are keyed by slot: survivors keep their tick, gain, exposure and
        place in the order (position refreshed), new slots append in slot
        order with defaults, vanished slots drop.
        """
        incoming = dict(spots)
        kept = [row for row in self.rows if row.slot in incoming]
        for row in kept:
            row.position_um = incoming[row.slot]
        known = {row.slot for row in kept}
        new = [
            PmtSpotRow(slot=slot, position_um=position)
            for slot, position in sorted(incoming.items())
            if slot not in known
        ]
        self.rows = kept + new

    def start_exposure_countdown(self, exposure_s, now=None):
        """Count the current progress line down over `exposure_s` seconds."""
        now = time.monotonic() if now is None else now
        self._countdown_prefix = self.progress
        self.exposure_deadline = now + exposure_s

        self.update_countdown(now)

    def update_countdown(self, now=None):
        """Refresh the progress line's remaining time, to a tenth of a second."""
        if not self.exposure_deadline:
            return

        now = time.monotonic() if now is None else now
        remaining = max(self.exposure_deadline - now, 0.0)
        self.progress = f"{self._countdown_prefix} · {remaining:.1f} s left"

    def stop_countdown(self):
        self.exposure_deadline = 0.0

    def mark_active_spot(self, slot):
        """Highlight the row of the spot being captured; 0 clears it."""
        for row in self.rows:
            row.active = row.slot == slot

    def capture_entries(self):
        """The ticked rows, in table order, as PmtCaptureEntry payloads."""
        return [
            {
                "slot": row.slot,
                "gain": int(row.gain),
                "exposure_s": float(row.exposure_s),
            }
            for row in self.rows
            if row.capture
        ]

    def capture_request(self):
        """Ticked spots plus the stream settings the capture converts with."""
        return {
            "entries": self.capture_entries(),
            "avg": int(self.stream_avg),
            "osr": int(self.stream_osr),
            "rf_ohms": float(self.rf_ohms),
        }

    def stream_request(self):
        """Start, or live-update, the pane's stream at the current settings."""
        return {
            "gain": int(self.gain),
            "avg": int(self.stream_avg),
            "osr": int(self.stream_osr),
            "rf_ohms": float(self.rf_ohms),
        }

    def acquire_request(self):
        """A buffered acquire at the current gain and Rf."""
        return {"gain": int(self.gain), "rf_ohms": float(self.rf_ohms)}

    def add_result_frame(self, done):
        """Append a capture's per-spot results as a new frame and show it.

        Converted with the capture's OWN adc_full_scale/rf_ohms — the pane's
        current settings may have changed since the capture ran.
        """
        rows = []

        for result in done.results:
            mean_voltage = mean_current = "-"

            if not result.error:
                mean_voltage = self.format_quantity(
                    self.counts_to_volts(result.mean_counts, done.adc_full_scale),
                    "V",
                )
                mean_current = self.format_quantity(
                    self.counts_to_amps(
                        result.mean_counts, done.adc_full_scale, done.rf_ohms
                    ),
                    "A",
                )

            rows.append(
                PmtSpotResultRow(
                    slot=result.slot,
                    gain=result.gain,
                    exposure_s=result.exposure_s,
                    n_samples=result.n_samples,
                    mean_counts=result.mean_counts,
                    sd_counts=result.sd_counts,
                    mean_voltage=mean_voltage,
                    mean_current=mean_current,
                    csv_path=result.csv_path,
                    file=Path(result.csv_path).name if result.csv_path else "",
                    error=result.error,
                )
            )

        frame = PmtResultFrame(taken=datetime.now().strftime("%H:%M:%S"), rows=rows)
        self.result_frames.append(frame)
        self.frame_index = len(self.result_frames) - 1

    def show_previous_frame(self):
        self.frame_index = max(self.frame_index - 1, 0)

    def show_next_frame(self):
        self.frame_index = min(self.frame_index + 1, len(self.result_frames) - 1)
