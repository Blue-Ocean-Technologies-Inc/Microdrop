import time
from threading import RLock

import numpy as np
import serial

from .consts import (
    MAX_TEMPERATURE_C,
    MIN_TEMPERATURE_C,
    NUM_CONTROL_IN_BYTES,
    NUM_CONTROL_OUT_BYTES,
    NUM_ELECTRODE_BYTES,
    NUM_ELECTRODES,
)


# Minimum seconds between actual serial writes (throttle / debounce).
WRITE_DEBOUNCE_S = 0.05


class OpenDropSerialProxy:
    """
    Thin serial proxy implementing the OpenDrop frame protocol
    """

    def __init__(self, port: str, baud_rate: int, serial_timeout_s: float):
        self.port = port
        self.baud_rate = int(baud_rate)
        self.serial_timeout_s = float(serial_timeout_s)
        self.transaction_lock = RLock()
        self.serial_port = None

        self.state_of_channels = np.zeros(NUM_ELECTRODES, dtype=bool)
        self.control_data_out = bytearray(NUM_CONTROL_OUT_BYTES)
        self.control_data_in = bytearray(NUM_CONTROL_IN_BYTES)

        self._last_write_time = 0.0
        self._last_telemetry = None

    @property
    def is_connected(self) -> bool:
        return self.serial_port is not None and self.serial_port.is_open

    def check_connection(self) -> bool:
        """
        Return True if the serial port is still valid (device present).
        Performs a minimal I/O so unplug is detected; use periodically.
        """
        if self.serial_port is None or not self.serial_port.is_open:
            return False
        try:
            self.serial_port.reset_input_buffer()
            return True
        except (OSError, serial.SerialException):
            return False
        except Exception:
            return False

    def connect(self):
        if self.is_connected:
            return
        self.serial_port = serial.Serial(
            port=self.port,
            baudrate=self.baud_rate,
            timeout=self.serial_timeout_s,
            write_timeout=self.serial_timeout_s,
        )
    
    def disconnect(self):
        self.close()
    
    def close(self):
        if self.serial_port is not None:
            try:
                self.serial_port.close()
            except (OSError, serial.SerialException):
                pass
            finally:
                self.serial_port = None
                self._last_telemetry = None
                self._last_write_time = 0.0

    def write_state(self, feedback_enabled: bool, temperatures_c: list[int], read_timeout_ms: int) -> dict:
        """
        Send current channel state + control bytes and parse telemetry.
        Debounced by WRITE_DEBOUNCE_S: calls within 0.05s skip the write and return last telemetry.
        Returns parsed telemetry dict.
        """
        if not self.is_connected:
            raise RuntimeError("OpenDrop serial port is not connected.")

        if len(temperatures_c) != 3:
            raise ValueError("temperatures_c must contain exactly 3 values.")

        with self.transaction_lock:
            now = time.monotonic()
            if self._last_telemetry is not None and (now - self._last_write_time) < WRITE_DEBOUNCE_S:
                return self._last_telemetry

            tx_electrodes = self._encode_electrodes(self.state_of_channels)
            self.control_data_out[:] = bytes(NUM_CONTROL_OUT_BYTES)
            self.control_data_out[6] = 1 if bool(feedback_enabled) else 0
            self.control_data_out[8] = int(np.clip(int(temperatures_c[0]), MIN_TEMPERATURE_C, MAX_TEMPERATURE_C))
            self.control_data_out[9] = int(np.clip(int(temperatures_c[1]), MIN_TEMPERATURE_C, MAX_TEMPERATURE_C))
            self.control_data_out[10] = int(np.clip(int(temperatures_c[2]), MIN_TEMPERATURE_C, MAX_TEMPERATURE_C))

            self.serial_port.reset_input_buffer()
            self.serial_port.write(tx_electrodes)
            self.serial_port.write(self.control_data_out)
            self.serial_port.flush()

            response = self._read_exact(NUM_CONTROL_IN_BYTES, read_timeout_ms / 1000.0)
            self.control_data_in[:] = bytes(NUM_CONTROL_IN_BYTES)
            self.control_data_in[: len(response)] = response

            self._last_write_time = now
            self._last_telemetry = self._decode_telemetry(bytes(response))
            return self._last_telemetry

    def _read_exact(self, n_bytes: int, timeout_s: float) -> bytes:
        deadline = time.monotonic() + float(timeout_s)
        chunks = bytearray()

        while len(chunks) < n_bytes and time.monotonic() < deadline:
            remaining = n_bytes - len(chunks)
            chunk = self.serial_port.read(remaining)
            if chunk:
                chunks.extend(chunk)
                continue
            time.sleep(0.001)

        return bytes(chunks)

    @staticmethod
    def _encode_electrodes(channel_mask: np.ndarray) -> bytes:
        """
        OpenDrop expects 18 bytes, each composed from 8 channels:
        send_value = (send_value << 1) + channel[(7-y) + x*8].
        """
        if channel_mask.shape[0] != NUM_ELECTRODES:
            raise ValueError(f"Expected {NUM_ELECTRODES} channels, got {channel_mask.shape[0]}.")

        out = bytearray(NUM_ELECTRODE_BYTES)
        for x in range(NUM_ELECTRODE_BYTES):
            send_value = 0
            for y in range(8):
                idx = (7 - y) + x * 8
                send_value = (send_value << 1) + int(bool(channel_mask[idx]))
            out[x] = send_value
        return bytes(out)

    @staticmethod
    def _decode_telemetry(control_data_in: bytes) -> dict:
        """
        Parse controller response based on OpenDropController4_25.pde:
        - bytes [0:16] feedback bitmasks for 128 channels
        - bytes [17:22] temperatures (fraction/int split)
        - byte [23] board id
        """
        n = len(control_data_in)
        feedback_mask = np.zeros(NUM_ELECTRODES, dtype=bool)
        feedback_bytes_count = min(16, n)

        for x in range(feedback_bytes_count):
            read_data = control_data_in[x]
            for y in range(8):
                idx = (7 - y) + x * 8
                feedback_mask[idx] = bool((read_data >> y) & 0x01)

        temperature_1 = None
        temperature_2 = None
        temperature_3 = None
        if n >= 23:
            temperature_1 = (control_data_in[17] / 100.0) + control_data_in[18]
            temperature_2 = (control_data_in[19] / 100.0) + control_data_in[20]
            temperature_3 = (control_data_in[21] / 100.0) + control_data_in[22]

        board_id = int(control_data_in[23]) if n >= 24 else None
        connected = n >= 16
        return {
            "connected": connected,
            "board_id": board_id,
            "feedback_mask": feedback_mask,
            "temperature_1": temperature_1,
            "temperature_2": temperature_2,
            "temperature_3": temperature_3,
            "raw_response_len": n,
        }
