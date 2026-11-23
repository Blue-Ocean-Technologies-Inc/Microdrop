# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Home All and the motor stops for the motors mixin, the vendor UI's way.

The stops follow the vendor's vocabulary: "Stop motion" is one axis's
MOTOR_CONTROL STOP, "EMERGENCY STOP — MOTORS" one MOTOR_ESTOP for every
axis. Both skip the proxy lock, so neither waits behind the move it stops.

Home All is the vendor's host plan (``dropbot_portable.ui.motion_controls``,
``MechanismController.home_all_plan``), never the board's HW_RESET, which
the vendor runs only after a flash: the battery expansion of the motor
board's home-sequence table, one unit at a time. A unit's HOME is its
coordinated reset (PMT_RESET, MAG_RESET, TRAY_RESET, FLU_RESET, one
PUSHPAD_RESET for both pads; the PMT, tray and filter resets end at their
``_dp_park``), and a PARK row, or a home + park of the magnet or a pad, adds
a MOTOR_CONTROL park. An empty or unreadable table runs the compiled
default (PMT, magnet, pads, tray, filter), as the firmware does.

Each step is judged like the vendor's job outcome: no reply, a refusal, or
an error status the answer carries (``ui.device_status``, the vendor's one
decoder of those). As there, a failed step does not cancel the later ones;
an E-STOP does (the vendor's queued steps are answered as aborted by the
firmware; this host plan stops sending them).
"""

# Standard library imports.
import threading

# Third-party imports.
from dropbot_portable import MotorBoard, param_layout
from dropbot_portable.commands import Frame
from dropbot_portable.ui.device_status import device_status_error

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, Instance

# Local imports.
from .consts import (
    MAG_RESET_CMD,
    MOTOR_ACTION_PARK,
    MOTOR_ESTOP_CMD,
    MOTOR_IDS,
    TRAY_RESET_CMD,
)
from .motion_replies import describe_last_result, motor_command_failure

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Motor id -> the plan step that homes it; the pads share one reset.
_UNIT_RESETS = {
    0: "tray_reset",
    1: "pmt_reset",
    2: "mag_reset",
    3: "flu_reset",
    4: "pushpad_reset",
    5: "pushpad_reset",
}
#: Motor ids whose reset already ends at its _dp_park (tray, PMT, filter).
_PARKING_RESETS = (0, 1, 3)
#: Units a home + park parks with an extra MOTOR_CONTROL park step.
_PARKED_AFTER_RESET = (
    param_layout.HS_UNIT_MAGNET
    | param_layout.HS_UNIT_PAD_L
    | param_layout.HS_UNIT_PAD_R
)
_PARK_STEP_PREFIX = "park_"
#: Reset step -> its command id, for the driver's account of a failed one.
_RESET_COMMANDS = {
    "pmt_reset": MotorBoard.PMT_RESET,
    "mag_reset": MAG_RESET_CMD,
    "pushpad_reset": MotorBoard.PUSHPAD_RESET,
    "tray_reset": TRAY_RESET_CMD,
    "flu_reset": MotorBoard.FLU_RESET,
}
#: The vendor's per-connection uart marker: TRAY_RESET answered RESP_UNKNOWN.
_TRAY_RESET_UNSUPPORTED = "_tray_reset_unsupported"


def home_seq_rows(reply):
    """The board's home-sequence table from a GET_PARAMS(_dp_home_seq)
    reply; None (firmware that does not serve it) reads as the empty table,
    which runs the compiled default."""

    if reply is None:
        return list(param_layout.HOME_SEQ_DEFAULT)

    return param_layout.unpack_home_seq(bytes(reply.value))


def home_all_plan(rows):
    """The host steps of the vendor's ``home_all_plan``, in its order."""

    if param_layout.home_seq_is_empty(rows):
        rows = param_layout.HOME_SEQ_DEFAULT

    plan = []

    for bit, action in param_layout.home_seq_battery_steps(rows):
        motor_id = param_layout.HS_UNITS[bit][1]
        reset = _UNIT_RESETS[motor_id]
        homes = action in (param_layout.HS_ACT_HOME_PARK, param_layout.HS_ACT_HOME)

        if homes and reset not in plan:
            plan.append(reset)

        parks_after_reset = (
            action == param_layout.HS_ACT_HOME_PARK
            and motor_id not in _PARKING_RESETS
            and bit & _PARKED_AFTER_RESET
        )

        if action == param_layout.HS_ACT_PARK or parks_after_reset:
            plan.append(f"{_PARK_STEP_PREFIX}{motor_id}")

    return plan


