# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater auto-tune (dropbot-portable 1.8.0 ``heater_tune``): start, cancel
and apply, mirroring the vendor's tuning panel and its safety rules.

A tune runs on a daemon thread (a capture lasts up to an hour, past a
Dramatiq actor's time limit) and holds the proxy lock per driver call only:
one TEMP_READ_INFO a second and the drive / OFF commands the state machine
returns (``heater_tune_capture``). It starts only with both heaters off, no
protocol step holding a heater target and the cap below the board's own
target ceiling. While it runs it owns the heaters: the listener refuses
every other heater request (HEATER_TUNE_BLOCKED_TOPICS), a protocol
temperature step fails at once, a self-test run is refused, and a
DISCONNECT becomes a cancel, so the port never closes under a driven
heater. Cancel, an E-STOP, a heater failsafe alarm on its channel, plugin
stop and a lost link all end it with the heater switched off (a lost link
leaves that to the firmware's host-silence failsafe).

The fitted model and proposed gains are only published; the frontend
writes them with HEATER_TUNE_APPLY after the operator confirms."""

# Standard library imports.
import json
import threading

# Third-party imports.
from dropbot_portable.heater_tune import Tuning, apply_tuning, capture_problem
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Any, HasTraits, Instance, Int, Str, observe, provides

# Microdrop package imports.
from portable_dropbot_self_tests.consts import SELF_TEST_RUN

# Local imports.
from ..consts import (
    DEFAULT_TEMP_CHANNEL,
    DISCONNECT,
    HEATER_TUNE_APPLY,
    HEATER_TUNE_JOIN_TIMEOUT_S,
    HEATER_TUNE_START,
    PROTOCOL_SET_TEMPERATURE,
    TEMP_CHANNEL_MAX,
    TEMP_CONTROL,
    TEMP_SET_PID,
    TEMP_SET_TARGET,
    AlarmRaised,
    HeaterTuneApplyRequest,
    HeaterTuneStartRequest,
    heater_tune_applied_publisher,
    heater_tune_done_publisher,
    heater_tune_progress_publisher,
    temperature_reached_publisher,
)
from ..heater_limits import heater_failsafe_alarms, heater_target_refusal
from ..heater_tune_capture import (
    CONNECTION_LOST_REASON,
    FITTING_PHASE,
    HeaterTuneCancel,
    capture_config,
    run_step_capture,
    smith_model_refusal,
    summarize_capture,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The requests a running tune refuses: every other heater action, the
#: self-test run, and a disconnect (which cancels the tune instead).
HEATER_TUNE_BLOCKED_TOPICS = (
    TEMP_SET_TARGET,
    TEMP_CONTROL,
    TEMP_SET_PID,
    PROTOCOL_SET_TEMPERATURE,
    HEATER_TUNE_APPLY,
    SELF_TEST_RUN,
    DISCONNECT,
)


class HeaterTuneBoard(HasTraits):
    """The board a tune drives (see ``heater_tune_capture``): one driver
    call per method, each under the controller's proxy lock, except OFF,
    which must never queue (as HV off)."""

    #: The composed Portable DropBot controller running the tune.
    controller = Any()

    def attached(self):
        return self.controller.proxy is not None

    def read(self, channel):
        """(current °C, output %) of a TEMP_READ_INFO, or None."""
        ok, info = self.controller._proxy_call(
            f"heater tune: read ch{channel}",
            lambda: self.controller.proxy.sig.temp_read_info(channel),
        )

        if not ok or info is None:
            return None

        return info.current, info.output

    def drive(self, channel, duty_pct):
        """Manual duty on ``channel`` (TEMP_HEAT_PWM); the other heater gets
        0, which leaves a regulating loop alone (it is off: start rule)."""
        duties = [0, 0]
        duties[channel] = duty_pct
        ok, accepted = self.controller._proxy_call(
            f"heater tune: drive ch{channel} at {duty_pct} %",
            lambda: self.controller.proxy.sig.temp_heat_pwm(*duties),
        )

        return bool(ok and accepted)

    def off(self, channel):
        """TEMP_START_STOP 0: ends a manual drive and a regulated loop."""
        ok, accepted = self.controller._proxy_call(
            f"heater tune: ch{channel} off",
            lambda: self.controller.proxy.sig.temp_start_stop(
                channel=channel, enable=0
            ),
            serialize=False,
        )

        return bool(ok and accepted)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotHeaterTuneMixinService(HasTraits):
    id = Str("portable_dropbot_heater_tune_mixin_service")
    name = Str("Portable Dropbot Heater Tune Mixin")

    #: The running tune's cancel event; None when idle. Set and cleared
    #: under `_heater_tune_claim`.
    _heater_tune_cancel = Instance(HeaterTuneCancel)
    #: The heater the running tune drives.
    _heater_tune_channel = Int()
    #: The running tune's daemon thread (see the module docstring).
    _heater_tune_thread = Instance(threading.Thread)
    #: Serializes the tune claim and the apply. `Instance(threading.Lock)`
    #: is rejected on the Pi's Python 3.12, hence `Any()` with a `_default`.
    _heater_tune_claim = Any()

    def __heater_tune_claim_default(self):
        return threading.Lock()

    # ------------------------------------------------------------------ #
    # Heater ownership                                                    #
    # ------------------------------------------------------------------ #

    def _exclusive_owner_reason(self, topic):
        if self._heater_tune_cancel is not None and topic in HEATER_TUNE_BLOCKED_TOPICS:
            return (
                f"heater auto-tune on ch{self._heater_tune_channel} owns the "
                f"heaters: cancel it first"
            )

        return super()._exclusive_owner_reason(topic)

    def _on_request_refused(self, topic, message, reason):
        """Answer a refused tune request (its contract replies); a refused
        protocol temperature step fails at once instead of timing out, and a
        refused DISCONNECT during a tune cancels it."""
        cancel = self._heater_tune_cancel

        if topic == HEATER_TUNE_START:
            self._refuse_heater_tune(_message_channel(message), reason)
        elif topic == HEATER_TUNE_APPLY:
            self._publish_heater_tune_applied(_message_channel(message), error=reason)
        elif cancel is not None and topic == PROTOCOL_SET_TEMPERATURE:
            temperature_reached_publisher.publish(
                {"channel": _message_channel(message), "error": reason}
            )
        elif (
            cancel is not None
            and topic == DISCONNECT
            and self.portable_dropbot_connection_active
        ):
            cancel.cancel("disconnect requested")
            logger.warning(
                "Disconnect deferred: heater auto-tune cancelled instead (heater "
                "off); disconnect again once it has finished"
            )

        super()._on_request_refused(topic, message, reason)

    def _on_motor_estop(self):
        """End a running tune on an E-STOP, as the vendor panel does."""
        super()._on_motor_estop()
        cancel = self._heater_tune_cancel

        if cancel is not None:
            cancel.cancel("E-STOP")

    def on_alarm_signal(self, message):
        """A heater failsafe alarm on the tuned heater ends the tune (the
        firmware has already switched that heater off); the protocol-step
        handling (temp mixin) still runs."""
        cancel = self._heater_tune_cancel

        if cancel is not None:
            self._cancel_heater_tune_on_failsafe(cancel, message)

        super().on_alarm_signal(message)

    def _cancel_heater_tune_on_failsafe(self, cancel, message):
        try:
            alarm_raised = AlarmRaised.model_validate_json(str(message))
        except ValidationError as error:
            logger.warning(f"Unreadable alarm payload: {error}")
            return

        for code, channel, text in heater_failsafe_alarms(alarm_raised):
            if channel in (None, self._heater_tune_channel):
                cancel.cancel(f"heater failsafe alarm {code}: {text.strip()}")
                return

    @observe("portable_dropbot_connection_active")
    def _cancel_heater_tune_on_disconnect(self, event):
        cancel = self._heater_tune_cancel

        if not event.new and cancel is not None:
            cancel.cancel(CONNECTION_LOST_REASON)

    def cleanup(self):
        """Cancel a running tune and wait for its heater OFF before the
        connection teardown."""
        cancel = self._heater_tune_cancel
        thread = self._heater_tune_thread

        if cancel is not None:
            cancel.cancel("MicroDrop is closing")

        if thread is not None and thread.is_alive():
            thread.join(timeout=HEATER_TUNE_JOIN_TIMEOUT_S)

        super().cleanup()

    # ------------------------------------------------------------------ #
    # Requests                                                            #
    # ------------------------------------------------------------------ #

    def on_heater_tune_start_request(self, message):
        """Check the start rules under the claim, then hand the capture to a
        daemon thread; its HEATER_TUNE_DONE closes every start request."""
        try:
            request = HeaterTuneStartRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._refuse_heater_tune(
                _message_channel(message), error.errors()[0]["msg"]
            )
            return

        with self._heater_tune_claim:
            reason = self._heater_tune_start_refusal(request)

            if reason:
                self._refuse_heater_tune(request.channel, reason)
                return

            cancel = HeaterTuneCancel()
            self._heater_tune_cancel = cancel
            self._heater_tune_channel = request.channel

        thread = threading.Thread(
            target=self._run_heater_tune,
            args=(request, cancel),
            daemon=True,
            name="heater-tune",
        )
        self._heater_tune_thread = thread
        thread.start()

        logger.info(
            f"Portable Dropbot heater auto-tune ch{request.channel}: step "
            f"{request.duty_pct} %, cap {request.max_temp_c:g} °C, limit "
            f"{request.max_duration_s} s"
        )

    def on_heater_tune_cancel_request(self, message):
        cancel = self._heater_tune_cancel

        if cancel is None:
            logger.info("Heater auto-tune cancel: no tune running")
            return

        cancel.cancel("cancelled by the operator")

    def on_heater_tune_apply_request(self, message):
        """Write proposed gains and this channel's Smith model row (vendor
        ``apply_tuning``), held to what the firmware accepts; refused while
        a heater is on, since a temp_smith write re-initialises both loops."""
        try:
            request = HeaterTuneApplyRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._publish_heater_tune_applied(
                _message_channel(message), error=error.errors()[0]["msg"]
            )
            return

        channel = request.channel
        tuning = Tuning(
            kp=request.kp, ki=request.ki, kd=request.kd, lam=0.0, ti=0.0, style=""
        )

        with self._heater_tune_claim:
            reason = self._heater_tune_apply_refusal(request)

            if reason:
                self._publish_heater_tune_applied(channel, error=reason)
                return

            ok, outcome = self._proxy_call(
                f"heater tune: apply ch{channel}",
                lambda: apply_tuning(
                    self.proxy.sig,
                    self.proxy.uart,
                    channel,
                    tuning,
                    request.smith_model,
                    persist=request.persist,
                    period_ms=request.period_ms,
                ),
            )

        if not ok or not isinstance(outcome, dict):
            self._publish_heater_tune_applied(
                channel, error=f"write failed: {outcome or 'not connected'}"
            )
            return

        self._publish_heater_tune_applied(
            channel,
            gains=bool(outcome["gains"]),
            smith=str(outcome["smith"] or ""),
            gains_persisted=outcome["gains_persisted"],
        )
        logger.info(
            f"Portable Dropbot heater auto-tune ch{channel} applied: kp="
            f"{request.kp} ki={request.ki} kd={request.kd}, smith "
            f"{request.smith_model}, persist={request.persist}: {outcome}"
        )

    # ------------------------------------------------------------------ #
    # Start / apply rules                                                 #
    # ------------------------------------------------------------------ #

    def _heater_tune_start_refusal(self, request):
        """Why a tune must not start (operator text), or ""; the caller
        holds `_heater_tune_claim`."""
        reason = self._heater_tune_busy_reason()

        if reason:
            return reason

        refusal = heater_target_refusal(request.max_temp_c, self._heater_max_temp_c())

        if refusal:
            return f"maximum temperature: {refusal}"

        ok, info = self._proxy_call(
            f"heater tune: read ch{request.channel}",
            lambda: self.proxy.sig.temp_read_info(request.channel),
        )
        current_c = info.current if ok and info is not None else None

        return capture_problem(capture_config(request), current_c) or ""

    def _heater_tune_apply_refusal(self, request):
        """Why proposed gains must not be written (operator text), or "";
        the caller holds `_heater_tune_claim`."""
        reason = self._heater_tune_busy_reason()

        if reason:
            return reason

        return smith_model_refusal(request.channel, request.smith_model)

    def _heater_tune_busy_reason(self):
        """A tune, a protocol step's setpoint or a heater already on: the
        vendor panel's "both heaters must be off" rule."""

        if self._heater_tune_cancel is not None:
            return "a heater auto-tune is already running"

        step_watch = self._temp_reached_cancel

        if step_watch is not None and not step_watch.is_set():
            return "a protocol step holds a heater target"

        ok, status = self._proxy_call(
            "heater tune: status", lambda: self.proxy.sig.status()
        )

        if not ok or status is None:
            return "no STATUS reply: cannot tell whether the heaters are off"

        running = [
            channel
            for channel in range(TEMP_CHANNEL_MAX + 1)
            if int(status.temp_onoff or 0) >> channel & 1
        ]

        if running:
            return f"heater ch{running[0]} is on: switch it off first"

        return ""

    # ------------------------------------------------------------------ #
    # The run                                                             #
    # ------------------------------------------------------------------ #

    def _run_heater_tune(self, request, cancel):
        """The capture, the fit and the done publish; the claim is released
        whatever happens, the heater switched off by the capture itself."""
        channel = request.channel
        board = HeaterTuneBoard(controller=self)

        try:
            capture, off_confirmed = run_step_capture(
                board,
                capture_config(request),
                cancel,
                self._publish_heater_tune_progress,
            )

            if capture.phase == "done":
                heater_tune_progress_publisher.publish(
                    {"channel": channel, "phase": FITTING_PHASE, "elapsed_s": 0.0}
                )

            outcome = summarize_capture(capture)
            outcome["off_confirmed"] = off_confirmed

            if not off_confirmed and board.attached():
                outcome["reason"] = (
                    f"{outcome['reason']}; heater OFF NOT CONFIRMED: switch it off "
                    f"by hand and check it"
                )
        except Exception as error:
            # Broad by design: any failure must still end in a done publish
            # and a released claim (the capture already tried the OFF).
            logger.exception(f"Portable Dropbot heater auto-tune ch{channel} failed")
            outcome = {
                "channel": channel,
                "ok": False,
                "reason": f"tune failed: {error}",
                "off_confirmed": False,
            }
        finally:
            with self._heater_tune_claim:
                self._heater_tune_cancel = None

        logger.info(
            f"Portable Dropbot heater auto-tune ch{channel} ended: "
            f"{'ok' if outcome['ok'] else 'no result'} ({outcome['reason']})"
        )
        heater_tune_done_publisher.publish(outcome)

    def _publish_heater_tune_progress(self, capture, current_c):
        samples = capture.samples
        elapsed_s = samples[-1][0] - capture.t0 if samples else 0.0

        heater_tune_progress_publisher.publish(
            {
                "channel": capture.cfg.channel,
                "phase": capture.phase,
                "elapsed_s": round(elapsed_s, 1),
                "current_c": current_c,
                "duty_pct": capture.cfg.duty_pct if capture.heating else 0,
            }
        )

    def _refuse_heater_tune(self, channel, reason):
        logger.warning(
            f"Portable Dropbot heater auto-tune ch{channel} refused: {reason}"
        )
        heater_tune_done_publisher.publish(
            {"channel": channel, "ok": False, "reason": reason}
        )

    def _publish_heater_tune_applied(self, channel, **outcome):
        if outcome.get("error"):
            logger.warning(
                f"Portable Dropbot heater auto-tune ch{channel} apply refused: "
                f"{outcome['error']}"
            )

        heater_tune_applied_publisher.publish({"channel": channel, **outcome})


def _message_channel(message):
    """The heater channel a (possibly invalid) request names, for its reply;
    the default channel when it names none."""
    try:
        channel = int(json.loads(str(message)).get("channel", DEFAULT_TEMP_CHANNEL))
    except (ValueError, TypeError, AttributeError):
        return DEFAULT_TEMP_CHANNEL

    return min(max(channel, 0), TEMP_CHANNEL_MAX)
