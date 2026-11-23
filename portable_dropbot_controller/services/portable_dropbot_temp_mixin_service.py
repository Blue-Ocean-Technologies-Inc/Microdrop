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
settle within tolerance). Requests are checked against what MCU 1.0.1.31
accepts before they are sent, and a heater failsafe alarm on a protocol's
loop fails the protocol: the step still waiting on it, or, once the
setpoint was reached, the run holding it."""

# Standard library imports.
import json
import threading
import time

# Third-party imports.
from dropbot_portable.param_layout import HEAT_FS_DEFAULT
from pydantic import ValidationError

# Enthought library imports.
from traits.api import HasTraits, Instance, Int, Str, provides

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    TEMP_REACHED_POLL_INTERVAL_S,
    TEMP_REACHED_TIMEOUT_S,
    TEMP_UPDATED,
    AlarmRaised,
    ProtocolSetTemperatureRequest,
    TempSetPidRequest,
    TempSetTargetRequest,
    temperature_reached_publisher,
)
from ..heater_limits import heater_failsafe_alarms, heater_target_refusal
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotTempMixinService(HasTraits):
    id = Str("portable_dropbot_temp_mixin_service")
    name = Str("Portable Dropbot Temp Mixin")

    #: Current protocol-step watcher (see on_protocol_set_temperature_request):
    #: it waits for the setpoint, then holds the loop armed until heater-off,
    #: a newer request, or a failure.
    _temp_reached_watcher = Instance(threading.Thread)
    #: Set to stop the watcher this call armed, either because a newer
    #: request or a heater-off superseded it, a failsafe alarm failed its
    #: step, or the watch gave up.
    _temp_reached_cancel = Instance(threading.Event)
    #: The heater loop the current watcher waits on.
    _temp_reached_channel = Int()
    #: Set by the current watcher once its setpoint was reached: the step
    #: has its ack, and the loop is held for the rest of the run.
    _temp_holding = Instance(threading.Event, ())
    #: A failsafe alarm that hit the held loop: the watcher republishes it
    #: as the step error until the run turns the heater off, so the next
    #: step boundary fails the protocol even if a pause dropped one publish.
    _temp_hold_fault = Str()

    # ------------------------------------------------------------------ #
    # Pane requests                                                        #
    # ------------------------------------------------------------------ #
    def on_temp_set_target_request(self, message):
        try:
            request = TempSetTargetRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._publish_error("temp target", error.errors()[0]["msg"])
            return

        refusal = heater_target_refusal(request.target_c, self._heater_max_temp_c())

        if refusal:
            self._publish_error(f"temp target ch{request.channel}", refusal)
            return

        ok, result = self._proxy_call(
            f"temp target ch{request.channel}",
            lambda: self.proxy.uart.set_temp_target(request.target_c, request.channel),
        )

        logger.info(
            f"Portable Dropbot temp ch{request.channel} target --> "
            f"{request.target_c} °C: {'ok' if ok and result else 'FAILED'}"
        )

    def on_temp_control_request(self, message):
        data = json.loads(str(message))
        channel = int(data["channel"])
        on = bool(data["on"])

        if not on and channel == self._temp_reached_channel:
            # Control off (the pane, or a protocol ending) also ends the
            # watch on a step's setpoint: still polling toward it, or
            # holding it.
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
            return

        self._publish_temp_info(channel, info)

    def on_temp_read_pid_request(self, message):
        """Read a loop's PID tuning through the generated proxy, as the
        vendor UI does: it decodes the uint16 fields the firmware stores
        (the uart helper still reads them as int16, so a period above
        32767 ms came back negative)."""
        channel = int(str(message))
        ok, pid = self._proxy_call(
            f"temp PID ch{channel}", lambda: self.proxy.sig.temp_read_params(channel)
        )

        if not ok or pid is None:
            logger.warning(f"Portable Dropbot temp PID ch{channel} read FAILED")
            return

        publish_message(
            topic=TEMP_UPDATED,
            message=json.dumps({"channel": channel, "pid": pid._asdict()}),
        )

    def on_temp_set_pid_request(self, message):
        """Write a loop's PID tuning; a set the firmware would refuse (gain
        above 100, Kp = Ki = 0) is answered with its reason instead. It goes
        through the generated proxy, as the vendor UI's does: uint16 fields
        and rounded gains (the uart helper packs int16, which cannot carry a
        period above 32767 ms, and truncates 0.29 to 0.28)."""
        data = json.loads(str(message))

        try:
            request = TempSetPidRequest.model_validate(data)
        except ValidationError as error:
            reason = error.errors()[0]["msg"]
            logger.warning(f"Portable Dropbot temp PID not applied: {reason}")
            self._publish_pid_outcome(data.get("channel"), error=reason)
            return

        ok, result = self._proxy_call(
            f"temp PID ch{request.channel}",
            lambda: self.proxy.sig.temp_set_params(
                channel=request.channel,
                kp=request.kp,
                ki=request.ki,
                kd=request.kd,
                period_ms=request.period_ms,
            ),
        )
        applied = bool(ok and result)

        self._publish_pid_outcome(request.channel, applied=applied)
        logger.info(
            f"Portable Dropbot temp ch{request.channel} PID --> "
            f"kp={request.kp} ki={request.ki} kd={request.kd} "
            f"period={request.period_ms} ms: {'ok' if applied else 'FAILED'}"
        )

    def _publish_pid_outcome(self, channel, applied=False, error=""):
        publish_message(
            topic=TEMP_UPDATED,
            message=json.dumps(
                {"channel": channel, "pid_applied": applied, "pid_error": error}
            ),
        )

    def _publish_temp_info(self, channel, info):
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

    def _heater_max_temp_c(self):
        """The board's heater failsafe max temperature (heat_fs max_temp_c),
        or the firmware default when the board does not serve one."""
        ok, failsafe = self._proxy_call(
            "heater failsafe read", lambda: self.proxy.uart.heater_failsafe()
        )

        if not ok or failsafe is None or failsafe[2] is None:
            return HEAT_FS_DEFAULT[2]

        return failsafe[2]

    # ------------------------------------------------------------------ #
    # Protocol-step setpoint                                               #
    # ------------------------------------------------------------------ #
    def on_protocol_set_temperature_request(self, message):
        """Protocol-step setpoint: set the target, turn control on, then
        arm a background watcher that polls the channel and acks
        TEMPERATURE_REACHED once the reading settles within tolerance.
        A new request cancels any watcher still running from a previous
        step; a refused setpoint fails the step at once."""
        self._cancel_temp_reached_watcher()

        try:
            request = ProtocolSetTemperatureRequest.model_validate_json(str(message))
        except ValidationError as error:
            data = json.loads(str(message))
            self._fail_temperature_step(
                data.get("channel", 0), error.errors()[0]["msg"]
            )
            return

        channel, target_c = request.channel, request.target_c
        refusal = heater_target_refusal(target_c, self._heater_max_temp_c())

        if refusal:
            self._fail_temperature_step(channel, refusal)
            return

        ok_target, result_target = self._proxy_call(
            f"protocol temp target ch{channel}",
            lambda: self.proxy.uart.set_temp_target(target_c, channel),
        )
        ok_control, result_control = self._proxy_call(
            f"protocol temp control ch{channel}",
            lambda: self.proxy.uart.set_temp_control(True, channel),
        )

        if not (ok_target and result_target and ok_control and result_control):
            self._fail_temperature_step(
                channel, f"ch{channel} setpoint {target_c} °C was not accepted"
            )
            return

        cancel_event = threading.Event()
        self._temp_reached_cancel = cancel_event
        self._temp_reached_channel = channel
        self._temp_holding = threading.Event()
        self._temp_hold_fault = ""
        self._temp_reached_watcher = threading.Thread(
            target=self._watch_temp_reached,
            args=(channel, target_c, request.tolerance_c, cancel_event),
            daemon=True,
        )
        self._temp_reached_watcher.start()

    def on_alarm_signal(self, message):
        """A heater failsafe alarm switches its loop off until restarted.
        On a protocol's loop it fails the protocol: the step waiting on the
        setpoint fails at once instead of timing out, and a loop already
        holding its setpoint fails the run at its next step boundary."""
        cancel_event = self._temp_reached_cancel

        if cancel_event is None or cancel_event.is_set():
            return

        try:
            alarm_raised = AlarmRaised.model_validate_json(str(message))
        except ValidationError as error:
            logger.warning(f"Unreadable alarm payload: {error}")
            return

        channel = self._temp_reached_channel

        for code, alarm_channel, text in heater_failsafe_alarms(alarm_raised):
            if alarm_channel not in (None, channel):
                continue

            reason = f"heater failsafe alarm {code}: {text.strip()}"

            if self._temp_holding.is_set():
                # The holding watcher republishes it until heater-off.
                self._temp_hold_fault = f"{reason} (while holding the setpoint)"
                self._fail_temperature_step(channel, self._temp_hold_fault)
            else:
                cancel_event.set()
                self._fail_temperature_step(channel, reason)

            return

    def _fail_temperature_step(self, channel, reason):
        logger.warning(f"Portable Dropbot protocol temp ch{channel} FAILED: {reason}")
        temperature_reached_publisher.publish({"channel": channel, "error": reason})

    def _cancel_temp_reached_watcher(self):
        """Stop a still-running watcher from a previous protocol-step
        request; a no-op if none is running."""
        if self._temp_reached_cancel is not None:
            self._temp_reached_cancel.set()

    def _watch_temp_reached(self, channel, target_c, tolerance_c, cancel_event):
        """Wait for ch{channel}'s setpoint, then hold it armed (see
        _hold_temp_setpoint) until cancelled."""
        holding = self._temp_holding

        if self._wait_temp_reached(
            channel, target_c, tolerance_c, cancel_event, holding
        ):
            self._hold_temp_setpoint(channel, cancel_event)

    def _hold_temp_setpoint(self, channel, cancel_event):
        """The step has its ack, but the loop stays the run's until heater-off
        or a newer setpoint: a failsafe alarm meanwhile (on_alarm_signal) is
        republished every poll interval as the step error, which the
        temperature column raises at the next step boundary."""

        while not cancel_event.wait(TEMP_REACHED_POLL_INTERVAL_S):
            fault = self._temp_hold_fault

            if fault and self._temp_reached_cancel is cancel_event:
                self._fail_temperature_step(channel, fault)

    def _wait_temp_reached(self, channel, target_c, tolerance_c, cancel_event, holding):
        """Poll ch{channel} until it settles within tolerance of target_c,
        then set ``holding`` and publish TEMPERATURE_REACHED — or fail the
        step after TEMP_REACHED_TIMEOUT_S. Each reading is also republished
        on TEMP_UPDATED so the temp & lighting pane keeps tracking a
        step-driven channel. Stops early if cancelled or the proxy
        disconnects. Returns whether the setpoint was reached."""
        deadline = time.monotonic() + TEMP_REACHED_TIMEOUT_S

        while not cancel_event.is_set() and self.proxy is not None:
            if time.monotonic() >= deadline:
                cancel_event.set()
                self._fail_temperature_step(
                    channel,
                    f"not within {tolerance_c} °C of {target_c} °C after "
                    f"{TEMP_REACHED_TIMEOUT_S:g} s",
                )

                return False

            ok, info = self._proxy_call(
                f"protocol temp info ch{channel}",
                lambda: self.proxy.uart.get_temp_info(channel),
            )

            if ok and info is not None:
                self._publish_temp_info(channel, info)
                current_c = info[0]

                if abs(current_c - target_c) <= tolerance_c:
                    # A failsafe alarm may have failed the step meanwhile.
                    if cancel_event.is_set():
                        return False

                    # Holding before the ack: an alarm from here on is a
                    # hold-phase fault, never lost between the two.
                    holding.set()
                    temperature_reached_publisher.publish(
                        {"channel": channel, "current_c": current_c}
                    )

                    return True

            cancel_event.wait(TEMP_REACHED_POLL_INTERVAL_S)

        return False
