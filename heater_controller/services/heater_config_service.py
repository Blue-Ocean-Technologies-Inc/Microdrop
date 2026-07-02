import json
import os
import subprocess
import sys
import tempfile

from traits.api import provides, HasTraits, Instance

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..interfaces.i_heater_control_mixin_service import IHeaterControlMixinService
from ..heater_serial_proxy import HeaterSerialProxy
from ..consts import CONFIG_PUSHED

from logger.logger_service import get_logger
logger = get_logger(__name__)

# Timeout for an individual mpremote invocation (cp / reset).
MPREMOTE_TIMEOUT_S = 60


@provides(IHeaterControlMixinService)
class HeaterConfigService(HasTraits):
    """Board operations for the 'Configure Sensors & Heaters' editor.

    ``on_dump_config_request``  -> send ``dump_config``; the proxy captures the
        CONFIG_BEGIN/END reply and publishes it on CONFIG_DUMPED.
    ``on_scan_sensors_request`` -> run a 1-Wire bus scan; the proxy collects the
        ``Sensor N: <rom>`` reply lines and publishes them on SENSORS_SCANNED.
    ``on_save_config_to_board_request`` -> write a config JSON onto the board's
        filesystem (``config.json``) via mpremote and reboot it. The firmware has
        no serial config-write command, so — like the old UI — we copy the file
        with mpremote, which needs exclusive serial access; this releases the
        proxy's port for the copy and then triggers a reconnect.

    All only run while connected (the base listener gates requests on the
    connection), so a missing proxy can't be hit for scan/dump.
    """
    proxy = Instance(HeaterSerialProxy)

    def on_dump_config_request(self, message):
        logger.info("Heater dump_config requested")
        with self.proxy.transaction_lock:
            self.proxy.send_command("dump_config")

    def on_scan_sensors_request(self, message):
        logger.info("Heater 1-Wire sensor scan requested")
        self.proxy.scan_sensors()

    # ------------------------------------------------------------------ #
    # Save & push config to the board                                     #
    # ------------------------------------------------------------------ #
    def on_save_config_to_board_request(self, message):
        try:
            config = json.loads(message.content)
        except Exception as exc:
            self._publish_pushed(False, f"Invalid config payload: {exc}")
            return
        if self.proxy is None:
            self._publish_pushed(False, "Heater is not connected")
            return

        port = self.proxy.port
        fd, tmp_path = tempfile.mkstemp(prefix="heater_config_", suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(config, fh, indent=2)

        # mpremote needs exclusive access to the serial port, which the proxy
        # holds open — release it for the copy.
        logger.info(f"Pushing config to heater on {port}; releasing the serial port")
        self.proxy.terminate()
        self.proxy = None

        ok, msg = True, "Config written to the board; it is rebooting."
        try:
            self._mpremote(port, "cp", tmp_path, ":config.json")
            self._mpremote(port, "reset")
        except Exception as exc:
            ok, msg = False, f"Push failed: {exc}"
            logger.error(f"Heater config push failed: {exc}")
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            # Reconnect whether or not the push succeeded (the port is free and
            # the board may have rebooted). The monitor re-finds and reconnects.
            publish_message("disconnected", self.disconnected_topic)

        self._publish_pushed(ok, msg)

    @staticmethod
    def _mpremote(port, *args):
        """Run ``mpremote connect <port> <args...>`` via the active interpreter,
        raising RuntimeError on a non-zero exit (or if mpremote is missing)."""
        cmd = [sys.executable, "-m", "mpremote", "connect", port, *args]
        logger.info(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=MPREMOTE_TIMEOUT_S)
        except FileNotFoundError:
            raise RuntimeError("mpremote is not installed in the backend environment")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"mpremote {' '.join(args)} failed: {detail}")

    @staticmethod
    def _publish_pushed(ok, message):
        logger.info(f"Heater config push result: ok={ok} ({message})")
        publish_message(json.dumps({"ok": ok, "message": message}), CONFIG_PUSHED)
