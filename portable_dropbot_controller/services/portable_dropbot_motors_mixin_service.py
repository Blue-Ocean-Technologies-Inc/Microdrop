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

# Third-party imports.
from dropbot_portable import MotorBoard
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Any, Str, provides

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    CHIP_CABIN_TRAY_ONLY_FLAG,
    CHIP_CABIN_WITH_POGOS_FLAG,
    CHIP_ENGAGE_MODE_SMART,
    FILTER_POSITIONS,
    MAGNET_APPLIED,
    MAGNET_HEIGHT_MM_BOUNDS,
    MOTOR_IDS,
    PAD_ENGAGE_ACTION_ENGAGE,
    PAD_ENGAGE_ACTION_RETRACT,
    PAD_ENGAGE_CMD,
    PAD_ENGAGE_FAILURES,
    PAD_ENGAGE_MAX_STEPS,
    PAD_ENGAGE_MODE_CLASSIC,
    PAD_ENGAGE_MODE_SMART,
    PAD_ENGAGE_OVERDRIVE_UM,
    PAD_ENGAGE_PADS_MAY_BE_PRESSED,
    PAD_ENGAGE_STATUS_MOTOR_ERROR,
    PAD_ENGAGE_STATUS_OK,
    PAD_ENGAGE_STEP_UM,
    PMT_PRESET_PARK_MOTOR_FIRMWARE,
    SMART_ENGAGE_NEEDS,
    TRAY_ACTION_CODES,
    MoveTrayRequest,
    chip_lock_failed_publisher,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from ..motion_replies import (
    acknowledged_failure,
    filter_move_failure,
    mechanism_failure,
    motor_command_failure,
)
from ..motion_safety import MotionSafetyMixin

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: What the magnet mechanism request accepts — the driver's own
#: vocabulary.
_MAGNET_ACTIONS = ("engage", "disengage", "press", "release")


def parse_move_tray_request(message):
    """Read a MOVE_TRAY message into a MoveTrayRequest.

    A legacy bare direction ("in", "out", "toggle") runs the pogo pushpad
    macro, as it always did. Raises pydantic.ValidationError on anything
    else.
    """
    text = str(message).strip()

    if text.startswith("{"):
        return MoveTrayRequest.model_validate_json(text)

    return MoveTrayRequest(direction=text.lower())


