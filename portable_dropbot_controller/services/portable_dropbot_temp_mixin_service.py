# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Per-channel heater temperature-control requests (target, start/
stop, readings, PID tuning), driven from the temp & lighting pane."""
import json

from traits.api import HasTraits, Str, provides

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import TEMP_UPDATED
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotTempMixinService(HasTraits):
    id = Str("portable_dropbot_temp_mixin_service")
    name = Str("Portable Dropbot Temp Mixin")

    def on_temp_set_target_request(self, message):
        data = json.loads(str(message))
        channel = int(data["channel"])
        target_c = float(data["target_c"])
        ok, result = self._proxy_call(
            f"temp target ch{channel}",
            lambda: self.proxy.uart.set_temp_target(target_c, channel))
        logger.info(f"Portable Dropbot temp ch{channel} target --> "
                    f"{target_c} °C: {'ok' if ok and result else 'FAILED'}")

    def on_temp_control_request(self, message):
        data = json.loads(str(message))
        channel = int(data["channel"])
        on = bool(data["on"])
        ok, result = self._proxy_call(
            f"temp control ch{channel}",
            lambda: self.proxy.uart.set_temp_control(on, channel))
        logger.info(f"Portable Dropbot temp control ch{channel} --> "
                    f"{'on' if on else 'off'}: "
                    f"{'ok' if ok and result else 'FAILED'}")

    def on_temp_read_info_request(self, message):
        channel = int(str(message))
        ok, info = self._proxy_call(
            f"temp info ch{channel}",
            lambda: self.proxy.uart.get_temp_info(channel))
        if not ok or info is None:
            logger.warning(f"Portable Dropbot temp info ch{channel} read "
                           f"FAILED")
        if ok and info is not None:
            current_c, target_c, output_pct = info
            publish_message(topic=TEMP_UPDATED, message=json.dumps({
                "channel": channel,
                "current_c": current_c,
                "target_c": target_c,
                "output_pct": output_pct,
            }))

    def on_temp_read_pid_request(self, message):
        channel = int(str(message))
        ok, pid = self._proxy_call(
            f"temp PID ch{channel}",
            lambda: self.proxy.uart.get_temp_params(channel))
        if not ok or pid is None:
            logger.warning(f"Portable Dropbot temp PID ch{channel} read "
                           f"FAILED")
        if ok and pid is not None:
            publish_message(topic=TEMP_UPDATED, message=json.dumps(
                {"channel": channel, "pid": pid}))

    def on_temp_set_pid_request(self, message):
        data = json.loads(str(message))
        channel = int(data["channel"])
        ok, result = self._proxy_call(
            f"temp PID ch{channel}",
            lambda: self.proxy.uart.set_temp_params(
                float(data["kp"]), float(data["ki"]),
                float(data["kd"]), int(data["period_ms"]), channel))
        logger.info(f"Portable Dropbot temp ch{channel} PID --> "
                    f"kp={data['kp']} ki={data['ki']} kd={data['kd']} "
                    f"period={data['period_ms']} ms: "
                    f"{'ok' if ok and result else 'FAILED'}")
