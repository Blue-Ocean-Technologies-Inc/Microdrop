import json
import time
import threading

import serial

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from .consts import CONNECTED, DISCONNECTED, BOARD_BAUDRATE

logger = get_logger(__name__)

# Telemetry frames arrive as: §<FRAME>{json}\n  e.g.  §PID_TEC1{"temp": 41.2}
TELEMETRY_MARKER = "§"


class HeaterSerialProxy:
    """Minimal headless serial proxy for the heater controller (RP2040 / MicroPython).

    Unlike the mr-box peripheral (structured base_node_rpc RPC), the heater speaks
    newline-terminated plain text: commands are strings (``whoami``, ``scan``,
    ``stream_all``, ``pid_<heater>_<setpoint>``, ...) and responses are plain-text
    lines plus ``§<FRAME>{json}`` telemetry packets.

    For now received data is log-only (printed via the logger); wiring it onto
    dramatiq topics is a deliberate next step. The proxy opens the port, runs a
    background reader thread, exposes ``send_command`` for writes, and publishes
    the connected/disconnected signals so the controller tracks connection state.
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
