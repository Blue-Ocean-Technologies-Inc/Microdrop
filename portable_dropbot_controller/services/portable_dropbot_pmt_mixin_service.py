# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PMT requests (power, gain, acquire), driven from the PMT pane.

The acquire macro mirrors the vendor UI's: fluorescence LED off
(belt-and-braces — firmware dark-chambers it too) -> power on -> gain
-> acquire; the pane's Light setpoint is re-applied afterwards so the
Microdrop light state stays truthful."""
import json

from traits.api import HasTraits, Str, provides

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import PMT_GAIN_BOUNDS, PMT_UPDATED
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotPmtMixinService(HasTraits):
    id = Str("portable_dropbot_pmt_mixin_service")
    name = Str("Portable Dropbot PMT Mixin")

    def _publish_pmt(self, **payload):
        publish_message(topic=PMT_UPDATED, message=json.dumps(payload))

    def on_pmt_power_request(self, message):
        on = str(message) == "True"
        ok, actual = self._proxy_call(
            "PMT power", lambda: self.proxy.uart.pmt_power(on))
        if ok and actual is not None:
            self._publish_pmt(power=bool(actual))
        logger.info(f"Portable Dropbot PMT power --> "
                    f"{'on' if on else 'off'}: "
                    f"{'ok' if ok and actual is not None else 'FAILED'}")

    def on_pmt_set_gain_request(self, message):
        gain = min(max(PMT_GAIN_BOUNDS[0], int(float(str(message)))),
                   PMT_GAIN_BOUNDS[1])
        ok, result = self._proxy_call(
            f"PMT gain {gain}",
            lambda: self.proxy.uart.pmt_set_gain(gain))
        logger.info(f"Portable Dropbot PMT gain --> {gain}: "
                    f"{'ok' if ok and result else 'FAILED'}")

    def on_pmt_acquire_request(self, message):
        if self.proxy is None:
            return
        gain = int(json.loads(str(message)).get("gain", -1))
        logger.info(f"Portable Dropbot PMT acquire started "
                    f"(gain={'unchanged' if gain < 0 else gain})")
        uart = self.proxy.uart
        self._publish_pmt(acquiring=True)
        # One lock for the whole macro so the status poll cannot
        # interleave; the fit takes ~10 s on a full buffer.
        with self._proxy_lock:
            try:
                self._proxy_call(
                    "PMT acquire: fluorescence LED off",
                    lambda: uart.setLEDIntensity(0, fluorescence=True))
                self._proxy_call("PMT acquire: power on",
                                 lambda: uart.pmt_power(True))
                if gain >= 0:
                    self._proxy_call(f"PMT acquire: gain {gain}",
                                     lambda: uart.pmt_set_gain(gain))
                ok, packets = self._proxy_call(
                    "PMT acquire", lambda: uart.pmt_acquire())
            finally:
                # The macro forced the fluorescence LED off; put the
                # pane's Light setpoint back so state stays truthful.
                self._apply_light_intensity()
        self._publish_pmt(
            acquiring=False,
            acquired_packets=(int(packets)
                              if ok and packets is not None else None))
        logger.info(f"Portable Dropbot PMT acquire --> "
                    f"{packets if ok else 'FAILED'} packets")