def home_all_block_reason(rows):
    """Why Home All must not run this table, or "": the firmware's own
    table rules, then the safe order (the tray home after the PMT and
    magnet homes), which the vendor UI enforces by default. An empty table
    is refused only as a write: Home All runs the compiled default for it,
    as the board does at boot (the vendor's own Home All drops that rule)."""
    problems = [
        problem
        for problem in param_layout.home_seq_problems(rows)
        if problem != param_layout.HOME_SEQ_EMPTY_PROBLEM
    ]

    if problems:
        return f"home sequence invalid: {'; '.join(problems)}"

    unsafe = param_layout.home_seq_safe_order_problems(rows)

    if unsafe:
        return f"home sequence order unsafe: {'; '.join(unsafe)}"

    return ""


def reset_tray(motor, uart):
    """Home the tray: the vendor's ``tray_reset_job``. TRAY_RESET, unless
    the firmware does not know it (RESP_UNKNOWN, remembered on the uart for
    the connection) or does not answer: then CABIN_MAG_RESET, which homes
    tray + magnet. A board refusal (an interlock) is False, no fallback."""
    errors = getattr(uart, "last_error_ftype", None)

    if not getattr(uart, _TRAY_RESET_UNSUPPORTED, False):
        if isinstance(errors, dict):
            errors.pop(TRAY_RESET_CMD, None)

        if motor.tray_reset() is not None:
            return True

        ftype = errors.get(TRAY_RESET_CMD) if isinstance(errors, dict) else None

        if ftype is None:
            result = uart.last_result(TRAY_RESET_CMD)
            ftype = getattr(result, "ftype", None)
            status = getattr(result, "status", None)

            if ftype is None and status not in (None, "timeout", "no_reply"):
                return False

        if ftype == Frame.RESP_UNKNOWN:
            setattr(uart, _TRAY_RESET_UNSUPPORTED, True)
        elif ftype is not None:
            return False

    return motor.cabin_mag_reset()


def run_home_step(proxy, step):
    """Send one plan step; the driver's reply."""

    if step.startswith(_PARK_STEP_PREFIX):
        motor_id = int(step.removeprefix(_PARK_STEP_PREFIX))
        return proxy.motor.motor_control(motor_id, MOTOR_ACTION_PARK, 0)

    if step == "tray_reset":
        return reset_tray(proxy.motor, proxy.uart)

    return getattr(proxy.motor, step)()


def home_step_failure(step, reply, uart):
    """Why a plan step failed, or "". No reply (None) or a refusal (False)
    is the driver's account of the request; an answer may still carry an
    error status (a MOTOR_CONTROL park's MTE_* code)."""

    if reply is None or reply is False:
        if step.startswith(_PARK_STEP_PREFIX):
            cmd = MotorBoard.MOTOR_CONTROL
        elif step == "tray_reset" and getattr(uart, _TRAY_RESET_UNSUPPORTED, False):
            cmd = MotorBoard.CABIN_MAG_RESET
        else:
            cmd = _RESET_COMMANDS[step]

        return describe_last_result(uart, cmd)

    return device_status_error(reply, f"home all {step}") or ""


