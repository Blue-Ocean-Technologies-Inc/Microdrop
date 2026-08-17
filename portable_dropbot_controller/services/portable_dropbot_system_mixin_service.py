"""Advanced-mode system requests: fan and buzzer control, plus the
per-motor mechanical param workflow (read -> RAM write -> flash
preset -> motor-board reboot to take effect)."""
import json
import struct

from traits.api import HasTraits, Str, provides

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import (
    MOTOR_PARAM_FIELDS, MOTOR_PARAM_NAMES, MOTOR_PARAMS_UPDATED,
)
from ..driver.commands import MotorBoard
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotSystemMixinService(HasTraits):
    id = Str("portable_dropbot_system_mixin_service")
    name = Str("Portable Dropbot System Mixin")

    # ------------------------------------------------------------------ #
    # Fan / buzzer                                                         #
    # ------------------------------------------------------------------ #
    def on_set_buzzer_request(self, message):
        on = str(message) == "True"
        self._proxy_call("buzzer",
                         lambda: self.proxy.uart.setBuzzer(on))
        logger.info(f"Portable Dropbot buzzer --> "
                    f"{'on' if on else 'off'}")

    def on_set_fan_request(self, message):
        data = json.loads(str(message))
        board = str(data["board"])
        if board not in ("signal", "motor"):
            logger.warning(f"Unknown fan board: {board!r}")
            return
        on = bool(data["on"])
        self._proxy_call(
            f"{board} fan",
            lambda: self.proxy.uart.setFan(on, board=board))
        logger.info(f"Portable Dropbot {board} fan --> "
                    f"{'on' if on else 'off'}")

    # ------------------------------------------------------------------ #
    # Motor mechanical params                                              #
    # ------------------------------------------------------------------ #
    def _publish_motor_params(self, **payload):
        publish_message(topic=MOTOR_PARAMS_UPDATED,
                        message=json.dumps(payload))

    def on_motor_params_read_request(self, message):
        motor = str(message).strip()
        friendly = MOTOR_PARAM_NAMES.get(motor)
        if friendly is None:
            logger.warning(f"Unknown motor for params read: {motor!r}")
            return
        ok, resp = self._proxy_call(
            f"read {motor} params",
            lambda: self.proxy.uart.getBoardParameter("motor", friendly))
        if not ok or not resp:
            self._publish_motor_params(motor=motor, error="read failed")
            return
        # The reply echoes the flash key, NUL, then the raw struct.
        blob = resp.split(b"\x00", 1)[1]
        # Old firmware stops at rspd (14 fields, 56 B); newer adds the
        # accel factors (16 fields, 64 B). Parse whichever prefix fits.
        n_fields = 16 if len(blob) >= 64 else 14 if len(blob) >= 56 else 0
        if not n_fields:
            self._publish_motor_params(
                motor=motor, error=f"short read ({len(blob)} bytes)")
            return
        fields = MOTOR_PARAM_FIELDS[:n_fields]
        fmt = ">" + "".join(f for _, f in fields)
        values = struct.unpack(fmt, blob[:struct.calcsize(fmt)])
        self._publish_motor_params(
            motor=motor,
            fields={name: value
                    for (name, _), value in zip(fields, values)})

    def on_motor_params_write_request(self, message):
        """RAM-only write; presetting to flash and rebooting the motor
        board are separate explicit requests."""
        data = json.loads(str(message))
        motor = str(data["motor"])
        friendly = MOTOR_PARAM_NAMES.get(motor)
        if friendly is None:
            logger.warning(f"Unknown motor for params write: {motor!r}")
            return
        supplied = data["fields"]
        # The struct is positional: only a prefix of the wire order can
        # be written (exactly what a read of that firmware returned).
        fields = [(name, fmt) for name, fmt in MOTOR_PARAM_FIELDS
                  if name in supplied]
        if [name for name, _ in fields] != \
                [name for name, _ in MOTOR_PARAM_FIELDS[:len(fields)]]:
            self._publish_motor_params(
                motor=motor, error="fields must be a wire-order prefix")
            return
        packed = b"".join(
            struct.pack(f">{fmt}",
                        float(supplied[name]) if fmt == "f"
                        else int(supplied[name]))
            for name, fmt in fields)
        key = MotorBoard.PARAMS[friendly]
        ok, result = self._proxy_call(
            f"write {motor} params",
            lambda: self.proxy.uart.setParams("motor", key, packed))
        self._publish_motor_params(motor=motor,
                                   written=bool(ok and result))
        logger.info(f"Portable Dropbot {motor} params write "
                    f"({len(fields)} fields) --> "
                    f"{'ok' if ok and result else 'FAILED'}")

    def on_motor_params_preset_request(self, message):
        motor = str(message).strip()
        friendly = MOTOR_PARAM_NAMES.get(motor)
        if friendly is None:
            logger.warning(f"Unknown motor for params preset: {motor!r}")
            return
        key = MotorBoard.PARAMS[friendly]
        ok, result = self._proxy_call(
            f"preset {motor} params",
            lambda: self.proxy.uart.presetParams("motor", key))
        self._publish_motor_params(motor=motor,
                                   preset=bool(ok and result))
        logger.info(f"Portable Dropbot {motor} params preset to flash "
                    f"--> {'ok' if ok and result else 'FAILED'}")

    def on_reboot_motor_board_request(self, message):
        """Reboot the motor board so flashed params take effect (the
        driver waits ~3 s and logs back in). The pads lose their homing
        across the reboot — Home All afterwards."""
        ok, logged_in = self._proxy_call(
            "reboot motor board",
            lambda: self.proxy.uart.RebootBoard("motor"))
        self._publish_motor_params(
            motor_board_rebooted=bool(ok and logged_in))
        logger.info(f"Portable Dropbot motor board reboot --> "
                    f"{'ok' if ok and logged_in else 'FAILED'}")
