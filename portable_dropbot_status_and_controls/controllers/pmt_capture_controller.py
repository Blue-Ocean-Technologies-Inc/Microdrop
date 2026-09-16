# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Buttons -> request topics for the PMT Capture pane: the multi-spot
capture, the live stream (with live avg/osr/gain updates while running),
and the buffered acquire. Spots, progress, live data and outcomes come back
through the message handler.

"Pane follows step" (#601 increment 2): while a step is attached and no
protocol is running, every table/settings edit publishes the step's
pmt_capture cell over protocol_tree_set_cell_publisher — the model's
loading_step flag suppresses this while attach_step/detach_step are
themselves applying a loaded cell or the manual snapshot."""

# Enthought library imports.
from pyface.timer.api import CallbackTimer
from traits.api import Instance, observe
from traitsui.api import Controller

# Microdrop package imports.
from pluggable_protocol_tree.consts import protocol_tree_set_cell_publisher
from portable_dropbot_controller.consts import (
    PMT_CAPTURE_ABORT,
    PMT_SPOTS_READ,
    PMT_STREAM_STOP,
    pmt_acquire_publisher,
    pmt_capture_publisher,
    pmt_stream_start_publisher,
)
from portable_dropbot_protocol_controls.consts import PMT_CAPTURE_COLUMN_ID

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.file_handler import open_file

# Local imports.
from ..consts import PMT_COUNTDOWN_TICK_S

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PmtCaptureController(Controller):
    #: Ticks the status line's exposure countdown on the GUI thread.
    _countdown_timer = Instance(CallbackTimer)

    # ------------------------------------------------------------------ #
    # Multi-spot capture                                                    #
    # ------------------------------------------------------------------ #

    @observe("model:start_button")
    def _start_capture(self, event):
        entries = self.model.capture_entries()
        if not entries:
            self.model.progress = "No spot ticked"
            return

        self.model.capturing = True
        self.model.progress = "starting..."
        logger.info(f"Requested PMT capture of {len(entries)} spot(s)")
        pmt_capture_publisher.publish(self.model.capture_request())

    @observe("model:abort_button")
    def _abort_capture(self, event):
        publish_message(topic=PMT_CAPTURE_ABORT, message="")

    @observe("model:refresh_button")
    def _refresh_spots(self, event):
        publish_message(topic=PMT_SPOTS_READ, message="")

    # dispatch="ui": the deadline is set by the message handler on a Dramatiq
    # worker thread, and a Qt timer created or started there never fires —
    # that thread has no event loop.
    @observe("model:exposure_deadline", dispatch="ui")
    def _run_exposure_countdown(self, event):
        # Tick only while a spot's exposure is counting down.
        if event.new:
            self._countdown_timer.start()
        else:
            self._countdown_timer.stop()

    def __countdown_timer_default(self):
        return CallbackTimer(
            interval=PMT_COUNTDOWN_TICK_S, callback=self.model.update_countdown
        )

    # ------------------------------------------------------------------ #
    # Pane follows step                                                     #
    # ------------------------------------------------------------------ #

    @observe("model:rows:items:gain")
    @observe("model:rows:items:exposure_s")
    @observe("model:rows:items:at_start")
    @observe("model:rows:items:at_end")
    @observe("model:rows:items")
    @observe("model:rows")
    @observe("model:stream_avg")
    @observe("model:stream_osr")
    @observe("model:rf_ohms")
    def _push_attached_step(self, event):
        # Not attached, mid-run (the tree refuses set-cell then anyway), or
        # attach_step/detach_step applying a loaded cell or the manual
        # snapshot — none of those are an operator edit to push.
        if (
            not self.model.attached_step_id
            or self.model.protocol_running
            or self.model.loading_step
        ):
            return

        value = self.model.step_cell_value()
        self.model.record_pushed_value(value)
        protocol_tree_set_cell_publisher.publish(
            step_id=self.model.attached_step_id,
            col_id=PMT_CAPTURE_COLUMN_ID,
            value=value,
        )

    # ------------------------------------------------------------------ #
    # Results                                                              #
    # ------------------------------------------------------------------ #

    @observe("model:previous_frame_button")
    def _show_previous_frame(self, event):
        self.model.show_previous_frame()

    @observe("model:next_frame_button")
    def _show_next_frame(self, event):
        self.model.show_next_frame()

    @observe("model:result_frames:items:rows:items:open_file")
    def _open_result_file(self, event):
        path = event.object.csv_path

        try:
            open_file(path)
        except OSError as error:
            logger.error(f"Could not open PMT capture file {path}: {error}")

    # ------------------------------------------------------------------ #
    # Live stream                                                          #
    # ------------------------------------------------------------------ #

    @observe("model:stream_start_button")
    def _start_stream(self, event):
        self.model.clear_live()
        logger.info(f"Requested PMT live stream at gain {self.model.gain}")
        pmt_stream_start_publisher.publish(self.model.stream_request())

    @observe("model:stream_stop_button")
    def _stop_stream(self, event):
        publish_message(topic=PMT_STREAM_STOP, message="")

    @observe("model:stream_avg, model:stream_osr, model:gain")
    def _update_running_stream(self, event):
        # Sent again while streaming, the firmware treats a start as a
        # parameter update — no restart, no sample gap.
        if self.model.streaming:
            pmt_stream_start_publisher.publish(self.model.stream_request())

    # ------------------------------------------------------------------ #
    # Buffered acquire                                                     #
    # ------------------------------------------------------------------ #

    @observe("model:acquire_button")
    def _acquire(self, event):
        self.model.acquiring = True
        self.model.acquire_summary = "acquiring (~20 s)..."
        logger.info(f"Requested PMT buffered acquire at gain {self.model.gain}")
        pmt_acquire_publisher.publish(self.model.acquire_request())