class MotionSafetyMixin(HasTraits):
    """Home All and the E-STOP for the motors mixin. Composes into the
    controller, which provides ``proxy``, ``pads_smart_engaged``,
    ``_proxy_call``, the publish helpers and the states mixin's
    ``_leave_realtime_mode``."""

    #: Motor ids a stop or E-STOP was sent to since their last move began:
    #: the interrupted move's failed reply is then logged, not published.
    _stopped_motor_ids = Instance(set, args=())

    #: Set by an E-STOP: the running Home All sends no further step.
    _home_all_estopped = Bool(False)

    #: Held while a Home All runs; a second one is refused, as in the vendor
    #: UI. Any(): Instance(threading.Lock) rejects locks on Python 3.12.
    _home_all_lock = Any()

    def __home_all_lock_default(self):
        return threading.Lock()

    def on_motor_stop_request(self, message):
        """Stop one motor (MOTOR_CONTROL STOP). The driver matches each
        reply to its own request, so it goes out while the move it stops is
        still waiting; that move's failed reply is then logged only."""
        motor_id = self._motor_id(message)

        if motor_id is None:
            return

        self._stopped_motor_ids.add(motor_id)

        self._motion_call(
            f"motor {message} stop",
            lambda: self.proxy.uart.motorStop(motor_id),
            MotorBoard.MOTOR_CONTROL,
            failure=motor_command_failure,
        )
        self._publish_motors()

    def on_motor_estop_request(self, message):
        """EMERGENCY STOP — MOTORS, the vendor UI's EStopButton: one
        MOTOR_ESTOP ramps every axis down (holding current kept) and aborts
        any move, home or coordinated sequence in flight. Motors only, as
        the vendor's: HV, the PMT supply, heaters and the rails stay as
        they are. It skips the proxy lock like a motor stop; the board
        answers at once with the axes that were moving."""
        self._home_all_estopped = True
        self._stopped_motor_ids.update(MOTOR_IDS.values())
        logger.warning("Portable Dropbot E-STOP: stopping ALL motor axes")

        ok, reply = self._proxy_call(
            "motor E-STOP", lambda: self.proxy.motor.motor_estop(), serialize=False
        )

        if ok and reply is None:
            uart = getattr(self.proxy, "uart", None)
            self._publish_error(
                "motor E-STOP", describe_last_result(uart, MOTOR_ESTOP_CMD)
            )
        elif ok:
            logger.info(
                f"Portable Dropbot E-STOP --> sent "
                f"(moving axes 0b{reply.moving_bitmap:06b})"
            )

        self._publish_motors()

    def on_home_all_request(self, message):
        """Run the vendor UI's Home All (see the module docstring), each
        step outside the proxy lock: they run for up to minutes (PMT_RESET
        340 s), and the driver matches every reply to its own request, so
        status polls, stops and the E-STOP keep going meanwhile. The
        firmware refuses conflicting motion (BUSY) on its own."""

        if not self._home_all_lock.acquire(blocking=False):
            self._publish_error("home all", "Home All is already running")
            return

        try:
            self._home_all()
        finally:
            self._home_all_lock.release()

        self._publish_status_snapshot()

    def _home_all(self):
        self._home_all_estopped = False

        # Nothing stays energized while the deck moves.
        self._leave_realtime_mode()

        ok, reply = self._proxy_call(
            "home sequence read",
            lambda: self.proxy.motor.get_params(param_layout.HOME_SEQ_KEY),
        )
        rows = home_seq_rows(reply if ok else None)
        blocked = home_all_block_reason(rows)

        if blocked:
            self._publish_error("home all", blocked)
            return

        plan = home_all_plan(rows)
        logger.info(f"Portable Dropbot Home All: {', '.join(plan)}")
        failed = []

        for step in plan:
            if self._home_all_estopped:
                logger.info("Portable Dropbot Home All stopped by E-STOP")
                return

            if not self._run_home_step(step):
                failed.append(step)
            elif step == "pushpad_reset":
                # The pad reset retracts both pads, smart engage or not.
                self.pads_smart_engaged = False

        logger.info(
            f"Portable Dropbot Home All --> "
            f"{f'finished, failed: {failed}' if failed else 'finished'}"
        )

    def _run_home_step(self, step):
        """Run one plan step outside the proxy lock; True when it succeeded.
        A failure is published, except one an E-STOP caused."""
        context = f"home all: {step}"
        ok, reply = self._proxy_call(
            context, lambda: run_home_step(self.proxy, step), serialize=False
        )

        # A raised failure has already been reported by _proxy_call.
        if not ok:
            return False

        failure = home_step_failure(step, reply, getattr(self.proxy, "uart", None))

        if not failure:
            return True

        if self._home_all_estopped:
            logger.info(f"Portable Dropbot {context} --> E-STOPPED ({failure})")
        else:
            self._publish_error(context, failure)

        return False
