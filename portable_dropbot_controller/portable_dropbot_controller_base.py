# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json
import threading
import time
from contextlib import nullcontext
from datetime import UTC, datetime

# Third-party imports.
import dramatiq

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, Instance, Int, Str, provides

# Microdrop package imports.
from dropbot_controller.consts import CAPACITANCE_UPDATED

# Microdrop utils imports.
from microdrop_utils.dramatiq_controller_base import (
    TimestampedMessage,
    generate_class_method_dramatiq_listener_actor,
    invoke_class_method,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from .consts import (
    CHIP_DETECT_RULE_ANY_POGO,
    CHIP_DETECT_RULE_BOTH_POGOS,
    CHIP_ON_PAD_POGO_BITS,
    CHIP_ON_PAD_PRESENCE_BIT,
    CHIP_ON_PAD_SEATED_MASK,
    CONNECT_TO_PORT,
    ERROR_RAISED,
    FLUORESCENCE_LED_RAW_MAX,
    HV_STATE_HALTED_BIT,
    MOTOR_SNAPSHOT_MIN_MOTOR_FIRMWARE,
    MOTORS_UPDATED,
    PKG,
    PORTABLE_DROPBOT_CONNECTED,
    PORTABLE_DROPBOT_DISCONNECTED,
    REALTIME_MODE_UPDATED,
    REFRESH_PORTS,
    RETRY_CONNECTION,
    STATUS_FAILURE_DISCONNECT_LIMIT,
    STATUS_UPDATED,
    alarm_raised_publisher,
)
from .interfaces.i_portable_dropbot_controller_base import (
    IPortableDropbotControllerBase,
)
from .motion_replies import motor_snapshot_picture
from .preferences import PortableDropbotPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__, level="INFO")


def chip_seated(contacts, rule):
    """Whether a chip_on_pad contact mask counts as a chip on the pad.

    Every rule needs the debounced presence bit, which alone is the presence
    rule (the vendor's, and what the HV interlock uses); the both-pogos rule
    also needs both raw pogo contacts, the any-pogo rule at least one.
    """

    if rule == CHIP_DETECT_RULE_BOTH_POGOS:
        return (contacts & CHIP_ON_PAD_SEATED_MASK) == CHIP_ON_PAD_SEATED_MASK

    if rule == CHIP_DETECT_RULE_ANY_POGO:
        return bool(contacts & CHIP_ON_PAD_PRESENCE_BIT) and bool(
            contacts & CHIP_ON_PAD_POGO_BITS
        )

    return bool(contacts & CHIP_ON_PAD_PRESENCE_BIT)


