# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Connection greying (inherited) plus the PMT Capture pane's signals: the
spot table, capture progress and outcome, the live stream, the detected
ADC, and the buffered acquire outcome."""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import Instance

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    PMT_ADC_QUERY,
    PMT_SPOTS_READ,
    PmtAcquireDone,
    PmtAdcUpdated,
    PmtCaptureDone,
    PmtCaptureProgress,
    PmtSpotsUpdated,
    PmtStreamUpdated,
)
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

# Microdrop utils imports.
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..models.pmt_capture_model import PortableDropbotPmtCaptureModel


class PortableDropbotPmtCaptureMessageHandler(BaseMessageHandler):
    model = Instance(PortableDropbotPmtCaptureModel)

    @timestamped_value("connected_message")
    def _on_connected_triggered(self, body):
        self.model.connected = True
        # Pull the board's spot table and detected ADC so the pane shows
        # reality rather than the "assumed" defaults.
        publish_message(topic=PMT_SPOTS_READ, message="")
        publish_message(topic=PMT_ADC_QUERY, message="")

    @timestamped_value("connected_message")
    def _on_disconnected_triggered(self, body):
        self.model.connected = False
        self.model.streaming = False
        self.model.acquiring = False
        # Force realtime mode off so the UI reflects the hardware state
        # (same as the shared base handler).
        self._on_realtime_mode_updated_triggered(
            TimestampedMessage("False", None), force_update=True
        )

    def _on_pmt_spots_updated_triggered(self, body):
        data = PmtSpotsUpdated.model_validate_json(str(body))
        self.model.merge_spots((s.slot, s.position_um) for s in data.spots)

    def _on_pmt_capture_progress_triggered(self, body):
        p = PmtCaptureProgress.model_validate_json(str(body))
        self.model.capturing = True
        self.model.progress = (
            f"Spot {p.slot} ({p.index + 1}/{p.total}): {p.stage} {p.detail}".rstrip()
        )

    def _on_pmt_capture_done_triggered(self, body):
        done = PmtCaptureDone.model_validate_json(str(body))
        self.model.capturing = False

        # A refusal carries directory="" and no results — never overwrite the
        # previous run's path or results table with that.
        if done.directory:
            self.model.results_directory = done.directory
            self.model.set_results(done)

        saved = sum(1 for r in done.results if r.csv_path)
        failed = [r for r in done.results if r.error]

        if done.error:
            self.model.progress = f"FAILED: {done.error}"
        elif done.aborted:
            self.model.progress = f"Aborted after {saved} spot(s)"
        elif done.ok:
            self.model.progress = f"{saved}/{len(done.results)} spots saved"
        else:
            self.model.progress = f"FAILED: spot {failed[0].slot} — {failed[0].error}"

    def _on_pmt_stream_updated_triggered(self, body):
        data = PmtStreamUpdated.model_validate_json(str(body))
        self.model.streaming = data.streaming

        if data.error:
            self.model.progress = f"stream error: {data.error}"

            return

        if data.samples:
            self.model.append_live(data.samples, data.packets)

    def _on_pmt_adc_updated_triggered(self, body):
        data = PmtAdcUpdated.model_validate_json(str(body))
        # full_scale == 0 means the type is unknown or the query failed —
        # keep the pane's previous conversion rather than zeroing it out.
        if data.full_scale:
            self.model.adc_full_scale = data.full_scale
        self.model.adc_display = data.error or data.name

    def _on_pmt_acquire_done_triggered(self, body):
        done = PmtAcquireDone.model_validate_json(str(body))
        self.model.acquiring = False

        if done.error:
            self.model.acquire_summary = f"FAILED: {done.error}"

            return

        mean_current = self.model.format_current(
            self.model.counts_to_amps(
                done.mean_counts, done.adc_full_scale, done.rf_ohms
            )
        )
        file_name = Path(done.csv_path).name if done.csv_path else "(not saved)"
        self.model.acquire_summary = (
            f"n={done.n_samples}  mean {done.mean_counts:.1f} counts "
            f"({mean_current})  {file_name}"
        )
