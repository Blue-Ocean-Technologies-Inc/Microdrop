# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Droplet detection: the shared DETECT_DROPLETS request answered by the
driver's own drop finder, judged against the droplet detection threshold
preference."""

# Standard library imports.
import json

# Enthought library imports.
from traits.api import HasTraits, Str, provides

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    DROPLET_DETECTION_THRESHOLD_PF,
    DROPLET_DETECTION_THRESHOLD_PF_KEY,
    DROPLETS_DETECTED,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()

SCAN_FAILED_MESSAGE = "The capacitance scan failed; see the log."


@provides(IPortableDropbotControlMixinService)
class PortableDropbotDropletDetectionMixinService(HasTraits):
    """Droplet detection through the driver's find_drops scan, which manages
    HV for the scan itself and never actuates an electrode."""

    id = Str("portable_dropbot_droplet_detection_mixin_service")
    name = Str("Portable Dropbot Droplet Detection Mixin")

    # ------------------------------------------------------------------ #
    # Requests                                                             #
    # ------------------------------------------------------------------ #

    def on_detect_droplets_request(self, message):
        """Answer DETECT_DROPLETS as the DropBot does: the requested
        channels (the session's used channels when the list is empty) that
        read at least their threshold. A refused or failed scan replies with
        the driver's reason."""
        channels = json.loads(str(message) or "[]")
        threshold_pf = float(
            app_globals.get(
                DROPLET_DETECTION_THRESHOLD_PF_KEY, DROPLET_DETECTION_THRESHOLD_PF
            )
        )

        ok, result = self._proxy_call(
            "droplet detection",
            lambda: self._find_drops(channels or None, threshold_pf),
        )

        if not ok:
            self._publish_droplets_detected(error=str(result or SCAN_FAILED_MESSAGE))

            return

        # A chunk that times out is left unmeasured rather than raised, so
        # no readings at all is a failed scan, not a dry chip.
        if not result.readings:
            self._publish_droplets_detected(error=SCAN_FAILED_MESSAGE)

            return

        if result.unmeasured:
            logger.warning(
                f"Portable Dropbot droplet scan left channels "
                f"{result.unmeasured} unmeasured"
            )

        self._publish_droplets_detected(detected_channels=result.liquid)
        logger.info(f"Portable Dropbot {result.summary()}")

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _find_drops(self, channels, threshold_pf):
        """Scan with ``threshold_pf`` as the session's default drop threshold;
        its saved per-channel overrides, a fresh baseline and the chip
        weights still apply on top, as in the vendor app."""
        session = self.proxy
        session.drop_thresholds = session.drop_thresholds.with_default(threshold_pf)

        return session.find_drops(channels=channels)

    @staticmethod
    def _publish_droplets_detected(detected_channels=(), error=""):
        """Publish the DropBot's DROPLETS_DETECTED reply shape."""
        response = {
            "success": not error,
            "detected_channels": list(detected_channels),
            "error": error,
        }

        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(response))
