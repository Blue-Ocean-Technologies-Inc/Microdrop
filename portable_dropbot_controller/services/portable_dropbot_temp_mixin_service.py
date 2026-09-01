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
stop, readings, PID tuning), driven from the temp & lighting pane, plus
the protocol-step setpoint (drives a channel and watches for it to
settle within tolerance)."""

import json
import threading
import time

from traits.api import HasTraits, Instance, Str, provides

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import (
    TEMP_REACHED_POLL_INTERVAL_S,
    TEMP_REACHED_TIMEOUT_S,
    TEMP_UPDATED,
    TEMPERATURE_REACHED,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotTempMixinService(HasTraits):
    id = Str("portable_dropbot_temp_mixin_service")
    name = Str("Portable Dropbot Temp Mixin")

    #: Current protocol-step reached-watcher (see
    #: on_protocol_set_temperature_request); a new request cancels it.
    _temp_reached_watcher = Instance(threading.Thread)
    #: Set to stop the watcher this call armed, either because a newer
    #: request superseded it or because the watch gave up.
    _temp_reached_cancel = Instance(threading.Event)

    def on_temp_set_target_request(self, message):
        data = json.loads(str(message))
        channel = int(data["channel"])
        target_c = float(data["target_c"])
        ok, result = self._proxy_call(
            f"temp target ch{channel}",
            lambda: self.proxy.uart.set_temp_target(target_c, channel),
        )
        logger.info(
            f"Portable Dropbot temp ch{channel} target --> "
            f"{target_c} °C: {'ok' if ok and result else 'FAILED'}"
        )

    def on_temp_control_request(self, message):
        data = json.loads(str(message))
        channel = int(data["channel"])
        on = bool(data["on"])
        if not on:
            # Control off (the pane, or a protocol ending) also ends any
            # reached-watch still polling toward a step's setpoint.
            self._cancel_temp_reached_watcher()
        ok, result = self._proxy_call(
            f"temp control ch{channel}",
            lambda: self.proxy.uart.set_temp_control(on, channel),
        )
        logger.info(
            f"Portable Dropbot temp control ch{channel} --> "
            f"{'on' if on else 'off'}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    def on_temp_read_info_request(self, message):
        channel = int(str(message))
        ok, info = self._proxy_call(
            f"temp info ch{channel}", lambda: self.proxy.uart.get_temp_info(channel)
        )
        if not ok or info is None:
            logger.warning(f"Portable Dropbot temp info ch{channel} read FAILED")
        if ok and info is not None:
            current_c, target_c, output_pct = info
            publish_message(
                topic=TEMP_UPDATED,
                message=json.dumps(
                    {
                        "channel": channel,
                        "current_c": current_c,
                        "target_c": target_c,
                        "output_pct": output_pct,
                    }
                ),
            )

    def on_temp_read_pid_request(self, message):
        channel = int(str(message))
        ok, pid = self._proxy_call(
            f"temp PID ch{channel}", lambda: self.proxy.uart.get_temp_params(channel)
        )
        if not ok or pid is None:
            logger.warning(f"Portable Dropbot temp PID ch{channel} read FAILED")
        if ok and pid is not None:
            publish_message(
                topic=TEMP_UPDATED, message=json.dumps({"channel": channel, "pid": pid})
            )

    def on_temp_set_pid_request(self, message):
        data = json.loads(str(message))
        channel = int(data["channel"])
        ok, result = self._proxy_call(
            f"temp PID ch{channel}",
            lambda: self.proxy.uart.set_temp_params(
                float(data["kp"]),
                float(data["ki"]),
                float(data["kd"]),
                int(data["period_ms"]),
                channel,
            ),
        )
        logger.info(
            f"Portable Dropbot temp ch{channel} PID --> "
            f"kp={data['kp']} ki={data['ki']} kd={data['kd']} "
            f"period={data['period_ms']} ms: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    def on_protocol_set_temperature_request(self, message):
        """Protocol-step setpoint: set the target, turn control on, then
        arm a background watcher that polls the channel and acks
        TEMPERATURE_REACHED once the reading settles within tolerance.
        A new request cancels any watcher still running from a previous
        step."""
        data = json.loads(str(message))
        channel = int(data["channel"])
        target_c = float(data["target_c"])
        tolerance_c = float(data["tolerance_c"])

        ok_target, result_target = self._proxy_call(
            f"protocol temp target ch{channel}",
            lambda: self.proxy.uart.set_temp_target(target_c, channel),
        )
        ok_control, result_control = self._proxy_call(
            f"protocol temp control ch{channel}",
            lambda: self.proxy.uart.set_temp_control(True, channel),
        )
        if not (ok_target and result_target and ok_control and result_control):
            logger.warning(
                f"Portable Dropbot protocol temp ch{channel} "
                f"setpoint --> {target_c} °C FAILED: not "
                f"arming reached-watcher"
            )
            return

        self._cancel_temp_reached_watcher()
        cancel_event = threading.Event()
        self._temp_reached_cancel = cancel_event
        self._temp_reached_watcher = threading.Thread(
            target=self._watch_temp_reached,
            args=(channel, target_c, tolerance_c, cancel_event),
            daemon=True,
        )
        self._temp_reached_watcher.start()

    def _cancel_temp_reached_watcher(self):
        """Stop a still-running watcher from a previous protocol-step
        request; a no-op if none is running."""
        if self._temp_reached_cancel is not None:
            self._temp_reached_cancel.set()

    def _watch_temp_reached(self, channel, target_c, tolerance_c, cancel_event):
        """Poll ch{channel} until it settles within tolerance of target_c,
        then publish TEMPERATURE_REACHED — or give up silently (warning
        log, no ack) after TEMP_REACHED_TIMEOUT_S. Each reading is also
        republished on TEMP_UPDATED so the temp & lighting pane keeps
        tracking a step-driven channel. Stops early if cancelled or the
        proxy disconnects."""
        deadline = time.monotonic() + TEMP_REACHED_TIMEOUT_S
        while not cancel_event.is_set() and self.proxy is not None:
            if time.monotonic() >= deadline:
                logger.warning(
                    f"Portable Dropbot protocol temp ch{channel} "
                    f"reached-watch timed out after "
                    f"{TEMP_REACHED_TIMEOUT_S}s: giving up."
                )
                return
            ok, info = self._proxy_call(
                f"protocol temp info ch{channel}",
                lambda: self.proxy.uart.get_temp_info(channel),
            )
            if ok and info is not None:
                current_c, read_target_c, output_pct = info
                publish_message(
                    topic=TEMP_UPDATED,
                    message=json.dumps(
                        {
                            "channel": channel,
                            "current_c": current_c,
                            "target_c": read_target_c,
                            "output_pct": output_pct,
                        }
                    ),
                )
                if abs(current_c - target_c) <= tolerance_c:
                    publish_message(
                        topic=TEMPERATURE_REACHED,
                        message=json.dumps(
                            {
                                "channel": channel,
                                "current_c": current_c,
                            }
                        ),
                    )
                    return
            cancel_event.wait(TEMP_REACHED_POLL_INTERVAL_S)
