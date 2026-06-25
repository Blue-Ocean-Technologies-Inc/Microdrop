import json
import time
import threading

import serial

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from .consts import (
    CONNECTED,
    DISCONNECTED,
    HEATERS_AVAILABLE,
    BOARD_BAUDRATE,
    CONFIG_BEGIN,
    CONFIG_END,
    CONFIG_ERROR_PREFIX,
)

logger = get_logger(__name__)

# Telemetry frames arrive as: §<FRAME>{json}\n  e.g.  §PID_TEC1{"temp": 41.2}
TELEMETRY_MARKER = "§"


class HeaterSerialProxy:
    """Minimal headless serial proxy for the heater controller (RP2040 / MicroPython).

    Unlike the mr-box peripheral (structured base_node_rpc RPC), the heater speaks
    newline-terminated plain text: commands are strings (``whoami``, ``scan``,
    ``stream_all``, ``pid_<heater>_<setpoint>``, ...) and responses are plain-text
    lines plus ``§<FRAME>{json}`` telemetry packets.

    Received data is mostly log-only (printed via the logger); the one piece we
    act on is the ``dump_config`` response (framed by CONFIG_BEGIN/END), which we
    request on connect to discover the available heater channels and publish them
    on HEATERS_AVAILABLE for a frontend to offer as a selection. The proxy opens
    the port, runs a background reader thread, exposes ``send_command`` for
    writes, and publishes the connected/disconnected signals so the controller
    tracks connection state.
    """

    SERIAL_TIMEOUT = 2.0
    SERIAL_WRITE_TIMEOUT = 2.0
    MAX_COMMAND_RETRIES = 3
    COMMAND_RETRY_DELAY = 0.5

    def __init__(self, port, baudrate=BOARD_BAUDRATE):
        self.port = port
        self.baudrate = baudrate
        self.transaction_lock = threading.Lock()

        self._stop_reader = threading.Event()
        self.reader_thread = None

        # dump_config response capture state (CONFIG_BEGIN .. CONFIG_END)
        self._capturing_config = False
        self._config_buffer = []

        # Opens the port (raises on failure so the monitor falls back to disconnect)
        self.serial_port = serial.Serial(
            port=port,
            baudrate=int(baudrate),
            timeout=self.SERIAL_TIMEOUT,
            write_timeout=self.SERIAL_WRITE_TIMEOUT,
        )

        # Flush any stale bytes before we start reading.
        try:
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
        except Exception as e:
            logger.debug(f"Could not flush heater serial buffers (may be expected): {e}")

        self.reader_thread = threading.Thread(target=self._serial_reader, daemon=True)
        self.reader_thread.start()

        logger.info(f"Heater connected on port {port} at {baudrate} baud")
        publish_message("connected", CONNECTED)

        # Ask the board for its config so we can advertise the available heater
        # channels. The response is captured by the reader thread.
        try:
            self.send_command("dump_config")
        except Exception as e:
            logger.warning(f"Could not request heater config on connect: {e}")

    # ------------------------------------------------------------------
    # Background reader: logs plain text + §{json} telemetry
    # ------------------------------------------------------------------
    def _serial_reader(self):
        """Daemon thread. Reads one line at a time and logs it. Lines beginning
        with ``§`` are parsed as ``§<FRAME>{json}`` telemetry. On a genuine
        disconnect (port error) it publishes the disconnected signal and exits.
        """
        try:
            while not self._stop_reader.is_set():
                if not self.serial_port or not self.serial_port.is_open:
                    break

                raw = self.serial_port.readline()
                if not raw:
                    continue  # read timeout → loop again

                try:
                    line = raw.decode(errors='ignore').strip()
                except UnicodeDecodeError:
                    continue
                if not line:
                    continue

                if line.startswith(TELEMETRY_MARKER):
                    frame, pkt = self.parse_telemetry_line(line)
                    if pkt is None:
                        logger.warning(f"Heater telemetry could not be parsed: {line}")
                    else:
                        logger.info(f"HEATER TELEMETRY [{frame}]: {pkt}")
                elif self._route_config_line(line):
                    continue  # consumed by the dump_config capture state machine
                else:
                    logger.info(f"HEATER RX: {line}")

        except (OSError, serial.SerialException) as e:
            if not self._stop_reader.is_set():
                logger.warning(f"Heater serial reader lost the port: {e}")
                publish_message("disconnected", DISCONNECTED)
        except Exception as e:
            logger.error(f"Heater serial reader crashed: {e}", exc_info=True)
        finally:
            logger.debug("Heater serial reader thread terminated")

    # ------------------------------------------------------------------
    # dump_config capture -> publish available heaters
    # ------------------------------------------------------------------
    def _route_config_line(self, line):
        """Feed a plain-text line through the ``dump_config`` capture state
        machine. Returns True if the line was part of the config response (and
        should not be logged as ordinary RX), False otherwise."""
        if line == CONFIG_BEGIN:
            self._capturing_config = True
            self._config_buffer = []
            return True
        if line == CONFIG_END:
            if self._capturing_config:
                self._capturing_config = False
                self._publish_available_heaters("\n".join(self._config_buffer))
            return True
        if line.startswith(CONFIG_ERROR_PREFIX):
            self._capturing_config = False
            logger.warning(f"Heater reported config error: {line}")
            return True
        if self._capturing_config:
            self._config_buffer.append(line)
            return True
        return False

    def _publish_available_heaters(self, config_text):
        """Parse the captured config JSON and publish the heater channel names."""
        heaters = self.parse_heaters_from_config(config_text)
        if heaters is None:
            logger.warning("Could not parse heater config; available heaters not published")
            return
        logger.info(f"Heater channels available: {heaters}")
        publish_message(json.dumps(heaters), HEATERS_AVAILABLE)

    @staticmethod
    def parse_heaters_from_config(config_text):
        """Extract the heater channel names from a ``dump_config`` JSON document.

        Returns a list of names (the keys of the ``heaters`` section), or None if
        the text isn't valid JSON.
        """
        try:
            config = json.loads(config_text)
        except Exception:
            return None
        heaters = config.get("heaters", {}) if isinstance(config, dict) else {}
        return list(heaters.keys()) if isinstance(heaters, dict) else []

    @staticmethod
    def parse_telemetry_line(line):
        """Parse a ``§<FRAME>{json}`` telemetry line into ``(frame, pkt)``.

        The frame tag (e.g. ``PID_TEC1``) sits between the marker and the JSON
        object and is tagged onto the dict as ``_frame``. Returns ``(frame, None)``
        when the line carries no/invalid JSON object.
        """
        json_start = line.find('{')
        if json_start == -1:
            return line[len(TELEMETRY_MARKER):], None
        frame = line[len(TELEMETRY_MARKER):json_start]
        try:
            pkt = json.loads(line[json_start:])
        except Exception:
            return frame, None
        if isinstance(pkt, dict):
            pkt['_frame'] = frame
        return frame, pkt

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def send_command(self, command):
        """Send a newline-terminated plain-text command to the heater, retrying a
        few times on transient write failures."""
        if not self.serial_port or not self.serial_port.is_open:
            raise RuntimeError("Heater serial port not open")

        if isinstance(command, str):
            if not command.endswith('\n'):
                command = command + '\n'
            command = command.encode()

        logger.debug(f"HEATER TX: {command}")

        for attempt in range(self.MAX_COMMAND_RETRIES):
            try:
                self.serial_port.write(command)
                return
            except Exception as e:
                if attempt == self.MAX_COMMAND_RETRIES - 1:
                    logger.error(f"Error sending heater command after retries: {e}")
                    raise
                logger.warning(
                    f"Heater command failed (attempt {attempt + 1}/{self.MAX_COMMAND_RETRIES}): {e}")
                time.sleep(self.COMMAND_RETRY_DELAY)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def terminate(self):
        """Stop the reader thread and close the port. Intentional shutdown — does
        not publish the disconnected signal."""
        self._stop_reader.set()
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1.0)
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                logger.debug("Heater serial port closed")
        except Exception as e:
            logger.error(f"Error closing heater serial port: {e}")
