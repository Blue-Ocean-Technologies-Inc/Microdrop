# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Buttons -> request topics for the Fluorescence Capture pane — all of it
shared with every capture pane (see capture_pane_controller.py) but the
request itself — plus the Manual controls, each applied live: a filter pick
moves the wheel, an exposure edit sets the camera's exposure, and Capture
frame grabs one frame into the experiment's captures. The LED is the status
pane's Light control.
Progress, readbacks and outcomes come back through the message handler."""

# Standard library imports.
import json
import uuid

# Enthought library imports.
from traits.api import Bool, observe

# Microdrop package imports.
from device_viewer.consts import DEVICE_VIEWER_SCREEN_CAPTURE, camera_controls_publisher
from microdrop_application.helpers import get_current_experiment_directory
from portable_dropbot_controller.consts import (
    FILTER_POSITIONS,
    FLUORESCENCE_CAPTURE_ABORT,
    MOTOR_HOME,
    SET_FILTER,
    fluorescence_capture_publisher,
    frame_description,
)
from portable_dropbot_protocol_controls.consts import FLUORESCENCE_CAPTURE_COLUMN_ID

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from .capture_pane_controller import CapturePaneController


class FluorescenceCaptureController(CapturePaneController):
    STEP_COLUMN_ID = FLUORESCENCE_CAPTURE_COLUMN_ID
    ABORT_TOPIC = FLUORESCENCE_CAPTURE_ABORT
    ROW_NOUN = "filter"

    #: True while homing resets the Filter pick to the first position — the
    #: wheel is already going there, so that change must not publish a move.
    _homing = Bool(False)

    def _publish_capture_request(self):
        request = self.model.capture_request(
            request_id=str(uuid.uuid4()), label="manual"
        )

        fluorescence_capture_publisher.publish(request)

    # ------------------------------------------------------------------ #
    # Manual controls                                                       #
    # ------------------------------------------------------------------ #

    @observe("model:manual_filter_position")
    def _move_filter(self, event):
        if not self._homing:
            publish_message(
                topic=SET_FILTER, message=str(self.model.manual_filter_position)
            )

    @observe("model:home_filter_button")
    def _home_filter(self, event):
        publish_message(topic=MOTOR_HOME, message="filter")

        # Homing ends at the first position (as the Motors pane assumes).
        self._homing = True

        try:
            self.model.manual_filter_position = FILTER_POSITIONS[0]
        finally:
            self._homing = False

    @observe("model:manual_auto_exposure")
    def _toggle_auto_exposure(self, event):
        # Turning auto off holds the exposure auto chose rather than jumping
        # to the slider (the readback then moves the slider there) — when
        # the camera reports it; otherwise the slider's exposure applies.
        hold = not event.new and self.model.auto_exposure_reported

        camera_controls_publisher.publish(
            self.model.manual_camera_request(hold_auto_exposure=hold)
        )

    @observe("model:manual_exposure_ms")
    def _set_manual_exposure(self, event):
        # The slider is inactive under auto.
        if not self.model.manual_auto_exposure:
            camera_controls_publisher.publish(self.model.manual_camera_request())

    @observe("model:manual_capture_button")
    def _capture_manual_frame(self, event):
        request_id = f"manual-{uuid.uuid4()}"
        frame_request = {
            "directory": str(get_current_experiment_directory()),
            "step_description": frame_description(
                "manual", self.model.manual_filter_position
            ),
            "show_status_message": False,
            "request_id": request_id,
        }

        self.model.manual_capture_request_id = request_id
        self.model.progress = "capturing a manual frame..."

        publish_message(
            topic=DEVICE_VIEWER_SCREEN_CAPTURE, message=json.dumps(frame_request)
        )
