# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Advanced-mode system requests: fan and buzzer control, the
per-motor mechanical param workflow (read -> RAM write -> flash
preset -> motor-board reboot to take effect), and the magnet engage
height in the motor board's device defaults (read -> RAM write, live
at once -> flash preset)."""

# Standard library imports.
import json
import struct

# Third-party imports.
from dropbot_portable import MotorBoard
from pydantic import ValidationError

# Enthought library imports.
from traits.api import HasTraits, Str, provides

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    FAN_BOARDS,
    MAGNET_DEFAULTS_FIELDS,
    MAGNET_DEFAULTS_FORMAT,
    MAGNET_DEFAULTS_PARAM,
    MOTOR_PARAM_FIELDS,
    MOTOR_PARAM_NAMES,
    MOTOR_PARAMS_UPDATED,
    MagnetEngageWriteRequest,
    magnet_engage_updated_publisher,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

# Logger import.
from logger.logger_service import get_logger

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
        ok, result = self._proxy_call("buzzer", lambda: self.proxy.uart.setBuzzer(on))
        logger.info(
            f"Portable Dropbot buzzer --> "
            f"{'on' if on else 'off'}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    def on_set_fan_request(self, message):
        data = json.loads(str(message))
        board = str(data.get("board") or self.preferences.fan_board)

        if board not in FAN_BOARDS:
            logger.warning(f"Unknown fan board: {board!r}")
            return

        on = bool(data["on"])
        ok, result = self._proxy_call(
            f"{board} fan", lambda: self.proxy.uart.setFan(on, board=board)
        )
        logger.info(
            f"Portable Dropbot {board} fan --> "
            f"{'on' if on else 'off'}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    # ------------------------------------------------------------------ #
    # Motor mechanical params                                              #
    # ------------------------------------------------------------------ #
    def _publish_motor_params(self, **payload):
        publish_message(topic=MOTOR_PARAMS_UPDATED, message=json.dumps(payload))

    def _read_motor_board_param(self, context, friendly):
        """Read one motor-board param struct by its driver PARAMS friendly
        name; returns the raw struct bytes, or None when the read failed."""
        ok, resp = self._proxy_call(
            context, lambda: self.proxy.uart.getBoardParameter("motor", friendly)
        )

        if not ok or not resp:
            return None

        # The reply echoes the flash key, NUL, then the raw struct.
        return resp.split(b"\x00", 1)[1]

    def _read_motor_param_fields(self, motor):
        """Read one motor's mechanical params. Returns (fields, error):
        fields maps name -> value for the wire-order prefix the firmware
        sent, or is None with error set when the read failed."""
        blob = self._read_motor_board_param(
            f"read {motor} params", MOTOR_PARAM_NAMES[motor]
        )

        if blob is None:
            return None, "read failed"

        # Old firmware stops at rspd (14 fields, 56 B); newer adds the
        # accel factors (16 fields, 64 B). Parse whichever prefix fits.
        n_fields = 16 if len(blob) >= 64 else 14 if len(blob) >= 56 else 0

        if not n_fields:
            return None, f"short read ({len(blob)} bytes)"

        fields = MOTOR_PARAM_FIELDS[:n_fields]
        fmt = ">" + "".join(f for _, f in fields)
        values = struct.unpack(fmt, blob[: struct.calcsize(fmt)])

        return {name: value for (name, _), value in zip(fields, values)}, ""

    def on_motor_params_read_request(self, message):
        motor = str(message).strip()

        if motor not in MOTOR_PARAM_NAMES:
            logger.warning(f"Unknown motor for params read: {motor!r}")
            return

        fields, error = self._read_motor_param_fields(motor)

        if error:
            self._publish_motor_params(motor=motor, error=error)
            return

        self._publish_motor_params(motor=motor, fields=fields)

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
        fields = [(name, fmt) for name, fmt in MOTOR_PARAM_FIELDS if name in supplied]
        if [name for name, _ in fields] != [
            name for name, _ in MOTOR_PARAM_FIELDS[: len(fields)]
        ]:
            self._publish_motor_params(
                motor=motor, error="fields must be a wire-order prefix"
            )
            return
        packed = b"".join(
            struct.pack(
                f">{fmt}", float(supplied[name]) if fmt == "f" else int(supplied[name])
            )
            for name, fmt in fields
        )
        key = MotorBoard.PARAMS[friendly]
        ok, result = self._proxy_call(
            f"write {motor} params",
            lambda: self.proxy.uart.setParams("motor", key, packed),
        )
        self._publish_motor_params(motor=motor, written=bool(ok and result))
        logger.info(
            f"Portable Dropbot {motor} params write "
            f"({len(fields)} fields) --> "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    def on_motor_params_preset_request(self, message):
        motor = str(message).strip()
        friendly = MOTOR_PARAM_NAMES.get(motor)
        if friendly is None:
            logger.warning(f"Unknown motor for params preset: {motor!r}")
            return
        key = MotorBoard.PARAMS[friendly]
        ok, result = self._proxy_call(
            f"preset {motor} params", lambda: self.proxy.uart.presetParams("motor", key)
        )
        self._publish_motor_params(motor=motor, preset=bool(ok and result))
        logger.info(
            f"Portable Dropbot {motor} params preset to flash "
            f"--> {'ok' if ok and result else 'FAILED'}"
        )

    def on_reboot_motor_board_request(self, message):
        """Reboot the motor board so flashed params take effect (the
        driver waits ~3 s and logs back in). The pads lose their homing
        across the reboot — Home All afterwards."""
        ok, logged_in = self._proxy_call(
            "reboot motor board", lambda: self.proxy.uart.RebootBoard("motor")
        )
        self._publish_motor_params(motor_board_rebooted=bool(ok and logged_in))
        logger.info(
            f"Portable Dropbot motor board reboot --> "
            f"{'ok' if ok and logged_in else 'FAILED'}"
        )

    # ------------------------------------------------------------------ #
    # Magnet engage height (motor-board device defaults)                   #
    # ------------------------------------------------------------------ #
    def _publish_magnet_engage(self, action, engage_um=None, error=""):
        engage_mm = None if engage_um is None else engage_um / 1000
        magnet_engage_updated_publisher.publish(
            {"action": action, "engage_mm": engage_mm, "error": error}
        )

    def _read_magnet_defaults(self):
        """Read the magnet device-defaults struct. Returns (defaults, error):
        defaults maps each MAGNET_DEFAULTS_FIELDS name -> µm, or is None
        with error set when the read failed."""
        blob = self._read_motor_board_param(
            "read magnet defaults", MAGNET_DEFAULTS_PARAM
        )

        if blob is None:
            return None, "read failed"

        size = struct.calcsize(MAGNET_DEFAULTS_FORMAT)

        if len(blob) < size:
            return None, f"short read ({len(blob)} bytes)"

        values = struct.unpack(MAGNET_DEFAULTS_FORMAT, blob[:size])

        return dict(zip(MAGNET_DEFAULTS_FIELDS, values)), ""

    def on_magnet_engage_read_request(self, message):
        defaults, error = self._read_magnet_defaults()

        if error:
            self._publish_magnet_engage("read", error=error)
            return

        self._publish_magnet_engage("read", engage_um=defaults["z_up"])

    def on_magnet_engage_write_request(self, message):
        """RAM-only write of the engage height (z_up): live from the next
        engage, lost on reboot until preset. The struct's other fields are
        read back first and written unchanged; a height above the magnet-Z
        soft limit is refused, since the firmware would reject every
        engage."""
        try:
            request = MagnetEngageWriteRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._publish_magnet_engage(
                "write", error=f"invalid height: {error.errors()[0]['msg']}"
            )
            return

        engage_um = round(request.engage_mm * 1000)
        defaults, error = self._read_magnet_defaults()

        if error:
            self._publish_magnet_engage("write", error=error)
            return

        motor_fields, error = self._read_motor_param_fields("magnet")

        if error:
            self._publish_magnet_engage("write", error=f"magnet-Z soft limit {error}")
            return

        soft_limit_um = motor_fields["pl_pos"]

        if engage_um > soft_limit_um:
            self._publish_magnet_engage(
                "write",
                error=(
                    f"{engage_um / 1000:.3f} mm is above the magnet-Z soft "
                    f"limit ({soft_limit_um / 1000:.3f} mm)"
                ),
            )
            return

        defaults["z_up"] = engage_um
        packed = struct.pack(
            MAGNET_DEFAULTS_FORMAT,
            *(defaults[name] for name in MAGNET_DEFAULTS_FIELDS),
        )
        key = MotorBoard.PARAMS[MAGNET_DEFAULTS_PARAM]
        ok, result = self._proxy_call(
            "write magnet engage height",
            lambda: self.proxy.uart.setParams("motor", key, packed),
        )
        written = bool(ok and result)

        if written:
            self._publish_magnet_engage("write", engage_um=engage_um)
        else:
            self._publish_magnet_engage("write", error="write failed")

        logger.info(
            f"Portable Dropbot magnet engage height {engage_um} µm write "
            f"--> {'ok' if written else 'FAILED'}"
        )

    def on_magnet_engage_preset_request(self, message):
        """Persist the device defaults now in RAM (the last write) to
        flash, so the engage height survives a reboot."""
        key = MotorBoard.PARAMS[MAGNET_DEFAULTS_PARAM]
        ok, result = self._proxy_call(
            "preset magnet engage height",
            lambda: self.proxy.uart.presetParams("motor", key),
        )
        preset = bool(ok and result)

        if preset:
            self._publish_magnet_engage("preset")
        else:
            self._publish_magnet_engage("preset", error="preset failed")

        logger.info(
            f"Portable Dropbot magnet defaults preset to flash "
            f"--> {'ok' if preset else 'FAILED'}"
        )
