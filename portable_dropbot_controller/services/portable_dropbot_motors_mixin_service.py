import json

from traits.api import HasTraits, Str, provides

from logger.logger_service import get_logger

from ..consts import FILTER_POSITIONS, MOTOR_IDS
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

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
        if direction not in _TRAY_ACTIONS:
            logger.warning(f"Unknown tray direction: {direction!r}")
            return
        self._proxy_call(f"tray {direction}",
                         lambda: self.proxy.move_tray(direction))
        self._publish_status_snapshot()

    def on_move_magnet_request(self, message):
        action = str(message).strip().lower()
        if action not in _MAGNET_ACTIONS:
            logger.warning(f"Unknown magnet action: {action!r}")
            return
        self._proxy_call(f"magnet {action}",
                         lambda: self.proxy.move_magnet(action))
        self._publish_status_snapshot()

    def on_set_filter_request(self, message):
        position = int(str(message))
        if position not in FILTER_POSITIONS:
            logger.warning(f"Filter position out of range: {position}")
            return
        self._proxy_call(f"filter {position}",
                         lambda: self.proxy.setFilter(position))
        self._publish_status_snapshot()

    def on_set_pogo_request(self, message):
        engaged = str(message) == "True"
        self._proxy_call(f"pogo {'down' if engaged else 'up'}",
                         lambda: self.proxy.setPogo(engaged))
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
        self._proxy_call("home all", lambda: self.proxy.home_all())
        self._publish_status_snapshot()

    # ------------------------------------------------------------------ #
    # Advanced per-motor moves (steps, Int)                                #
    # ------------------------------------------------------------------ #
    def _motor_id(self, name):
        motor_id = MOTOR_IDS.get(str(name).strip().lower())
        if motor_id is None:
            logger.warning(f"Unknown motor: {name!r}")
        return motor_id

    def on_motor_move_request(self, message):
        """JSON {"motor": name, "mode": "absolute"|"relative",
        "value": steps}."""
        payload = json.loads(str(message))
        motor_id = self._motor_id(payload.get("motor"))
        if motor_id is None:
            return
        mode = str(payload.get("mode", "absolute"))
        value = int(payload.get("value", 0))
        if mode == "relative":
            self._proxy_call(
                f"motor {payload['motor']} relative {value}",
                lambda: self.proxy.uart.motorRelativeMove(motor_id,
                                                          value))
        else:
            self._proxy_call(
                f"motor {payload['motor']} absolute {value}",
                lambda: self.proxy.uart.motorAbsoluteMove(motor_id,
                                                          value))
        self._publish_motors()

    def on_motor_stop_request(self, message):
        motor_id = self._motor_id(message)
        if motor_id is None:
            return
        self._proxy_call(f"motor {message} stop",
                         lambda: self.proxy.uart.motorStop(motor_id))
        self._publish_motors()

    def on_motor_home_request(self, message):
        motor_id = self._motor_id(message)
        if motor_id is None:
            return
        self._proxy_call(f"motor {message} home",
                         lambda: self.proxy.uart.motorHome(motor_id))
        self._publish_motors()

    def on_refresh_motors_request(self, message):
        self._publish_status_snapshot()