@provides(IPortableDropbotControllerBase)
class PortableDropbotControllerBase(HasTraits):
    #: The driver's DropletBotSession; Any because portable_dropbot is
    #: an optional dependency (the monitor mixin imports it lazily).
    proxy = Any()
    portable_dropbot_connection_active = Bool(False)
    preferences = Instance(PortableDropbotPreferences)
    realtime_mode = Bool(False)
    voltage = Int()
    frequency = Int()
    light_intensity = Int()
    #: Illumination switch: off drives the LED to 0 while keeping the
    #: % setpoint for the next on.
    light_on = Bool(True)
    #: The last PAD_ENGAGE left the pads pressing the chip (or may have).
    #: The motor board's lpush/rpush track its own press and are not known
    #: to follow a smart engage, so the chip lock indicator reads this too.
    pads_smart_engaged = Bool(False)

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = Str(f"{PKG}_listener")
    timestamps = Instance(dict, args=())

    #: Consecutive status polls with no board answering (see
    #: _publish_status_snapshot); reset by any successful read.
    _status_failures = Int(0)

    #: Serializes the short driver calls of the monitor's poll and the
    #: Dramatiq workers, and keeps a handler's multi-call sequence (the
    #: calibration macro) whole. Correctness never needs it: the driver
    #: matches every reply to its request (cmd, cmd_idx) and serialises the
    #: commands that must not interleave (param writes, firmware upgrade)
    #: itself. So the long or urgent calls skip it (``serialize=False``):
    #: every motion, which the firmware gates with BUSY, so that a minutes-
    #: long move never parks workers on it, and HV off and the motor stops,
    #: which must never queue. RLock: handlers nest _proxy_call.
    _proxy_lock = Any()

    def __proxy_lock_default(self):
        return threading.RLock()

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        if self.proxy is not None:
            try:
                self.proxy.disconnect()
            except Exception as exc:
                logger.warning(
                    f"Error disconnecting Portable Dropbot during cleanup: {exc}"
                )
        self.proxy = None
        self.portable_dropbot_connection_active = False

    def listener_actor_routine(
        self, timestamped_message: TimestampedMessage, topic: str
    ):
        topics_tree = topic.split("/")

        if len(topics_tree) < 3:
            return

        primary_sub_topic = topics_tree[1]
        specific_sub_topic = topics_tree[-1]
        requested_method = None
        # Replies matched by request_id skip the per-topic recency filter: a
        # newer, unrelated media capture must not drop an older one that the
        # fluorescence routine is still waiting on.
        drop_stale = True

        if topic == PORTABLE_DROPBOT_CONNECTED:
            self.portable_dropbot_connection_active = True
            requested_method = f"on_{specific_sub_topic}_signal"

        elif topic == PORTABLE_DROPBOT_DISCONNECTED:
            self.portable_dropbot_connection_active = False
            requested_method = f"on_{specific_sub_topic}_signal"

        elif topic in (RETRY_CONNECTION, CONNECT_TO_PORT, REFRESH_PORTS):
            # Connection-establishing requests are exactly the ones
            # that must run while disconnected.
            requested_method = f"on_{specific_sub_topic}_request"

        elif primary_sub_topic == "requests":
            owner_reason = self._exclusive_owner_reason(topic)

            if not self.portable_dropbot_connection_active:
                logger.warning(
                    f"Request for '{specific_sub_topic}' denied: "
                    f"Portable Dropbot is disconnected."
                )
                self._on_request_refused(
                    topic, timestamped_message, "Portable Dropbot is disconnected"
                )
            elif owner_reason:
                logger.warning(
                    f"Request for '{specific_sub_topic}' refused: {owner_reason}."
                )
                self._on_request_refused(topic, timestamped_message, owner_reason)
            else:
                requested_method = f"on_{specific_sub_topic}_request"

        elif hasattr(self, f"on_{specific_sub_topic}_signal"):
            # Any other subscribed topic is another plugin's signal (the
            # camera's controls_applied / media_captured): it answers a
            # routine already under way, so it runs whatever the connection
            # state.
            requested_method = f"on_{specific_sub_topic}_signal"
            drop_stale = False

        if not requested_method:
            return

        if drop_stale:
            if (
                self.timestamps.get(topic, datetime.min)
                > timestamped_message.timestamp_dt
            ):
                logger.debug(f"Stale message on {topic} ignored.")
                return

            self.timestamps[topic] = timestamped_message.timestamp_dt

        logger.debug(f"Handling {topic} --> {requested_method}")
        err_msg = invoke_class_method(self, requested_method, timestamped_message)

        if err_msg:
            logger.error(f"Error handling topic {topic}: {err_msg}")

    def _exclusive_owner_reason(self, topic):
        """Why a routine that owns the board exclusively refuses the request
        on ``topic``; "" when nothing owns it or the topic is allowed. A mixin
        running such a routine (the self-test run) overrides this."""
        return ""

    def _on_request_refused(self, topic, message, reason):
        """Called for a request the listener refused (disconnected, or an
        exclusive owner holds the board). A mixin whose request contract
        promises a reply even then (the self-test hub's) overrides this and
        answers with ``reason``."""

    def _on_motor_estop(self):
        """Called by an E-STOP request before it goes out. A mixin whose
        routine must stop on it (the self-test run) overrides this and calls
        super()."""

    def traits_init(self):
        logger.info("Starting PortableDropbotController listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )

    # ------------------------------------------------------------------ #
    # Publish helpers                                                      #
    # ------------------------------------------------------------------ #
    def _publish_connected(self):
        publish_message(topic=PORTABLE_DROPBOT_CONNECTED, message="True")

    def _publish_disconnected(self):
        publish_message(topic=PORTABLE_DROPBOT_DISCONNECTED, message="True")

    def _publish_realtime_mode(self):
        publish_message(
            topic=REALTIME_MODE_UPDATED,
            message="True" if self.realtime_mode else "False",
        )

    def _publish_error(self, context, error):
        logger.error(f"Portable Dropbot {context} failed: {error}")
        publish_message(
            topic=ERROR_RAISED,
            message=json.dumps({"context": context, "error": str(error)}),
        )

    def _publish_alarm(self, cmd, alarms):
        """Wired into the driver's on_alarm callback: one AlarmReport per
        frame, its fields carried through so the pane can tell a clear
        (``active`` 0) from a raise. A plain string from an older driver
        travels as text only (the vendor UI's own ``hasattr(entry, "code")``
        test: every str has a ``title`` method).

        Runs on the driver's RX thread, where an exception would vanish
        unreported: a frame that fails validation is logged instead."""
        try:
            reports = []

            for alarm in alarms:
                report = {"text": str(alarm)}

                if hasattr(alarm, "code"):
                    report.update(
                        code=alarm.code,
                        title=alarm.title,
                        detail=alarm.detail,
                        active=alarm.active,
                        level=alarm.level,
                    )

                reports.append(report)

            alarm_raised_publisher.publish(
                {
                    "command": str(cmd),
                    "alarms": [str(alarm) for alarm in alarms],
                    "reports": reports,
                }
            )
        except Exception:
            # Broad by design: nothing may escape into the RX thread.
            logger.exception(f"Portable Dropbot alarm frame {cmd} not published")

    # ------------------------------------------------------------------ #
    # Guarded driver access                                                #
    # ------------------------------------------------------------------ #
    def _proxy_call(self, context, call, serialize=True):
        """Run one driver call; an OS/serial-level failure means the
        device is gone (disconnect + rescan), anything else is
        reported as an error signal rather than a traceback. Returns
        (ok, result); a failed call's result is the exception it raised,
        so a caller can relay the driver's reason.

        ``serialize=False`` skips the proxy lock (see ``_proxy_lock``): for
        motion, HV off and the stops."""
        if self.proxy is None:
            logger.warning(f"Portable Dropbot not connected: ignoring {context}.")
            return False, None

        try:
            with self._proxy_lock if serialize else nullcontext():
                return True, call()
        except OSError as error:
            logger.warning(f"Portable Dropbot vanished during {context}: {error}")
            self.on_disconnected_signal("")
            return False, error
        except Exception as error:
            self._publish_error(context, error)
            return False, error

    # ------------------------------------------------------------------ #
    # Status / motor snapshots                                             #
    # ------------------------------------------------------------------ #
    def _publish_status_snapshot(self):
        """One driver status read fans out to both panes: the signal
        board's readings (HV, temps, chip detect...) on STATUS_UPDATED
        and the motor picture on MOTORS_UPDATED. The driver already
        reports engineering units (°C, %RH, V), so they pass through
        as-is."""
        ok, status = self._proxy_call("status read", lambda: self.proxy.status)
        if not ok or not isinstance(status, dict) or not status:
            # The driver answers {} when neither board replied — a
            # timeout per command, seconds per poll. A link that dead
            # for several polls in a row is a disconnect, not a blip:
            # declare it and let the scanner take over, instead of
            # polling a silent board forever behind an "Active" label.
            self._status_failures += 1
            if self._status_failures >= STATUS_FAILURE_DISCONNECT_LIMIT:
                logger.warning(
                    f"Portable Dropbot status unanswered "
                    f"{self._status_failures} polls in a row — "
                    f"treating the link as lost."
                )
                self._status_failures = 0
                self._publish_disconnected()
                self.on_disconnected_signal("")
            return
        self._status_failures = 0
        self._publish_capacitance(status.get("signal", {}))
        signal = dict(status.get("signal", {}))

        if "chip_on_pad" in signal:
            # A contact mask, not a flag: the chip-detect preference decides
            # whether partial pogo contact (3 or 5) counts as a chip. The raw
            # mask rides along so the pane can say which pogo pads touch it.
            signal["chip_pad_contacts"] = int(signal["chip_on_pad"])
            signal["chip_on_pad"] = chip_seated(
                signal["chip_pad_contacts"], self.preferences.chip_detect_rule
            )

        if "hv_state" in signal:
            # hv_state bit3: the firmware latched a halt (HALT_STATUS).
            signal["halted"] = bool(int(signal["hv_state"]) & HV_STATE_HALTED_BIT)

        signal.update(self._status_tail_readouts())
        publish_message(topic=STATUS_UPDATED, message=json.dumps(signal))
        self._publish_motors(mechanisms=status.get("motor", {}), poll=False)

    def _status_tail_readouts(self):
        """The STATUS tail the driver captured from the last status reply:
        the board's HV setpoint, fault_flags and their names. MCU firmware
        before 1.0.1.30 sends no tail, so the driver's last_status_tail is
        None there and this answers {}."""
        tail = getattr(getattr(self.proxy, "uart", None), "last_status_tail", None)

        if not isinstance(tail, dict):
            return {}

        return {
            name: tail[name]
            for name in ("hv_setpoint", "fault_flags", "faults")
            if name in tail
        }

    @staticmethod
    def _publish_capacitance(board_signal):
        """Publish the chip capacitance on the DropBot's CAPACITANCE_UPDATED,
        so the device viewer's volume estimate and calibration, the volume
        threshold column and the run log work on the portable too.

        ``chip_cap`` is the actuated electrodes' summed capacitance, the
        quantity the DropBot reports; ``board_signal`` is the driver's
        status dict, already in pF and V.
        """
        chip_cap = board_signal.get("chip_cap")

        if chip_cap is None:
            return

        publish_message(
            topic=CAPACITANCE_UPDATED,
            message=json.dumps(
                {
                    "capacitance": f"{chip_cap:.4g} pF",
                    "voltage": f"{board_signal.get('hv_vol', 0.0):.3g} V",
                    # The status reply carries no instrument clock: a host
                    # monotonic microsecond counter, wrapping like the
                    # DropBot's uint32 one, keeps the run log's rollover
                    # correction honest.
                    "instrument_time_us": int(time.monotonic() * 1e6) % 2**32,
                    "reception_time": datetime.now(UTC).timestamp(),
                }
            ),
        )

    def _publish_motors(self, mechanisms=None, poll=True):
        """Publish the motor picture on MOTORS_UPDATED.

        Motor firmware that answers MOTOR_SNAPSHOT gives every position,
        homed flag, moving flag and fault in one frame, answered at once
        even mid-move, so both callers take it. Older firmware falls back:
        ``poll=False`` (the periodic status snapshot) publishes the driver's
        CACHED positions instead of querying the board (the per-motor
        position round-trips plus the homed query cost more than the whole
        monitor interval); every motor action and the manual refresh poll
        fresh."""
        picture = self._read_motor_snapshot()

        if picture is not None:
            positions, homed = picture["positions"], picture["homed"]
        elif poll:
            # Both driver calls answer {motor_name: value} dicts — or
            # False/None when the motor board is not answering, which
            # the isinstance guard treats as "nothing to report".
            _ok, positions = self._proxy_call(
                "motor positions", lambda: self.proxy.uart.getMotorPositions()
            )
            _ok, homed = self._proxy_call(
                "motor homed flags", lambda: self.proxy.uart.queryMotorHomed()
            )
        else:
            # No serial traffic: the driver caches every position it
            # learns from action results and position replies.
            _ok, positions = self._proxy_call(
                "cached motor positions", lambda: self.proxy.uart.motors.positions()
            )
            homed = None

        payload = {
            "positions": (dict(positions) if isinstance(positions, dict) else {}),
            "homed": dict(homed) if isinstance(homed, dict) else {},
            "mechanisms": mechanisms if mechanisms is not None else {},
            "pads_smart_engaged": self.pads_smart_engaged,
            # Snapshot firmware only: {motor: bool} and {motor: [fault names]}.
            "moving": picture["moving"] if picture is not None else {},
            "faults": picture["faults"] if picture is not None else {},
        }
        publish_message(topic=MOTORS_UPDATED, message=json.dumps(payload))

    def _read_motor_snapshot(self):
        """The motor picture of one MOTOR_SNAPSHOT (see
        ``motor_snapshot_picture``), or None when the motor firmware
        predates it or the board gave no usable answer."""

        if not self._motor_firmware_at_least(MOTOR_SNAPSHOT_MIN_MOTOR_FIRMWARE):
            return None

        ok, reply = self._proxy_call(
            "motor snapshot", lambda: self.proxy.motor.motor_snapshot()
        )

        return motor_snapshot_picture(reply) if ok else None

    def _apply_actuation(self):
        """Push the current HV setpoints (both Int) to the device."""
        logger.debug(
            f"Applying actuation setpoints: {self.voltage} V, {self.frequency} Hz"
        )
        self._proxy_call(
            "set actuation",
            lambda: self.proxy.set_actuation(int(self.voltage), int(self.frequency)),
        )

    def _apply_light_intensity(self):
        """Push the light brightness to the device: the % setpoint
        scaled to the fluorescence LED's 16-bit range — that is the
        LED that actually lights this instrument — or 0 while the
        light is switched off."""
        raw = (
            round(int(self.light_intensity) * FLUORESCENCE_LED_RAW_MAX / 100)
            if self.light_on
            else 0
        )
        logger.debug(
            f"Applying light intensity: {self.light_intensity} % "
            f"(raw {raw}, light "
            f"{'on' if self.light_on else 'off'})"
        )
        # The generated proxy sends the 16-bit value as is; the uart
        # facade's setLEDIntensity clamps its argument to 0-100 and halves
        # it, which left this lamp at 50/65535 at "100 %".
        self._proxy_call(
            "set light intensity", lambda: self.proxy.sig.fluorescence_ctrl(raw)
        )

    # ------------------------------------------------------------------ #
    # Shared-signal handlers                                               #
    # ------------------------------------------------------------------ #
    def on_connected_signal(self, message):
        self.portable_dropbot_connection_active = True

    def on_disconnected_signal(self, message):
        self.portable_dropbot_connection_active = False
        if self.proxy is not None:
            try:
                self.proxy.disconnect()
            except Exception:
                pass
            self.proxy = None
