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
capture (start/abort, results and "pane follows step" shared with every
capture pane — see capture_pane_controller.py), the spot refresh, the live
stream (with live avg/osr/gain updates while running), and the buffered
acquire. Spots, progress, live data and outcomes come back through the
message handler."""

# Enthought library imports.
from pyface.timer.api import CallbackTimer
from traits.api import Bool, Instance, observe

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    MOTOR_HOME,
    PMT_CAPTURE_ABORT,
    PMT_MOVE_TO_SPOT,
    PMT_SPOTS_READ,
    PMT_STREAM_STOP,
    pmt_acquire_publisher,
    pmt_capture_publisher,
    pmt_stream_start_publisher,
)
from portable_dropbot_protocol_controls.consts import PMT_CAPTURE_COLUMN_ID

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import PMT_COUNTDOWN_TICK_S
from .capture_pane_controller import CapturePaneController

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PmtCaptureController(CapturePaneController):
    STEP_COLUMN_ID = PMT_CAPTURE_COLUMN_ID
    ABORT_TOPIC = PMT_CAPTURE_ABORT
    ROW_NOUN = "spot"

    #: Ticks the status line's exposure countdown on the GUI thread.
    _countdown_timer = Instance(CallbackTimer)
    #: True while homing resets live_spot to park — the PMT is already
    #: going there, so that change must not publish a second move.
    _homing = Bool(False)

    def _publish_capture_request(self):
        pmt_capture_publisher.publish(self.model.capture_request())

    # ------------------------------------------------------------------ #
    # Spots and the exposure countdown                                      #
    # ------------------------------------------------------------------ #

    @observe("model:refresh_button")
    def _refresh_spots(self, event):
        publish_message(topic=PMT_SPOTS_READ, message="")

    @observe("model:live_spot")
    def _move_to_spot(self, event):
        if not self._homing:
            publish_message(topic=PMT_MOVE_TO_SPOT, message=str(event.new))

    @observe("model:home_pmt_button")
    def _home_pmt(self, event):
        publish_message(topic=MOTOR_HOME, message="pmt")

        # Homing ends at park.
        self._homing = True

        try:
            self.model.live_spot = 0
        finally:
            self._homing = False

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

    @observe("model:stream_avg, model:stream_osr, model:rf_ohms")
    def _push_attached_pane_settings(self, event):
        # The step cell carries these beside its entries.
        self._push_attached_step(event)

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