@provides(IPortableDropbotControlMixinService)
class PortableDropbotMotorsMixinService(MotionSafetyMixin):
    """Mechanism macros and per-motor moves (Home All and the stops: see
    MotionSafetyMixin). Every handler republishes the motor picture, so
    the panel repaints from what the hardware reports."""

    id = Str("portable_dropbot_motors_mixin_service")
    name = Str("Portable Dropbot Motors Mixin")

    #: Held while a PAD_ENGAGE runs: a second engage is refused and a
    #: retract waits for it, as on the vendor UI's slow lane.
    _pad_engage_lock = Any()

    def __pad_engage_lock_default(self):
        return threading.Lock()

    # ------------------------------------------------------------------ #
    # Mechanism macros                                                     #
    # ------------------------------------------------------------------ #
    def on_move_tray_request(self, message):
        try:
            request = parse_move_tray_request(message)
        except ValidationError as error:
            logger.warning(f"Unknown tray request {message!r}: {error}")
            return

        direction = request.direction

        if direction == "toggle":
            direction = self._tray_toggle_direction()

            if direction is None:
                return

        flags = (
            CHIP_CABIN_WITH_POGOS_FLAG
            if request.actuate_pogos
            else CHIP_CABIN_TRAY_ONLY_FLAG
        )
        move = f"tray {direction}" + ("" if request.actuate_pogos else " (tray only)")
        logger.info(f"Portable Dropbot {move} requested")

        # The vendor UI's tray move: one CHIP_CABIN_CTRL, the pogo pushpad
        # macro unless tray-only. The firmware's own interlocks park the
        # PMT and make the magnet tray-safe first, or refuse the move.
        self._motion_call(
            move,
            lambda: self.proxy.motor.chip_cabin_ctrl(
                TRAY_ACTION_CODES[direction], flags
            ),
            MotorBoard.CHIP_CABIN_CTRL,
        )
        self._publish_status_snapshot()

    def _tray_toggle_direction(self):
        """The direction that flips the tray, or None when its state has no
        single opposite. The status pane's device picture: one click
        ejects, the next brings it back.

        The cabin state comes from the motor STATUS (byte 1), in the ctrl
        vocabulary (TRAY_ACTION_CODES: 0 in, 1 out). The magnet view
        position, moving and FAULT states are reported instead of guessed.
        """
        ok, motor_status = self._proxy_call(
            "motor status read", lambda: self.proxy.uart.GetBoardStatus("motor")
        )

        if not ok or not motor_status or len(motor_status) < 2:
            logger.warning("Tray toggle ignored: current tray position unknown.")
            return None

        state = motor_status[1]

        if state == TRAY_ACTION_CODES["in"]:
            return "out"

        if state == TRAY_ACTION_CODES["out"]:
            return "in"

        logger.warning(
            f"Tray toggle ignored: the tray reports state 0x{state:02X} (moving, "
            f"FAULT or the magnet view position); move it explicitly, or home "
            f"it: only a successful home clears a FAULT."
        )

        return None

    def _motion_call(
        self, context, call, cmd, failure=mechanism_failure, motor_id=None
    ):
        """Run one motion command and judge its reply; True when it moved.

        ``failure`` reads the reply the driver's way: ``mechanism_failure``
        judges the coordinated tray / magnet / pogo / filter commands,
        ``motor_command_failure`` a raw per-motor command. A refusal, a
        timeout or a FAULT is published as an error, like a driver call
        that raised, unless a stop was sent to ``motor_id`` meanwhile.

        Every motion skips the proxy lock (see ``_proxy_call``): the
        firmware refuses conflicting motion with BUSY on its own.
        """
        ok, reply = self._proxy_call(context, call, serialize=False)

        # A raised failure has already been reported by _proxy_call.
        if not ok:
            logger.info(f"Portable Dropbot {context} --> FAILED")
            return False

        error = failure(reply, getattr(self.proxy, "uart", None), cmd)

        if error is not None and motor_id in self._stopped_motor_ids:
            logger.info(f"Portable Dropbot {context} --> stopped ({error})")
            return False

        if error is not None:
            self._publish_error(context, error)
            return False

        logger.info(f"Portable Dropbot {context} --> ok")

        return True

    def on_move_magnet_request(self, message):
        action = str(message).strip().lower()

        if action not in _MAGNET_ACTIONS:
            logger.warning(f"Unknown magnet action: {action!r}")
            return

        logger.info(f"Portable Dropbot magnet {action} requested")
        self._motion_call(
            f"magnet {action}",
            lambda: self.proxy.move_magnet(action),
            MotorBoard.MAG_CTRL,
        )
        self._publish_status_snapshot()

    def on_protocol_set_magnet_request(self, message):
        """Protocol-driven magnet engage/disengage or absolute move.
        JSON {"on": bool, "height_mm": float}.

        "on": False disengages. "on": True with height_mm below
        MAGNET_HEIGHT_MM_BOUNDS[0] (the column's "Default" sentinel)
        runs the firmware's engage macro; any other height drives the
        magnet motor to that absolute position (mm, converted to the
        firmware's µm move units). Only a move the board confirms is
        acked: on a refusal (the magnet needs the tray in and the axis
        homed), a timeout or a FAULT the error is published instead, the
        protocol step's wait_for times out and the step fails.
        """
        payload = json.loads(str(message))
        on = bool(payload["on"])
        height_mm = float(payload["height_mm"])

        if not on:
            applied = self._motion_call(
                "protocol magnet disengage",
                lambda: self.proxy.move_magnet("disengage"),
                MotorBoard.MAG_CTRL,
            )
        elif height_mm < MAGNET_HEIGHT_MM_BOUNDS[0]:
            applied = self._motion_call(
                "protocol magnet engage",
                lambda: self.proxy.move_magnet("engage"),
                MotorBoard.MAG_CTRL,
            )
        else:
            value_um = round(height_mm * 1000)
            applied = self._motion_call(
                f"protocol magnet absolute {value_um}",
                lambda: self.proxy.uart.motorAbsoluteMove(
                    MOTOR_IDS["magnet"], value_um
                ),
                MotorBoard.MOTOR_CONTROL,
                failure=motor_command_failure,
            )

        if applied:
            publish_message(topic=MAGNET_APPLIED, message=str(int(on)))
        else:
            logger.warning(
                f"Portable Dropbot protocol magnet "
                f"{'on' if on else 'off'} ({height_mm} mm) --> no ack published"
            )

        self._publish_status_snapshot()

    def on_set_filter_request(self, message):
        position = int(str(message))

        if position not in FILTER_POSITIONS:
            logger.warning(f"Filter position out of range: {position}")
            return

        logger.info(f"Portable Dropbot filter position {position} requested")
        # The generated motor proxy waits up to 60 s for the move reply;
        # the uart facade's setFilter gives up after 5 s and reports a
        # wheel still turning as a failure.
        self._motion_call(
            f"filter {position}",
            lambda: self.proxy.motor.fluorescence_ctrl(position),
            MotorBoard.FLUORESCENCE_CTRL,
            failure=filter_move_failure,
        )
        self._publish_status_snapshot()

    def on_set_pogo_request(self, message):
        # Hardware truth (vendor test UI, HW-confirmed): 1 = press
        # (engage), 0 = release. Acts on BOTH pads as a coordinated
        # pair — no per-side mechanism command exists; a single pad
        # moves only via the raw per-motor moves/home.
        engaged = str(message) == "True"
        action = "press" if engaged else "release"
        logger.info(f"Portable Dropbot pogo {action} requested")
        self._motion_call(
            f"pogo {action}",
            lambda: self.proxy.uart.setPogo(1 if engaged else 0),
            MotorBoard.PUSHPAD_CTRL,
        )
        self._publish_status_snapshot()

    def on_lock_chip_request(self, message):
        """Chip lock IS the pogo pads pressing the chip; a topic of
        its own so panes and protocol steps say what they mean. The
        snapshot afterwards lets chip_on_pad report the result rather
        than assuming it.

        The chip engage mode preference picks how a lock presses: the
        motor board's classic press, or the signal board's smart
        PAD_ENGAGE. An unlock retracts through PAD_ENGAGE whenever a
        smart engage may hold the pads (smart mode, or the last
        PAD_ENGAGE left them down), so changing the mode in between
        never strands them pressed."""
        lock = str(message) == "True"
        smart = self.preferences.chip_engage_mode == CHIP_ENGAGE_MODE_SMART

        if lock and smart:
            self._pad_engage(PAD_ENGAGE_ACTION_ENGAGE, PAD_ENGAGE_MODE_SMART)
        elif not lock and (smart or self.pads_smart_engaged):
            self._pad_engage(PAD_ENGAGE_ACTION_RETRACT, PAD_ENGAGE_MODE_CLASSIC)
        else:
            self.on_set_pogo_request(message)

    def _pad_engage(self, action, mode):
        """Run one PAD_ENGAGE with the fixed smart descent. The board
        replies only once the pads stop (up to 45 s); the pad engage lock,
        not the proxy lock, is held until then. A failure is published on
        CHIP_LOCK_FAILED."""
        engage = action == PAD_ENGAGE_ACTION_ENGAGE
        context = "smart chip lock" if engage else "chip unlock (pad retract)"
        logger.info(f"Portable Dropbot {context} requested")

        if not self._pad_engage_lock.acquire(blocking=not engage):
            chip_lock_failed_publisher.publish(
                {
                    "action": "lock",
                    "error": "a pad engage is already in flight",
                    "pads_may_be_pressed": self.pads_smart_engaged,
                }
            )
            return

        try:
            ok, reply = self._proxy_call(
                context,
                lambda: self.proxy.sig.pad_engage(
                    action,
                    mode,
                    PAD_ENGAGE_STEP_UM,
                    PAD_ENGAGE_MAX_STEPS,
                    PAD_ENGAGE_OVERDRIVE_UM,
                ),
                serialize=False,
            )
        finally:
            self._pad_engage_lock.release()

        status = reply.status if ok and reply is not None else None

        if status == PAD_ENGAGE_STATUS_OK:
            logger.info(
                f"Portable Dropbot {context} --> ok "
                f"(steps L {reply.l_steps}, R {reply.r_steps})"
            )
            self.pads_smart_engaged = engage
        else:
            # Unlike every other failure, these may leave the pads down: the
            # indicator stays locked, so the next click is the retract.
            if status in PAD_ENGAGE_PADS_MAY_BE_PRESSED:
                self.pads_smart_engaged = True

            error = self._pad_engage_error(engage, ok, reply)
            logger.error(f"Portable Dropbot {context} --> FAILED: {error}")
            chip_lock_failed_publisher.publish(
                {
                    "action": "lock" if engage else "unlock",
                    "error": error,
                    "pads_may_be_pressed": not engage
                    or status in PAD_ENGAGE_PADS_MAY_BE_PRESSED,
                }
            )

        self._publish_status_snapshot()

    def _pad_engage_error(self, engage, ok, reply):
        """Why a PAD_ENGAGE failed: the raised error, the driver's account
        of an unanswered or refused call, or the reply's status."""

        if not ok:
            return str(reply or "Portable DropBot not connected")

        if reply is None:
            result = self.proxy.uart.last_result(PAD_ENGAGE_CMD)
            error = result.describe() if result is not None else "no reply"
        else:
            error = PAD_ENGAGE_FAILURES.get(reply.status, f"status {reply.status}")

        if engage and (reply is None or reply.status == PAD_ENGAGE_STATUS_MOTOR_ERROR):
            error = f"{error}; {SMART_ENGAGE_NEEDS}"

        return error

    # ------------------------------------------------------------------ #
    # Per-motor moves (µm — the firmware's 0.001 mm move units)           #
    # ------------------------------------------------------------------ #
    def _motor_id(self, name):
        motor_id = MOTOR_IDS.get(str(name).strip().lower())

        if motor_id is None:
            logger.warning(f"Unknown motor: {name!r}")

        return motor_id

    def on_motor_move_request(self, message):
        """JSON {"motor": name, "mode": "absolute"|"relative",
        "value": distance in µm (the firmware's 0.001 mm units)}."""
        payload = json.loads(str(message))
        motor_id = self._motor_id(payload.get("motor"))

        if motor_id is None:
            return

        mode = "relative" if payload.get("mode") == "relative" else "absolute"
        value = int(payload.get("value", 0))
        self._stopped_motor_ids.discard(motor_id)

        self._motion_call(
            f"motor {payload['motor']} {mode} move {value} um",
            lambda: self.proxy.uart.motorAction(motor_id, mode, value),
            MotorBoard.MOTOR_CONTROL,
            failure=motor_command_failure,
            motor_id=motor_id,
        )
        self._publish_motors()

    def on_motor_set_speed_request(self, message):
        """JSON {"motor": name, "value": run speed in REAL µm/s}. The
        driver converts it for motor firmware before layout 2.0, and
        refuses the write (a raised error, published) while it cannot
        confirm the board's units. Runtime only, until the motor board
        reboots; homing's leave-origin phase runs at it too (the driver's
        setMotorSpeed CAUTION). The vendor UI applies it as is and never
        restores a default, so neither does this."""
        payload = json.loads(str(message))
        motor_id = self._motor_id(payload.get("motor"))

        if motor_id is None:
            return

        speed = int(payload.get("value", 0))

        self._motion_call(
            f"motor {payload['motor']} speed {speed} um/s",
            lambda: self.proxy.uart.setMotorSpeed(motor_id, speed),
            MotorBoard.MOTOR_SPEED_SET,
            failure=motor_command_failure,
        )

    def on_motor_home_request(self, message):
        """Home one motor with a raw MOTOR_CONTROL home, except the PMT on
        motor firmware PMT_PRESET_PARK_MOTOR_FIRMWARE and newer: there it
        runs the driver's PMT_RESET, which homes and then parks at
        `_dp_park`, so it ends where the PMT pane's spot pick says homing
        ends. Older firmware parks where its raw home ends."""
        motor_id = self._motor_id(message)

        if motor_id is None:
            return

        self._stopped_motor_ids.discard(motor_id)

        if motor_id == MOTOR_IDS["pmt"] and self._motor_firmware_at_least(
            PMT_PRESET_PARK_MOTOR_FIRMWARE
        ):
            self._motion_call(
                "motor pmt home (PMT_RESET, ends at park)",
                lambda: self.proxy.motor.pmt_reset(),
                MotorBoard.PMT_RESET,
                failure=acknowledged_failure,
                motor_id=motor_id,
            )
        else:
            self._motion_call(
                f"motor {message} home",
                lambda: self.proxy.uart.motorHome(motor_id),
                MotorBoard.MOTOR_CONTROL,
                failure=motor_command_failure,
                motor_id=motor_id,
            )

        self._publish_motors()

    def on_refresh_motors_request(self, message):
        self._publish_status_snapshot()
