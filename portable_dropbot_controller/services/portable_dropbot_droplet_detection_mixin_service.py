# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Droplet detection: a per-channel capacitance baseline measured on a dry
chip, then the shared DETECT_DROPLETS request answered by comparing a fresh
scan against it (the driver's calibrate_baseline / detect_drops)."""

# Standard library imports.
import json

# Enthought library imports.
from traits.api import Bool, HasTraits, Str, observe, provides

# Microdrop package imports.
from electrode_controller.consts import ElectrodeChannelsRequest
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    DROPLET_DETECTION_THRESHOLD_PF,
    DROPLET_SCAN_SWITCH_TIME_MS,
    DROPLETS_DETECTED,
    LAST_CHANNEL_STATES_REQUESTED_KEY,
    CalibrateDropletBaselineRequest,
    droplet_baseline_updated_publisher,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()

#: The 120-channel board's scan is a self-test with its own HV setup; a
#: larger board measures with the current HV settings, so HV must be on.
SELF_POWERED_SCAN_MAX_CHANNELS = 120

SCAN_FAILED_MESSAGE = "The capacitance scan failed; see the log."


@provides(IPortableDropbotControlMixinService)
class PortableDropbotDropletDetectionMixinService(HasTraits):
    """Droplet detection against a dry-chip baseline. The baseline lives on
    the driver session, so a reconnect discards it."""

    id = Str("portable_dropbot_droplet_detection_mixin_service")
    name = Str("Portable Dropbot Droplet Detection Mixin")

    #: Whether the current session holds a droplet baseline.
    _has_droplet_baseline = Bool(False)

    @observe("proxy")
    def _forget_droplet_baseline(self, event):
        """A new (or no) driver session has no baseline."""
        self._has_droplet_baseline = False

    # ------------------------------------------------------------------ #
    # Requests                                                             #
    # ------------------------------------------------------------------ #

    def on_calibrate_droplet_baseline_request(self, message):
        """Measure every channel, with the chip dry, as the reference that
        droplet detection compares against."""
        request = CalibrateDropletBaselineRequest.model_validate_json(str(message))
        ok, baseline = self._run_channel_scan(
            "droplet baseline",
            lambda: self.proxy.calibrate_baseline(
                switch_time_ms=request.switch_time_ms
            ),
        )

        if not ok or not baseline:
            logger.warning("Portable Dropbot droplet baseline FAILED")
            droplet_baseline_updated_publisher.publish({"error": SCAN_FAILED_MESSAGE})

            return

        self._has_droplet_baseline = True
        droplet_baseline_updated_publisher.publish({"channels": len(baseline)})
        logger.info(f"Portable Dropbot droplet baseline: {len(baseline)} channels")

    def on_detect_droplets_request(self, message):
        """Answer DETECT_DROPLETS as the DropBot does: the requested
        channels (every channel when the list is empty) that read at least
        DROPLET_DETECTION_THRESHOLD_PF above their baseline."""

        if not self._has_droplet_baseline:
            self._publish_droplets_detected(
                error="No droplet baseline: calibrate it from the status pane "
                "with the chip dry."
            )

            return

        channels = json.loads(str(message) or "[]")
        ok, drops = self._run_channel_scan(
            "droplet detection",
            lambda: self.proxy.detect_drops(
                channels=channels or None,
                threshold_pf=DROPLET_DETECTION_THRESHOLD_PF,
                switch_time_ms=DROPLET_SCAN_SWITCH_TIME_MS,
            ),
        )

        # An empty result means the scan returned nothing, not "no liquid":
        # every scanned channel gets an entry either way.
        if not ok or not drops:
            self._publish_droplets_detected(error=SCAN_FAILED_MESSAGE)

            return

        detected = sorted(channel for channel, has_drop in drops.items() if has_drop)
        self._publish_droplets_detected(detected_channels=detected)
        logger.info(f"Portable Dropbot droplets detected on channels {detected}")

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _run_channel_scan(self, context, scan):
        """Run a full-channel capacitance scan and return ``(ok, result)``.
        The scan drives HV and switches every channel itself, so the user's
        HV, setpoints and actuated electrodes are put back afterwards."""
        with self._proxy_lock:
            if self._board_channels() > SELF_POWERED_SCAN_MAX_CHANNELS:
                self._proxy_call("HV enable", lambda: self.proxy.sig.hv_enable(1, 0))

            result = self._proxy_call(context, scan)
            self._restore_actuation_after_scan()

        return result

    def _restore_actuation_after_scan(self):
        """Put HV, the V/F setpoints and the electrodes back as realtime
        mode had them before the scan."""
        self._apply_actuation()

        if not self.realtime_mode:
            self._proxy_call("clear channels", lambda: self.proxy.clear_channels())
            self._proxy_call("HV disable", lambda: self.proxy.sig.hv_enable(0, 0))

            return

        channels = self._last_requested_channels()
        self._proxy_call("HV enable", lambda: self.proxy.sig.hv_enable(1, 0))
        self._proxy_call(
            "restore electrodes", lambda: self.proxy.actuate_channels(channels)
        )

    def _last_requested_channels(self):
        """The channels of the last electrode state change applied, or none."""
        message = app_globals.get(LAST_CHANNEL_STATES_REQUESTED_KEY)

        if not message:
            return []

        request = ElectrodeChannelsRequest.model_validate_json(
            message, context={"max_channels": self._board_channels()}
        )

        return [int(channel) for channel in request.channels]

    @staticmethod
    def _publish_droplets_detected(detected_channels=(), error=""):
        """Publish the DropBot's DROPLETS_DETECTED reply shape."""
        response = {
            "success": not error,
            "detected_channels": list(detected_channels),
            "error": error,
        }

        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(response))
