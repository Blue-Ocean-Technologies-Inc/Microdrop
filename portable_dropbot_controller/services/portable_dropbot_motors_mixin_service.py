# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import json

from traits.api import HasTraits, Str, provides

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import (
    FILTER_POSITIONS,
    MAGNET_APPLIED,
    MAGNET_HEIGHT_MM_BOUNDS,
    MOTOR_IDS,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

from logger.logger_service import get_logger

logger = get_logger(__name__)

#: What the tray and magnet mechanism requests accept — the driver's
#: own vocabulary.
_TRAY_ACTIONS = ("in", "out")
_MAGNET_ACTIONS = ("engage", "disengage", "press", "release")


@provides(IPortableDropbotControlMixinService)
class PortableDropbotMotorsMixinService(HasTraits):
    """Mechanism macros and advanced per-motor moves. Every handler
    finishes by republishing the motor picture, so the motor panel
    repaints from what the hardware reports, not what was asked."""

    id = Str("portable_dropbot_motors_mixin_service")
    name = Str("Portable Dropbot Motors Mixin")

    # ------------------------------------------------------------------ #
    # Mechanism macros                                                     #
    # ------------------------------------------------------------------ #
    def on_move_tray_request(self, message):
        direction = str(message).strip().lower()
        if direction == "toggle":
            # The status pane's device picture: one click ejects, the
            # next brings it back. Read the cabin state from the motor
            # STATUS (byte 1) — the CHIP_CABIN_READ blob goes
            # undecoded even in the vendor UI, but STATUS answers
            # reliably (it feeds the mechanisms readout) and its state
            # mirrors the ctrl vocabulary (0 = in, 1 = out), the same
            # way mag reports 1 while engaged.
            ok, motor_status = self._proxy_call(
                "motor status read", lambda: self.proxy.uart.GetBoardStatus("motor")
            )
            if not ok or not motor_status or len(motor_status) < 2:
                logger.warning("Tray toggle ignored: current tray position unknown.")
                return
            direction = "in" if motor_status[1] == 1 else "out"
        if direction not in _TRAY_ACTIONS:
            logger.warning(f"Unknown tray direction: {direction!r}")
            return
        logger.info(f"Portable Dropbot tray {direction} requested")
        # move_tray returns the driver error flag: True means the move
        # reported an error status.
        ok, error_flag = self._proxy_call(
            f"tray {direction}", lambda: self.proxy.move_tray(direction)
        )
        logger.info(
            f"Portable Dropbot tray {direction} --> "
            f"{'ok' if ok and error_flag is not True else 'FAILED'}"
        )
        self._publish_status_snapshot()

    def on_move_magnet_request(self, message):
        action = str(message).strip().lower()
        if action not in _MAGNET_ACTIONS:
            logger.warning(f"Unknown magnet action: {action!r}")
            return
        logger.info(f"Portable Dropbot magnet {action} requested")
        ok, result = self._proxy_call(
            f"magnet {action}", lambda: self.proxy.move_magnet(action)
        )
        logger.info(
            f"Portable Dropbot magnet {action} --> "
            f"{'ok' if ok and result not in (None, False) else 'FAILED'}"
        )
        self._publish_status_snapshot()

    def on_protocol_set_magnet_request(self, message):
        """Protocol-driven magnet engage/disengage or absolute move.
        JSON {"on": bool, "height_mm": float}.

        "on": False disengages. "on": True with height_mm below
        MAGNET_HEIGHT_MM_BOUNDS[0] (the column's "Default" sentinel)
        runs the firmware's engage macro; any other height drives the
        magnet motor to that absolute position (mm, converted to the
        firmware's µm move units). On hardware error the ack is NOT
        published — the protocol step's wait_for times out and the
        step fails (consistent with the rest of this mixin's request
        handlers).
        """
        payload = json.loads(str(message))
        on = bool(payload["on"])
        height_mm = float(payload["height_mm"])

        if not on:
            ok, result = self._proxy_call(
                "protocol magnet disengage", lambda: self.proxy.move_magnet("disengage")
            )
        elif height_mm < MAGNET_HEIGHT_MM_BOUNDS[0]:
            ok, result = self._proxy_call(
                "protocol magnet engage", lambda: self.proxy.move_magnet("engage")
            )
        else:
            value_um = round(height_mm * 1000)
            ok, result = self._proxy_call(
                f"protocol magnet absolute {value_um}",
                lambda: self.proxy.uart.motorAbsoluteMove(
                    MOTOR_IDS["magnet"], value_um
                ),
            )

        if ok and result not in (None, False):
            logger.info(
                f"Portable Dropbot protocol magnet "
                f"{'on' if on else 'off'} ({height_mm} mm) --> ok"
            )
            publish_message(topic=MAGNET_APPLIED, message=str(int(on)))
        else:
            logger.warning(
                f"Portable Dropbot protocol magnet "
                f"{'on' if on else 'off'} ({height_mm} mm) --> "
                f"FAILED; no ack published"
            )
        self._publish_status_snapshot()

    def on_set_filter_request(self, message):
        position = int(str(message))
        if position not in FILTER_POSITIONS:
            logger.warning(f"Filter position out of range: {position}")
            return
        logger.info(f"Portable Dropbot filter position {position} requested")
        ok, result = self._proxy_call(
            f"filter {position}", lambda: self.proxy.uart.setFilter(position)
        )
        logger.info(
            f"Portable Dropbot filter --> {position}: "
            f"{'ok' if ok and result not in (None, False) else 'FAILED'}"
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
        ok, result = self._proxy_call(
            f"pogo {action}", lambda: self.proxy.uart.setPogo(1 if engaged else 0)
        )
        logger.info(
            f"Portable Dropbot pogo {action} --> "
            f"{'ok' if ok and result not in (None, False) else 'FAILED'}"
        )
        self._publish_status_snapshot()

    def on_lock_chip_request(self, message):
        """Chip lock IS the pogo pads pressing the chip; a topic of
        its own so panes and protocol steps say what they mean. The
        snapshot afterwards lets chip_on_pad report the result rather
        than assuming it."""
        self.on_set_pogo_request(message)

    def on_home_all_request(self, message):
        # The full homing sequence runs tens of seconds; it executes
        # here on the worker thread, so the GUI stays live and the
        # snapshot lands when the hardware is truly home.
        logger.info("Portable Dropbot home-all requested (runs tens of seconds)")
        ok, _ = self._proxy_call("home all", lambda: self.proxy.home_all())
        logger.info(f"Portable Dropbot home-all --> {'finished' if ok else 'FAILED'}")
        self._publish_status_snapshot()

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
        mode = str(payload.get("mode", "absolute"))
        value = int(payload.get("value", 0))
        if mode == "relative":
            ok, result = self._proxy_call(
                f"motor {payload['motor']} relative {value}",
                lambda: self.proxy.uart.motorRelativeMove(motor_id, value),
            )
        else:
            ok, result = self._proxy_call(
                f"motor {payload['motor']} absolute {value}",
                lambda: self.proxy.uart.motorAbsoluteMove(motor_id, value),
            )
        # motorAction returns the final position on success, an error
        # string or status otherwise.
        logger.info(
            f"Portable Dropbot motor {payload['motor']} {mode} "
            f"move {value} um --> "
            f"{result if ok and result is not None else 'FAILED'}"
        )
        self._publish_motors()

    def on_motor_set_speed_request(self, message):
        """JSON {"motor": name, "value": run speed in µm/s}. Runtime
        only — the flashed default returns on reboot, and homing
        shares this speed, so keep bumps temporary (see the driver's
        setMotorSpeed notes)."""
        payload = json.loads(str(message))
        motor_id = self._motor_id(payload.get("motor"))
        if motor_id is None:
            return
        speed = int(payload.get("value", 0))
        ok, accepted = self._proxy_call(
            f"motor {payload['motor']} speed {speed}",
            lambda: self.proxy.uart.setMotorSpeed(motor_id, speed),
        )
        logger.info(
            f"Portable Dropbot motor {payload['motor']} speed "
            f"{speed} um/s --> "
            f"{accepted if ok and accepted is not None else 'FAILED'}"
        )

    def on_motor_stop_request(self, message):
        motor_id = self._motor_id(message)
        if motor_id is None:
            return
        ok, result = self._proxy_call(
            f"motor {message} stop", lambda: self.proxy.uart.motorStop(motor_id)
        )
        logger.info(
            f"Portable Dropbot motor {message} stop --> "
            f"{result if ok and result is not None else 'FAILED'}"
        )
        self._publish_motors()

    def on_motor_home_request(self, message):
        motor_id = self._motor_id(message)
        if motor_id is None:
            return
        ok, result = self._proxy_call(
            f"motor {message} home", lambda: self.proxy.uart.motorHome(motor_id)
        )
        logger.info(
            f"Portable Dropbot motor {message} home --> "
            f"{result if ok and result is not None else 'FAILED'}"
        )
        self._publish_motors()

    def on_refresh_motors_request(self, message):
        self._publish_status_snapshot()
