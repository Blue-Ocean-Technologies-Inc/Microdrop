# Standard library imports.
import random
import threading
import collections
import re
import struct
import time
import ctypes
import logging
from typing import Callable
from pathlib import Path
from enum import IntEnum

# Third-party imports.
import serial
import numpy as np
from tqdm import tqdm

# Local imports.
from .commands import Frame, MotorBoard, SignalBoard, Alarms

log = logging.getLogger(__name__)

# Response index where motor/mechanism status byte is located
MOTOR_STATUS_INDEX = 11


class _Busy:
    """Singleton sentinel: the board REFUSED the command (RESP_BUSY).

    [review 2026-08-31, A10] Never a valid payload (payloads are bytes), so it
    can be parked in response_map / returned from _wr_locked without colliding
    with a real reply. `_wr` maps it back to None for backward compatibility
    and records a per-thread mark that take_busy() drains, so BUSY stays a
    falsy no-reply at every existing call site while the worker and the log
    pane can report it honestly instead of as a timeout.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "BUSY"

    def __bool__(self) -> bool:
        return False


BUSY = _Busy()


class _Pending:
    """One outstanding request, keyed by (cmd, cmd_idx).

    [review 2026-08-31, A11] Replies used to be matched by command id ALONE
    (`response_map[cmd] = data`), so a reply arriving after its requester gave
    up was handed to the NEXT request for that command id, however unrelated.
    Measured: request 1 times out at 0.4 s, its reply lands at 0.45 s, request
    2 issued at 0.42 s returns request 1's payload in 54 ms. Live surfaces
    included motor_position_query (wrong axis position, silently), every
    30-60 s motion command (second move reports instantly complete while the
    axis has not moved), the 1 Hz STATUS poll (permanently one frame stale)
    and the params family (the field-observed pogo-params corruption).

    The wire already carries everything needed to match exactly and always
    has -- the firmware echoes the request's cmd_idx on EVERY reply:
      * `_frame.c:182`  msg->cmd_idx = SWAP_UINT16(frame->cmd_idx)  (RX)
      * `_frame.c:694-706`  the whole request struct, cmd_idx included, is
        memcpy'd into the reply before dlen/data/ftype are overwritten
      * `_frame.c:235`  frame->cmd_idx = SWAP_UINT16(msg->cmd_idx) -- the
        echo, deliberately NOT the board's own auto-incremented msg_idx
      * `_frame.c:575-627`  CAN routing forwards frames byte-for-byte in both
        directions, so a motor-board reply routed through the MCU reaches us
        with our original cmd_idx intact
    and this host has always allocated cmd_idx uniquely per frame under
    idx_lock (`_make_cmd_packet`). So the aliasing was purely a host-side
    matching bug, and the fix needs no firmware change.

    Fields:
      event    set once the request is resolved (reply, FAIL or BUSY)
      value    payload bytes on success; None on RESP_FAIL
      busy     the board REFUSED the command (RESP_BUSY -- terminal, see A10)
      failed   RESP_FAIL
      short    last RESP_OK payload shorter than `min_len`, kept as a fallback
      min_len  resolve only on a reply of at least this many bytes; used for
               commands whose real answer follows an immediate empty ACK
      progress a "still working" signal (matching ACK_OK, or a device-pushed
               REQ on the same cmd) arrived; consumed once by the waiter to
               extend its deadline, exactly as the old marker scheme did
    """

    __slots__ = ("event", "value", "busy", "failed", "short", "min_len",
                 "progress", "cmd", "cmd_idx")

    def __init__(self, cmd: int, cmd_idx: int, min_len: int = 0) -> None:
        self.event = threading.Event()
        self.value = None
        self.busy = False
        self.failed = False
        self.short = None
        self.min_len = min_len
        self.progress = False
        self.cmd = cmd
        self.cmd_idx = cmd_idx

# --- 200-channel expansion command IDs (see docs/SPEC_200_CHANNEL_IMPL.md) ---
# Not present in commands_generated.py/proxy.py yet (those are auto-regenerated
# by the MCU firmware build); defined here directly, same convention as the
# existing raw-ID usage in measureCapacitanceFull (0x122F).
CMD_BOARD_CHANNELS_GET = 0x1240        # no payload -> [u16 BE channels, u8 n_chips]
CMD_BOARD_CHANNELS_SET = 0x1241        # [u16 BE channels] -> echo [u16 BE channels]
CMD_ELECTRODE_STATE_CH = 0x1242        # channel bitmap (N+7)//8 bytes, LSB-first -> [u8 status]
CMD_ELECTRODE_STATE_READ_CH = 0x1243   # no payload -> channel bitmap (N+7)//8 bytes, LSB-first
CMD_SHORT_DETECT_CH = 0x1244           # [u8 n, ch0..chn-1] (n=0 -> all N) -> [u8 n_shorted, ch...]

# Per-channel capacitance without altering HV/frequency (existing firmware
# command, not new to the 200-channel expansion, but its usage here is
# chunk-bounded by the ZGSW response frame limit: ZGSW_MSG_MAX_SIZE=128
# bytes, silently dropped by __zgsw_transmit if exceeded. Subset request
# [u8 n, ch0..chn-1] (1<=n<=31, so reply 1+31*4=125 <= 128) -> reply
# [u8 n, n x float32 BE pF]. n=0 (all-channel) mode replies [u8 pF]*N and
# only fits within 128 bytes for N<=120 -- not used here for N>120.
CMD_CHANNEL_CAPACITANCES = 0x1235

# Legacy electrode-state read command (16-byte chain-packed). Not in
# commands.py; matches proxy.py's ELECTRODE_STATE_READ = 0x1220. NOTE: the
# older text in docs/SPEC_200_CHANNEL_IMPL.md mentioning 0x1227 for this is
# stale -- 0x1227 is CMD_PMT_ACQUIRE_START, unrelated. 0x1220 is confirmed
# correct against commands_generated.py / proxy.py.
CMD_ELECTRODE_STATE_READ = 0x1220

# --- I2: configurable UART baud (see docs/PLAN_SPEED_IMPROVEMENTS.md; coded
# against the documented wire contract -- implemented on the firmware side
# in parallel, not necessarily what a given connected board currently runs).
CMD_APP_BAUD_GET = 0x1246  # no payload -> [u32 BE baud]
CMD_APP_BAUD_SET = 0x1247  # [u32 BE baud] (whitelist, else RESP_FAIL) -> echo
                            # [u32 BE baud]. Reply is sent at the CURRENT
                            # baud; the new baud only takes effect after the
                            # board reboots (persisted to EEPROM/EasyFlash).
APP_BAUD_WHITELIST = (115200, 230400, 460800, 921600)

# --- I5: persistent cap calibration keyed by board UID (see
# docs/PLAN_SPEED_IMPROVEMENTS.md) ---
CMD_READ_UID = 0x1245  # no payload -> 12 raw bytes (STM32 factory UID)

# --- I4: 0x1232 stream collector (see docs/PLAN_SPEED_IMPROVEMENTS.md) ---
# ROUTE_POWER_CMD (existing firmware command, applications/user.h). During a
# CAP_READ_ALL (0x1232) scan the firmware streams one packet per channel as
# it's measured -- payload [u8 total, u8 idx_1based, u8 cap_pf] -- because the
# scan's own final summary reply cannot fit the 128-byte ZGSW frame limit on
# boards with board_channels > 120. See readAllChannels / _collect_cap_stream.
ROUTE_POWER_CMD = 0x112A

# For parsing status responses
class SysStatusMotorBoard(ctypes.Structure):
    """Motor board status: rst, cabin, mag, flu, lpush, rpush, pmt."""
    _fields_ = [("rst", ctypes.c_uint8),
                ("cabin", ctypes.c_uint8),
                ("mag", ctypes.c_uint8),
                ("flu", ctypes.c_uint8),
                ("lpush", ctypes.c_uint8),
                ("rpush", ctypes.c_uint8),
                ("pmt", ctypes.c_uint8)]

    def to_dict(self):
        fields = {field[0]: getattr(self, field[0]) for field in self._fields_}
        return fields

    def __repr__(self):
        items = ', '.join(f'{k}={v}' for k, v in self.to_dict().items())
        return f"SysStatusMotorBoard({items})"


class SysStatusSignalBoard(ctypes.BigEndianStructure):
    """Signal board status: 18 uint16 fields covering temp, HV, LEDs, cap, etc."""
    _fields_ = [("cur_temp", ctypes.c_uint16),
                ("target_temp", ctypes.c_uint16),
                ("out_power", ctypes.c_uint16),
                ("box_led_state", ctypes.c_uint16),
                ("light_led_bright", ctypes.c_uint16),
                ("flu_led_bright", ctypes.c_uint16),
                ("chip_on_pad", ctypes.c_uint16),
                ("chip_cap", ctypes.c_uint16),
                ("chip_shorts", ctypes.c_uint16),
                ("chip_res", ctypes.c_uint16),
                ("dev_temp", ctypes.c_uint16),
                ("dev_hum", ctypes.c_uint16),
                ("fan_duty", ctypes.c_uint16),
                ("pmt", ctypes.c_uint16),
                ("hv_vol", ctypes.c_uint16),
                ("hv_freq", ctypes.c_uint16),
                ("cap_match", ctypes.c_uint16),
                ("temp_onoff", ctypes.c_uint16)  # [E3] tempctrl on/off
                ]

    def to_dict(self):
        fields = {field[0]: getattr(self, field[0]) for field in self._fields_}
        fields['cur_temp'] = fields['cur_temp'] / 100.0
        fields['target_temp'] = fields['target_temp'] / 100.0
        fields['hv_vol'] = fields['hv_vol'] / 100.0
        fields['dev_temp'] = fields['dev_temp'] / 100.0
        fields['dev_hum'] = fields['dev_hum'] / 100.0
        fields['chip_shorts'] = fields['chip_shorts'] == 1
        fields['chip_on_pad'] = fields['chip_on_pad'] == 1
        box_led_state = {0: "off", 1: "red", 2: "green", 3: "yellow"}
        fields['box_led_state'] = box_led_state.get(fields['box_led_state'], f"unknown({fields['box_led_state']})")
        return fields

    def __repr__(self):
        return f"SysStatusSignalBoard({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class ProductModel(ctypes.BigEndianStructure):
    """Product model configuration: model_id, pmt_motor, magnet_endstop_location."""
    _fields_ = [("model_id", ctypes.c_int32),
                ("pmt_motor", ctypes.c_uint32),
                ('magnet_endstop_location', ctypes.c_uint32),
                ]

    @classmethod
    def from_dynamic_buffer(cls, data):
        required_size = ctypes.sizeof(cls) # Should be 12 bytes
        input_len = len(data)

        if input_len < required_size:
            # Create a mutable copy of the data
            padded_data = bytearray(data)
            # Append zeros to fill the missing space
            # This sets missing values to FF
            padded_data.extend(b'\xFF' * (required_size - input_len))
            return cls.from_buffer_copy(padded_data)

        # If size is correct, just read it normally
        return cls.from_buffer_copy(data)

    def to_dict(self):
        fields = {field[0]: getattr(self, field[0]) for field in self._fields_ if getattr(self, field[0]) != 0xFFFFFFFF}
        if fields.get('pmt_motor') is not None:
            fields['pmt_motor'] = fields['pmt_motor'] == 1
        if fields.get('magnet_endstop_location') is not None:
            fields['magnet_endstop_location'] = 'down' if fields['magnet_endstop_location'] == 1 else 'up'
        return fields

    def __repr__(self):
        return f"ProductModel({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class TempCalibMode(IntEnum):
    CALIB_MODE_NONE = 0
    CALIB_MODE_LINEAR = 1
    CALIB_MODE_QUADRATIC = 2
    CALIB_MODE_PIECEWISE = 3


class LinearParams(ctypes.BigEndianStructure):
    _fields_ = [("k", ctypes.c_float),
                ("b", ctypes.c_float)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}

    def __repr__(self):
        return f"LinearParams({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class QuadraticParams(ctypes.BigEndianStructure):
    _fields_ = [("a", ctypes.c_float),
                ("b", ctypes.c_float),
                ("c", ctypes.c_float)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}

    def __repr__(self):
        return f"QuadraticParams({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class TempCalibration(ctypes.BigEndianStructure):
    _fields_ = [
        ("mode", ctypes.c_int),          # Enum is essentially an int
        ("enable", ctypes.c_uint32),
        ("linear", LinearParams),        # Reference the class defined above
        ("quadratic", QuadraticParams)   # Reference the class defined above
    ]

    def to_dict(self):
        return {
            "mode": getattr(self, "mode"), # Could map to TempCalibMode(self.mode).name
            "enable": bool(self.enable),   # Convert 1/0 to True/False if desired
            "linear": self.linear.to_dict(),
            "quadratic": self.quadratic.to_dict()
        }

    def __repr__(self):
        return f"TempCalibration({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class TempCtrlParams(ctypes.BigEndianStructure):
    _fields_ = [
        ("temp_kp", ctypes.c_float),
        ("temp_ki", ctypes.c_float),
        ("temp_kd", ctypes.c_float),
        ("temp_offset", ctypes.c_float),
        ("temp_t", ctypes.c_int32),
        ("calibration", TempCalibration) # Nested struct
    ]

    def to_dict(self):
        fields = {field[0]: getattr(self, field[0]) for field in self._fields_ if field[0] != 'calibration'}
        # Recursively call to_dict on the nested structure
        fields['calibration'] = self.calibration.to_dict()
        return fields


class AdcData(ctypes.BigEndianStructure):
    _fields_ = [("CH0", ctypes.c_uint16),
                ("CH1", ctypes.c_uint16),
                ("CH2", ctypes.c_uint16),
                ("CH3", ctypes.c_uint16),
                ("CH4", ctypes.c_uint16),
                ("CH5", ctypes.c_uint16),
                ("CH6", ctypes.c_uint16),
                ("CH7", ctypes.c_uint16)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) / 100.0 for field in self._fields_}

    def __repr__(self):
        return f"AdcData({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class CapacitanceMeasurement(ctypes.BigEndianStructure):
    """Result of CMD_MEASURE_CAPACITANCE (0x122F): 21 bytes, big-endian.

    Fields (firmware measure_capacitance_server):
        cap_pf      measured capacitance in pF (DropBot formula)
        proportion  high/total sample proportion (signal quality, 0..1)
        mode        measurement mode flag
        n_total     total samples taken
        n_high      samples above mid-rail
        n_low       samples below mid-rail
        n_dropped   samples discarded
        elapsed_us  measurement duration in microseconds
    """
    _pack_ = 1
    _fields_ = [("cap_pf", ctypes.c_float),
                ("proportion", ctypes.c_float),
                ("mode", ctypes.c_uint8),
                ("n_total", ctypes.c_uint16),
                ("n_high", ctypes.c_uint16),
                ("n_low", ctypes.c_uint16),
                ("n_dropped", ctypes.c_uint16),
                ("elapsed_us", ctypes.c_uint32)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}

    def __repr__(self):
        return f"CapacitanceMeasurement({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class MagnetParams(ctypes.BigEndianStructure):
    _fields_ = [("z_up", ctypes.c_int32),
                ("z_down", ctypes.c_int32),
                ("y_0", ctypes.c_int32),
                ("y_space", ctypes.c_int32)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}

    def __repr__(self):
        return f"MagnetParams({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class PMTPositionParams(ctypes.BigEndianStructure):
    _fields_ = [("pos", ctypes.c_int32 * 5)]

    def to_dict(self):
        return {f"pmt_pos_{i}": val for i, val in enumerate(list(self.pos))}

    def __repr__(self):
        return f"PMTPositionParams({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class FilterPositionParams(ctypes.BigEndianStructure):
    _fields_ = [("pos", ctypes.c_int32 * 5)]

    def to_dict(self):
        return {f"filter_pos_{i}": val for i, val in enumerate(list(self.pos))}

    def __repr__(self):
        return f"FilterPositionParams({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class TrayPositionParams(ctypes.BigEndianStructure):
    _fields_ = [("out_pos", ctypes.c_int32),
                ("mag_pos", ctypes.c_int32),
                ("in_pos", ctypes.c_int32)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}

    def __repr__(self):
        return f"TrayPositionParams({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class HeaterPositionParams(ctypes.BigEndianStructure):
    _fields_ = [("z_pos", ctypes.c_int32),
                ("y_pos", ctypes.c_int32)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}

    def __repr__(self):
        return f"HeaterPositionParams({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class MotorPositionParams(ctypes.BigEndianStructure):
    """The `_mt_*_dp` mechanical blob: 6 floats + 11 int32, 68 bytes.

    [review 2026-08-31, L3] This was still the 56-byte, 14-field generation
    (ctypes.sizeof == 56). Because from_buffer_copy TOLERATES an oversized
    source, getBoardParameters silently discarded acc_run / acc_rst /
    stealthchop from every 68-byte read with no error at all, while
    motor_params_tab.py's own struct format was already correct -- so the two
    consumers of the same wire bytes disagreed about how many fields exist.

    Read it with from_dynamic_buffer(), never from_buffer_copy(): the two
    older firmware generations really do serve 56 and 64 byte blobs and
    from_buffer_copy raises on a short source.
    """
    _pack_ = 1
    _fields_ = [("lower_limit_position", ctypes.c_float),
                ("upper_limit_position", ctypes.c_float),
                ("lead_per_revolution", ctypes.c_float),
                ("origin_offset", ctypes.c_float),
                ("origin_area", ctypes.c_float),
                ("single_step_length", ctypes.c_float),
                ("direction", ctypes.c_int32),
                ("holding_current", ctypes.c_int32),
                ("moving_current", ctypes.c_int32),
                ("microstepping", ctypes.c_int32),
                ("moving_stallguard_threshold", ctypes.c_int32),
                ("homing_stallguard_threshold", ctypes.c_int32),
                ("homing_speed", ctypes.c_int32),
                ("moving_speed", ctypes.c_int32),
                # 2026-08-01 (56 -> 64 B): accel/decel ramp factors.
                ("acc_run", ctypes.c_int32),
                ("acc_rst", ctypes.c_int32),
                # 2026-08-28 (64 -> 68 B): per-axis StealthChop enable.
                ("stealthchop", ctypes.c_int32)]

    # What older firmware effectively runs for the fields it does not send,
    # matching full_test_ui/tabs/motor_params_tab.py's _MOTOR_PAD_DEFAULTS.
    _LEGACY_DEFAULTS = {"acc_run": 6, "acc_rst": 6, "stealthchop": 0}
    _KNOWN_SIZES = (56, 64, 68)

    @classmethod
    def from_dynamic_buffer(cls, data: bytes) -> "MotorPositionParams":
        """Decode a 56, 64 or 68 byte blob, padding legacy tails. [L3]"""
        size = ctypes.sizeof(cls)
        if len(data) >= size:
            return cls.from_buffer_copy(data[:size])
        if len(data) not in cls._KNOWN_SIZES:
            raise ValueError(
                f"{len(data)} B is not a known motor param blob size "
                f"{cls._KNOWN_SIZES}")
        padded = bytearray(data)
        # Field names in wire order; pad only the ones the board omitted.
        tail = [n for n, _ in cls._fields_][-((size - len(data)) // 4):]
        for name in tail:
            padded += struct.pack(">i", cls._LEGACY_DEFAULTS.get(name, 0))
        return cls.from_buffer_copy(bytes(padded))

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}

    def __repr__(self):
        return f"MotorPositionParams({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"


class Motor():
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
        self._opto_sensors = (False, False)
        self._position = 0
        self._speed = 0
        self._direction = 0
        self._status = 0
        self._error = None

    def __repr__(self):
        return f"Motor(id={self.id}, name={self.name!r}, pos={self._position}, spd={self._speed}, err={self._error})"

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'opto_sensors': self._opto_sensors,
            'position': self._position,
            'speed': self._speed,
            'direction': self._direction,
            'status': self._status,
            'error': self._error
        }

    @property
    def opto_sensors(self):
        return self._opto_sensors

    @opto_sensors.setter
    def opto_sensors(self, opto_sensors: tuple[bool, bool]):
        self._opto_sensors = (bool(opto_sensors[0]), bool(opto_sensors[1]))

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, position: int):
        self._position = position

    @property
    def speed(self):
        return self._speed

    @speed.setter
    def speed(self, speed: int):
        self._speed = speed

    @property
    def direction(self):
        return self._direction

    @direction.setter
    def direction(self, direction: int):
        self._direction = direction

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, status: int):
        if status == 0:
            status = "Normal"
        elif status == -7:
            status = "Busy"
        elif status == -6:
            status = "Stuck"
        elif status == -2:
            status = "Move Timed Out"
        elif status == -1:
            status = "Not Homed"
        else:
            if status == -101:
                error = "Chip Error"
            elif status == -102:
                error = "A/B Coil Not Connected"
            elif status == -103:
                error = "A/B Coil Shorted"
            elif status == -104:
                error = "Over Temperature Warning"
            elif status == -105:
                error = "Over Temperature"
            elif status == -106:
                error = "Power Short Circuit"
            elif status == -9:
                error = "Home Signal Not Triggered"
            elif status == -8:
                error = "Home Signal Triggered Continuously"
            elif status == -5:
                error = "Motor Over Forward Limit"
            elif status == -4:
                error = "Motor Over Reverse Limit"
            elif status == -3:
                error = "Motor Position Error"
            else:
                error = "Unknown Error"
            self._error = error
            self._status = "Error"
            return
        self._status = status
        self._error = None

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, error: int):
        self._error = error


class Motors():
    def __init__(self):
        self.motors = [
            Motor(0, 'tray'),
            Motor(1, 'pmt'),
            Motor(2, 'magnet'),
            Motor(3, 'filter'),
            Motor(4, 'pogo_left'),
            Motor(5, 'pogo_right')
        ]

    def to_dict(self):
        return {motor.id: motor.to_dict() for motor in self.motors}

    def get_motor(self, id: int):
        return self.motors[id]

    def get_motor_by_name(self, name: str):
        return next((motor for motor in self.motors if motor.name == name), None)

    def get_motor_by_id(self, id: int):
        return self.motors[id]

    @property
    def tray(self):
        return self.get_motor(0)

    @property
    def pmt(self):
        return self.get_motor(1)

    @property
    def magnet(self):
        return self.get_motor(2)

    @property
    def filter(self):
        return self.get_motor(3)

    @property
    def pogo_left(self):
        return self.get_motor(4)

    @property
    def pogo_right(self):
        return self.get_motor(5)

    def opto_sensors(self):
        return {motor.name: motor.opto_sensors for motor in self.motors}

    def positions(self):
        return {motor.name: motor.position for motor in self.motors}

    def speeds(self):
        return {motor.name: motor.speed for motor in self.motors}

    def directions(self):
        return {motor.name: motor.direction for motor in self.motors}

    def statuses(self):
        return {motor.name: motor.status for motor in self.motors}

    def errors(self):
        return {motor.name: motor.error for motor in self.motors}


class _CapStreamAssembler:
    """Assembles a CAP_READ_ALL (0x1232) per-channel packet stream.

    Pure state machine, no I/O -- feed() is called once per received
    ROUTE_POWER_CMD packet (payload [u8 total, u8 idx_1based, u8 cap_pf]).
    Kept standalone (no DropletBotUart dependency) so the assembly logic is
    directly unit-testable. See DropletBotUart._collect_cap_stream for the
    threaded collector that drives this from live packets.
    """

    def __init__(self, expected_total: int):
        self.expected_total = expected_total
        self.buffer = bytearray(expected_total)
        self.seen: set[int] = set()

    def feed(self, total: int, idx_1based: int, cap_pf: int) -> bool:
        """Record one packet.

        `total` is trusted only for logging/diagnostics -- the assembler
        always sizes against `expected_total` (queried moments before the
        scan via CMD_BOARD_CHANNELS_GET), since a mismatched `total` from a
        stray/corrupt packet must not resize the buffer mid-collection.

        Returns:
            True if this packet set a previously-unseen channel index within
            range; False for a duplicate or an out-of-range index (ignored).
        """
        idx0 = idx_1based - 1
        if not (0 <= idx0 < self.expected_total):
            return False
        is_new = idx0 not in self.seen
        self.seen.add(idx0)
        self.buffer[idx0] = max(0, min(255, cap_pf))
        return is_new

    @property
    def n_received(self) -> int:
        return len(self.seen)

    def is_complete(self) -> bool:
        return len(self.seen) >= self.expected_total

    def to_bytes(self) -> bytes:
        return bytes(self.buffer)


# --- PMT multi-packet upload ------------------------------------------------
# [WP-PMT 2026-08-28] Protocol facts, read off the firmware
# (firmware/MCU/applications/business/pmt.c: upload_adc128_data(), the
# PMT_SAMPLING_DONE_EVT branch of pmt_simple_entry(), and
# pmt_debug_upload_server()), not guessed:
#
#   * Every uploaded frame is exactly PMT_PACKET_SIZE = 128 payload bytes:
#         [total_packets u16 LE][packet_idx u16 LE][124 B = 62 samples u16 LE]
#     packet_idx counts 0 .. total_packets-1; the LAST packet is zero-PADDED
#     to the full 124 B (rt_memset in upload_adc128_data), so the padding is
#     indistinguishable from genuine zero samples -- the sample count has to
#     come from elsewhere (see sample_limit below).
#   * total_packets = ceil(total_samples*2 / 124), and is repeated in EVERY
#     packet header -- so the stream is self-describing: the completion
#     criterion is "every index 0..total_packets-1 seen", with total_packets
#     taken from the packet headers themselves (cross-checked against the
#     command's own reply when one is available).
#   * The frames are sent with zgsw_rep_notry(..., ZGSW_FT_RESP_OK, ...) --
#     i.e. they arrive as RESP_OK frames, NOT as unsolicited REQ frames.
#     RESP_OK is exactly the path that writes response_map[cmd] (see
#     _process_thread_fn), which is why the plain _wr() path only ever sees
#     the LAST packet: each packet overwrites the previous one under the same
#     cmd key. RESP_OK also reaches _dispatch(), so subscribe(cmd, cb) sees
#     every packet -- that is the hook this collector uses.
#   * Which cmd the packets carry depends on the path:
#       - acquire (CMD_PMT_ACQUIRE_START 0x1227): the 2-byte [packet_count
#         u16 LE] reply comes back on 0x1227 when sampling COMPLETES (~10.3 s
#         for the full 10240-sample buffer), and the packets then arrive on
#         CMD_PMT_DATA_REPORT 0x1228 (declared `unsolicited: true` in
#         commands.yaml).
#       - debug upload (CMD_PMT_DATA_UPLOAD_DEBUG 0x122E): BOTH the 2-byte
#         packet-count reply AND the 128-byte packets arrive on 0x122E. They
#         are told apart by length (2 vs 128), which is also why the generic
#         _wr() reply for that command is unreliable (a packet can win the
#         race and be returned as if it were the count).
#   * Packets are paced by rt_thread_mdelay(50) -- ~50 ms apart, so a full
#     10240-sample acquisition is 166 packets ~= 8.3 s of upload.
PMT_PACKET_SIZE = 128
PMT_PACKET_HEADER_BYTES = 4
PMT_SAMPLES_PER_PACKET = (PMT_PACKET_SIZE - PMT_PACKET_HEADER_BYTES) // 2  # 62
# firmware ADC_BUFFER_SIZE (pmt.c) -- a completed acquire always fills it.
PMT_ACQUIRE_BUFFER_SAMPLES = 10 * 1024


class PmtCapture:
    """Result of a multi-packet PMT upload (see DropletBotUart.pmt_*_collect).

    Always returned, complete or not: `complete` says whether every expected
    packet arrived, and `n_received`/`n_expected` + `missing` describe the
    partial result. Truthy even when incomplete (the worker layer treats
    None/False as "no reply", and a partial capture IS a reply).
    """

    def __init__(self, samples: list[int], n_received: int, n_expected: int,
                 missing: list[int], aborted: bool = False, busy: bool = False,
                 error: str | None = None, elapsed_s: float = 0.0):
        self.samples = samples
        self.n_received = n_received
        self.n_expected = n_expected
        self.missing = missing
        self.aborted = aborted
        self.busy = busy
        self.error = error
        self.elapsed_s = elapsed_s

    @property
    def complete(self) -> bool:
        return (self.error is None and not self.aborted
                and self.n_expected > 0 and self.n_received >= self.n_expected)

    def summary(self) -> str:
        bits = [f"{self.n_received}/{self.n_expected} packets",
                f"{len(self.samples)} samples", f"{self.elapsed_s:.1f}s"]
        if self.error:
            bits.append(f"ERROR: {self.error}")
        if self.busy:
            bits.append("device BUSY")
        if self.aborted:
            bits.append("ABORTED")
        if self.missing:
            shown = ",".join(str(i) for i in self.missing[:8])
            more = "..." if len(self.missing) > 8 else ""
            bits.append(f"missing idx [{shown}{more}]")
        return "  ".join(bits)

    def __repr__(self) -> str:
        return f"PmtCapture({self.summary()})"


class _PmtPacketAssembler:
    """Assembles a PMT 128-byte upload packet stream (pure state machine).

    No I/O and no DropletBotUart dependency, so the assembly/completion logic
    is directly unit-testable; DropletBotUart._collect_pmt_packets drives it
    from live subscriber callbacks.
    """

    def __init__(self, expected_total: int | None = None):
        self.expected_total: int | None = expected_total
        self.packets: dict[int, tuple] = {}
        self._total_mismatch_logged = False

    def set_expected(self, total: int) -> None:
        """Record the packet count reported by the command's own reply."""
        if total > 0:
            self.expected_total = total

    def feed(self, data: bytes) -> bool:
        """Record one 128-byte upload packet.

        Returns True if this was a new, in-range packet; False for a short
        frame, a duplicate index, or an out-of-range index.
        """
        if len(data) < PMT_PACKET_HEADER_BYTES + 2:
            return False
        total, idx = struct.unpack('<HH', data[:PMT_PACKET_HEADER_BYTES])
        if total == 0:
            return False
        if self.expected_total is None:
            self.expected_total = total
        elif total != self.expected_total:
            # Trust the LARGER of the two so a stale/short count can never
            # truncate a real upload; the count reply and the packet headers
            # come from the same firmware computation, so this is diagnostic.
            if not self._total_mismatch_logged:
                log.warning(f"PMT upload: packet header total={total} disagrees "
                            f"with expected={self.expected_total}")
                self._total_mismatch_logged = True
            self.expected_total = max(total, self.expected_total)
        if not (0 <= idx < self.expected_total) or idx in self.packets:
            return False
        payload = data[PMT_PACKET_HEADER_BYTES:PMT_PACKET_HEADER_BYTES + 2 * PMT_SAMPLES_PER_PACKET]
        n = len(payload) // 2
        self.packets[idx] = struct.unpack(f'<{n}H', payload[:2 * n])
        return True

    @property
    def n_received(self) -> int:
        return len(self.packets)

    def is_complete(self) -> bool:
        return (self.expected_total is not None
                and len(self.packets) >= self.expected_total)

    def missing(self) -> list[int]:
        if not self.expected_total:
            return []
        return [i for i in range(self.expected_total) if i not in self.packets]

    def to_samples(self, sample_limit: int | None = None) -> list[int]:
        """Flatten to one sample list in packet-index order.

        A missing packet contributes PMT_SAMPLES_PER_PACKET zeros so later
        packets keep their true sample offsets (the gap is reported through
        `missing()`, not silently closed up).

        `sample_limit`, when known, trims the zero padding the firmware adds
        to the last packet -- that padding cannot be detected from the data
        itself (see the protocol notes above).
        """
        out: list[int] = []
        for i in range(self.expected_total or 0):
            values = self.packets.get(i)
            out.extend(values if values is not None
                       else (0,) * PMT_SAMPLES_PER_PACKET)
        if sample_limit is not None and 0 <= sample_limit < len(out):
            out = out[:sample_limit]
        return out


class DropletBotUart:
    def __init__(self):
        self.serial = None
        self.is_running = False
        self._crc_table = self._generate_crc_table()

        # This replaces SnRingBuffer. A deque is thread-safe for appends/pops.
        self.byte_buffer = collections.deque()
        self.buffer_lock = threading.Lock()

        # This replaces the QMap<quint32, QByteArray> dataList
        # It holds responses, keyed by command ID
        self.response_map = {}
        self.response_lock = threading.Lock()

        # Serializes serial writes. The RX thread ACKs device frames while
        # caller threads send commands; pyserial's write() is not atomic
        # across threads, so two interleaved writes can splice one packet
        # into another.
        self.tx_lock = threading.Lock()
        self.idx_lock = threading.Lock()  # msg_idx/cmd_idx allocation (two lanes build packets concurrently)

        # [WP-LANES] Per-command in-flight guard. Pending replies are keyed by
        # command id (response_map), so two concurrent _wr() calls for the SAME
        # cmd would race for one another's reply -- the second call also clears
        # the first's markers on entry. The UI now drives this transport from
        # two lane threads, so serialize per cmd id: a second _wr() on the same
        # cmd BLOCKS until the first resolves, then proceeds normally.
        # RLock, not Lock, so a same-thread re-entrant call behaves exactly as
        # it did before (single-threaded behaviour is unchanged; an uncontended
        # acquire is ~100 ns).
        self._cmd_locks = {}  # cmd id -> threading.RLock
        self._cmd_locks_guard = threading.Lock()

        # [review 2026-08-31, A11] Replies matched by (cmd, cmd_idx) -- see
        # _Pending and _wr_locked_by_idx. response_map above is the legacy
        # cmd-id-only table, still written by the RX thread and still read by
        # _wr_locked_legacy for the handful of callers that hand _wr a buffer
        # that is not a frame this transport built.
        self._pending: dict[tuple[int, int], "_Pending"] = {}
        self._pending_lock = threading.Lock()
        # Per-thread "the board REFUSED this command" marker, drained by
        # take_busy(). See _Pending.busy / A10.
        self._busy_marks: dict[int, tuple[int, float]] = {}

        # Threads
        self.listen_thread = None
        self.process_thread = None
        self.msg_idx = 0

        self.cmd_idx = random.randint(0, 0xFFFF)  # randomize to avoid duplicate rejection on reconnect

        # --- Callbacks to replace Qt Signals ---
        self.on_ready_read = None  # e.g., on_ready_read(cmd, data)
        self.on_error = None       # e.g., on_error(err_code, cmd_str)
        self.on_alarm = None       # e.g., on_alarm(alarms)

        self.time_buffer = b''
        self.sig_board_connected = False
        self.motor_board_connected = False
        # [WP-L] board -> "module;hw;sw" identity echoed in the login reply
        # by firmware >= 2026-08-27 (empty until a login sees one).
        self.login_identity: dict = {}

        self.motors = Motors()

        # Board-channels cache (see _query_board_channels / board_channels
        # property). None until queried; queried automatically after a
        # successful signal-board login, or lazily on first property access.
        self._board_channels: int | None = None
        self._board_n_chips: int | None = None
        # True once we know the firmware predates the 200-channel commands
        # (0x1240 query failed, or a 0x1242/0x1243 attempt timed out). Lets
        # setElectrodeStates/getElectrodeStates skip the 2 s new-command
        # timeout and go straight to the legacy protocol on old firmware.
        self._legacy_fw: bool = False

        # Cached STM32 factory UID (lowercase hex string), see read_uid().
        self._uid_hex: str | None = None

        # Lightweight cmd -> callback subscription mechanism, alongside
        # on_ready_read (see _dispatch). Used by _collect_cap_stream to
        # catch ROUTE_POWER_CMD packets streamed during a CAP_READ_ALL scan
        # without disturbing normal _wr()/response_map request matching.
        self._subscribers: dict[int, Callable[[int, bytes], None]] = {}
        self._subscribers_lock = threading.Lock()

    def init(self, port, baudrate):
        """Opens the serial port and starts the background threads."""
        try:
            self.serial = serial.Serial(port, baudrate, timeout=0.1)
            self.is_running = True

            # Start the listener thread (Producer)
            self.listen_thread = threading.Thread(
                target=self._listen_thread_fn)
            self.listen_thread.daemon = True
            self.listen_thread.start()

            # Start the processing thread (Consumer)
            self.process_thread = threading.Thread(
                target=self._process_thread_fn)
            self.process_thread.daemon = True
            self.process_thread.start()

            log.info(f"Opened {port} at {baudrate} successfully.")
            return True
        except serial.SerialException as e:
            log.error(f"Error opening serial port: {e}")
            return False

    def close(self):
        """Stops threads and closes the serial port."""
        self.is_running = False
        if self.listen_thread:
            self.listen_thread.join()
        if self.process_thread:
            self.process_thread.join()
        if self.serial and self.serial.is_open:
            self.serial.close()
            log.info("Serial port closed.")

    def init_autodetect(self, port: str, baudrate: int = 115200,
                        login_timeout_s: float = 2.0) -> tuple[bool, int]:
        """Open `port`, autodetecting the app UART baud rate if needed.

        Tries `baudrate` first (opens the port there and attempts a
        signal-board login). If that login fails -- wrong baud, garbled
        framing, or no response at all -- closes the port and retries once
        at each of the other APP_BAUD_WHITELIST rates, in whitelist order
        (115200 first among the remaining candidates, since it's the
        firmware's default for unprovisioned/legacy boards and thus the most
        likely actual rate). Stops at the first baud where BoardLogin
        succeeds; that baud is left open on return.

        This is a pure "which rate is the board currently talking at" probe
        -- it does not touch app_baud persistence. It exists because
        set_app_baud() (0x1247) persists the new rate to EEPROM but it only
        takes effect after the board reboots, so the host has no reliable
        way to know in advance which rate a given board is on right now.

        Worst-case added delay is bounded by `login_timeout_s` times the
        number of whitelisted rates (default: 2 s x 4 = 8 s), under the 10 s
        budget.

        Args:
            port: Serial device path.
            baudrate: Baud rate to try first (e.g. the last-known/expected
                rate for this board). Defaults to 115200.
            login_timeout_s: Per-attempt BoardLogin timeout.

        Returns:
            (success, baud_used). On failure at every whitelisted rate,
            success is False, baud_used is 0, and the port is left closed.
        """
        candidates = [baudrate] + [b for b in APP_BAUD_WHITELIST if b != baudrate]
        for baud in candidates:
            if not self.init(port, baud):
                continue
            # A freshly opened FTDI port + just-started listener thread need a
            # moment to settle before the first frame is exchanged; without it
            # the initial login response is missed and autodetect fails even at
            # the CORRECT baud (observed 2026-07-22). Mirror the proven bare
            # init()->sleep->login path. The first frame after open is also
            # occasionally dropped, so try the login twice before moving on.
            time.sleep(0.8)
            if (self.BoardLogin('signal', timeout_s=login_timeout_s) or
                    self.BoardLogin('signal', timeout_s=login_timeout_s)):
                log.info(f"Autodetected app UART baud: {baud}")
                return True, baud
            log.warning(f"Login failed at {baud} baud; trying next rate")
            self.close()
        log.error(f"Autodetect failed at all whitelisted rates: {APP_BAUD_WHITELIST}")
        return False, 0

    # --- Producer Thread ---
    def _listen_thread_fn(self):
        """Reads from serial and puts data into the byte_buffer."""
        log.debug("Listen thread started.")
        while self.is_running:
            try:
                if self.serial.in_waiting > 0:
                    data = self.serial.read(256)
                    if data:
                        # print(f"Received {len(data)} bytes > {data.hex(' ')}")
                        with self.buffer_lock:
                            self.byte_buffer.extend(data)
                else:
                    time.sleep(0.001)
            except serial.SerialException as e:
                log.error(f"Serial port disconnected: {e}")
                if self.on_error:
                    self.on_error(-1, "Serial port disconnected")
                self.is_running = False  # Stop on error
        log.debug("Listen thread stopped.")

    # --- Consumer Thread ---
    # [review 2026-08-31, A9] Largest frame this protocol can produce is 527 B
    # (ZGSW_MSG_MAX_SIZE 512, firmware/MCU/rtconfig.h:360, + FRAME_HEAD_SIZE
    # 11, zgsw_protocol_frame_def.h:8, + 4-byte CRC). Anything claiming more
    # than this cap is a corrupt length byte, not a big frame.
    _MAX_FRAME_BYTES = 1024
    # A plausible-but-never-completing header is dropped after this long with
    # no new bytes arriving. 527 B takes ~46 ms at 115200 baud.
    _FRAME_RESYNC_S = 2.0

    def _process_thread_fn(self):
        """
        Parses the protocol from the byte_buffer.
        This is the equivalent of your 'run()' method.
        """
        log.debug("Process thread started.")
        # [A9] resync bookkeeping for a header that never completes
        pending_since = None
        pending_len = -1
        while self.is_running:
            # --- This section finds a complete packet ---
            # This logic must be replicated *exactly* from your C++ 'run' method

            # 1. Find STX_HEAD0
            while self.is_running:
                with self.buffer_lock:
                    if not self.byte_buffer:
                        break  # Buffer is empty

                    # print(f"Checking byte: {self.byte_buffer[0]:02x} vs {Frame.HEAD0:02x} > {self.byte_buffer[0] == Frame.HEAD0}")
                    if self.byte_buffer[0] == Frame.HEAD0:  # Found header!
                        # print(f"Found header: {self.byte_buffer[0]:02x}")
                        break
                    self.byte_buffer.popleft()  # Discard byte

            if not self.is_running:
                break

            # 2. Check for full header and get length
            need_more = False
            with self.buffer_lock:
                if len(self.byte_buffer) < 4:
                    need_more = True  # Not enough data for header yet
                # Check for STX_HEAD1
                elif self.byte_buffer[1] != Frame.HEAD1:
                    self.byte_buffer.popleft()  # Bad packet, discard STX0
                    pending_since = None
                    continue
                else:
                    # Get length field (headers + data length in C++)
                    packet_len, = struct.unpack(
                        '>H', bytes(list(self.byte_buffer)[2:4]))

                    # Calculate total packet length (like C++: len + 4)
                    total_packet_len = packet_len + 4

                    if total_packet_len > self._MAX_FRAME_BYTES:
                        # [review 2026-08-31, A9] The length came straight off
                        # the wire with no sanity cap. One flipped byte made
                        # the parser wait for up to 65,539 bytes, swallowing
                        # every subsequent real frame into the same span --
                        # and if the board then went quiet (it does, because
                        # the host stopped answering) it NEVER recovered.
                        # Measured: 176 bytes stuck, 10 valid frames injected
                        # behind the corrupt header, none ever parsed, every
                        # command timing out forever with the port still open.
                        # A strong candidate for the recurring "the MCU
                        # stopped answering until I reconnected" symptom.
                        # The protocol's own bound is 527 B
                        # (ZGSW_MSG_MAX_SIZE 512 + FRAME_HEAD_SIZE 11 + CRC 4).
                        log.warning(
                            "RX: impossible frame length %d (> %d) -- corrupt "
                            "header, dropping STX and resyncing",
                            total_packet_len, self._MAX_FRAME_BYTES)
                        self.byte_buffer.popleft()
                        pending_since = None
                        continue

                    if len(self.byte_buffer) < total_packet_len:
                        need_more = True  # Not enough data for full packet
                    else:
                        # If we're here, we have a full packet. Extract it.
                        packet_bytes = bytes([self.byte_buffer.popleft()
                                              for _ in range(total_packet_len)])
                        pending_since = None

            if need_more:
                # [review 2026-08-31, A9] Second half of the wedge fix: a
                # header that is plausible (<= the cap) but never completes
                # would still park the parser forever. If nothing has been
                # added to the buffer for _FRAME_RESYNC_S, drop the STX byte
                # and rescan -- a real frame at this baud completes in tens of
                # milliseconds.
                # [review 2026-08-31, L2] Both waits used to sleep INSIDE
                # `buffer_lock`, so every partial frame blocked the listener
                # thread for a full millisecond and the lock was re-acquired
                # immediately on wake -- measurably starving the writer.
                now = time.monotonic()
                with self.buffer_lock:
                    have = len(self.byte_buffer)
                if pending_since is None or have != pending_len:
                    pending_since, pending_len = now, have
                elif now - pending_since > self._FRAME_RESYNC_S:
                    with self.buffer_lock:
                        if self.byte_buffer:
                            self.byte_buffer.popleft()
                    log.warning(
                        "RX: frame header stalled for %.1fs with %d bytes "
                        "buffered -- dropping STX and resyncing",
                        self._FRAME_RESYNC_S, have)
                    pending_since = None
                time.sleep(0.001)
                continue

            # --- Now we have a full packet, process it ---

            # 3. Verify CRC
            data_for_crc = packet_bytes[:-4]
            device_crc, = struct.unpack('>I', packet_bytes[-4:])

            expected_crc = self._crc32(data_for_crc)  # Discard packet

            # 4. Parse the packet
            # Skip STX_HEAD(2) + length(2) = 4 bytes, then parse headers
            # msg_idx(2) + cmd_idx(2) + cmd(2) + ftype(1) = 7 bytes of headers
            header_format = '>HHH B'  # msg_idx, cmd_idx, cmd, ftype

            msg_idx, cmd_idx, cmd, ftype = struct.unpack(header_format,
                                                         packet_bytes[4:11])

            if expected_crc != device_crc:
                self._ack(cmd, msg_idx, cmd_idx, Frame.ACK_FAIL)
                log.warning(f"CRC FAIL cmd=0x{cmd:04X} got=0x{device_crc:08X} exp=0x{expected_crc:08X}")
                continue

            data = packet_bytes[11:-4]

            log.debug(f"RX: cmd=0x{cmd:04X} ftype={Frame.to_str(ftype)} len={len(data)}")


            # 5. Process based on ftype
            # A malformed payload or a throwing user callback must never end
            # this thread -- the whole per-packet body is guarded.
            try:
                # [review 2026-08-31, A11] Exact match FIRST: hand this frame
                # to the one request that carries this (cmd, cmd_idx), if any.
                # A frame with no waiter -- a late reply to a request that
                # already timed out, an unsolicited stream/alarm push carrying
                # the board's own cmd_idx sequence, a retransmission arriving
                # after its waiter left -- resolves nothing and is dispatched
                # only. That is what makes the aliasing class structurally
                # impossible rather than merely unlikely.
                self._resolve_pending(cmd, cmd_idx, ftype, data)
                if ftype == Frame.RESP_OK:
                    with self.response_lock:
                        # markers are per-cmd (see _wr): only this cmd's are consumed
                        self.response_map.pop((Frame.REQ, cmd), None)
                        self.response_map.pop((Frame.RESP_BUSY, cmd), None)
                        self.response_map[cmd] = data
                    # Send an ACK back (outside response_lock: a serial write
                    # must not be held up by / hold up response bookkeeping)
                    self._ack(cmd, msg_idx, cmd_idx)
                    if cmd & 0xFF == 0x72:
                        if self.on_alarm:
                            alarms = data.decode('utf8', errors='replace').split(';')
                            parsed_alarms = []
                            for alarm in alarms:
                                if alarm.find('A0') != -1 or alarm.find('B0') != -1:
                                    idx = alarm.find('A0') if alarm.find('A0') != -1 else alarm.find('B0')
                                    parsed_alarms.append(Alarms.to_str(alarm[idx:idx+6]))
                                else:
                                    # [2026-08-27] MCU alarms are 5-digit numeric codes
                                    # (possibly prefixed with level/idx bytes): decode
                                    # via the same table, keep the raw code visible.
                                    m = re.search(r'\d{5}', alarm)
                                    if m:
                                        parsed_alarms.append(f"{Alarms.to_str(m.group())} [{m.group()}]")
                                    else:
                                        parsed_alarms.append(alarm)
                            self.on_alarm(cmd, parsed_alarms)
                    else:
                        self._dispatch(cmd, data)
                elif ftype == Frame.RESP_FAIL:
                    # print(f"Error ftype: {Frame.to_str(ftype)} for cmd: {cmd:X}")
                    with self.response_lock:
                        self.response_map[cmd] = None
                    if self.on_error:
                        self.on_error(ftype,
                                      f"Device responded with error `{Frame.to_str(ftype)}` for cmd {cmd:X}")
                elif ftype == Frame.ACK_OK:
                    with self.response_lock:
                        self.response_map[Frame.ACK_OK] = cmd
                elif ftype == Frame.REQ:
                    with self.response_lock:
                        self.response_map[(Frame.REQ, cmd)] = True
                    # Send an ACK back (outside response_lock, see above)
                    self._ack(cmd, msg_idx, cmd_idx)
                    self._dispatch(cmd, data)
                elif ftype == Frame.RESP_BUSY:
                    # [review 2026-08-31, A10] BUSY is a TERMINAL REJECTION in
                    # firmware: every one of the 15 call sites that sends it
                    # returns on the next line, so no later reply ever follows
                    # (MCU pmt.c:643/651/687/710/787/792/868/891/950,
                    # extern_server.c:799, system_server.c:111; MotorDriver
                    # motion_coord.c:424+453, fluorescence.c:167/177/235).
                    # The host used to do the opposite -- park a marker that
                    # RESET the deadline -- so a refused command cost a full
                    # extra timeout_s (measured 1.21 s on a 1.0 s timeout,
                    # 30 s on a 30 s motion command) and then returned None,
                    # indistinguishable from a dead board. It now resolves the
                    # wait the way RESP_FAIL does, with a distinguishable
                    # sentinel so callers and the log pane can say "BUSY".
                    with self.response_lock:
                        self.response_map.pop((Frame.REQ, cmd), None)
                        self.response_map[cmd] = BUSY
                else:
                    # print(f"cmd: {cmd:X} > data: {data.hex(' ')}")
                    with self.response_lock:
                        self.response_map[cmd] = None
                    self._ack(cmd, msg_idx, cmd_idx)
                    # print(f"Error ftype: {Frame.to_str(ftype)} for cmd: {cmd:X}")
                    if self.on_error:
                        self.on_error(ftype,
                                      f"Device responded with error `{Frame.to_str(ftype)}` for cmd {cmd:X}")
            except Exception:
                log.exception(
                    f"RX packet handling failed for cmd=0x{cmd:04X} "
                    f"ftype={Frame.to_str(ftype)}")

        log.debug("Process thread stopped.")

    def _dispatch(self, cmd: int, data: bytes) -> None:
        """Fan out a received frame to on_ready_read and any subscriber.

        Called from the RX processing thread for every RESP_OK (non-alarm)
        and REQ frame -- matched or not against a pending _wr() request; this
        is the existing point unsolicited/streamed packets (e.g.
        ROUTE_POWER_CMD during a 0x1232 scan, see _collect_cap_stream) flow
        through today via on_ready_read. subscribe()/unsubscribe() add a
        second, targeted cmd -> callback path without changing
        on_ready_read's existing global-callback semantics or touching
        response_map's request/response bookkeeping.
        """
        if self.on_ready_read:
            try:
                self.on_ready_read(cmd, data)
            except Exception:
                log.exception("on_ready_read callback raised")
        with self._subscribers_lock:
            callback = self._subscribers.get(cmd)
        if callback is not None:
            try:
                callback(cmd, data)
            except Exception:
                log.exception(f"subscriber callback for cmd 0x{cmd:04X} raised")

    def subscribe(self, cmd: int, callback: Callable[[int, bytes], None]) -> None:
        """Register `callback(cmd, data)` for frames matching `cmd` (see _dispatch).

        Only one callback per `cmd` is supported; a second subscribe() for
        the same `cmd` replaces it. Callers must always pair this with
        unsubscribe(cmd) (e.g. via try/finally) to avoid leaking a stale
        callback into a later, unrelated collection window.
        """
        with self._subscribers_lock:
            self._subscribers[cmd] = callback

    def unsubscribe(self, cmd: int) -> None:
        """Remove a subscription registered via subscribe(). No-op if absent."""
        with self._subscribers_lock:
            self._subscribers.pop(cmd, None)

    def _crc32(self, data: bytes) -> int:
        # POLY = 0x04C11DB7
        crc = 0xFFFFFFFF

        padded_data = bytearray(data)

        # The C++ code pads the data to a multiple of 4 bytes with zeros
        # for word-by-word processing.
        if len(padded_data) % 4 != 0:
            padding_len = 4 - (len(padded_data) % 4)
            padded_data.extend(b'\x00' * padding_len)

        # for i in range(0, len(padded_data), 4):
        #     # The C++ code casts a byte array to uint32_t*, which on a
        #     # little-endian machine (like x86) reverses the byte order of
        #     # each 4-byte chunk.
        #     chunk, = struct.unpack('<I', padded_data[i:i+4])
        #     crc ^= chunk
        #     for _ in range(32):
        #         if crc & 0x80000000:
        #             crc = (crc << 1) ^ POLY
        #         else:
        #             crc <<= 1
        # return crc & 0xFFFFFFFF
        table = self._crc_table
        for i in range(0, len(padded_data), 4):
            # We extract the 4 bytes of the chunk
            b0 = padded_data[i]
            b1 = padded_data[i+1]
            b2 = padded_data[i+2]
            b3 = padded_data[i+3]

            # Process them in reverse order (3, 2, 1, 0) to match the
            # Little-Endian-load-then-Left-Shift logic of the original code.
            for b in (b3, b2, b1, b0):
                # Standard Table-Driven CRC32 Implementation
                pos = (crc >> 24) ^ b
                crc = ((crc << 8) & 0xFFFFFFFF) ^ table[pos]

        return crc

    def _generate_crc_table(self):
        """Generates the lookup table for polynomial 0x04C11DB7 (Non-Reflected)"""
        poly = 0x04C11DB7
        table = []
        for byte in range(256):
            crc = byte << 24
            for _ in range(8):
                if crc & 0x80000000:
                    crc = (crc << 1) ^ poly
                else:
                    crc = crc << 1
            table.append(crc & 0xFFFFFFFF)
        return table

    def _make_cmd_packet(self, cmd: int, buf: bytes = None,
                         frame_type: int = Frame.REQ,
                         msg_idx_override=None, cmd_idx_override=None):
        """Creates a complete command packet."""

        # [WP-LANES follow-up] Allocate BOTH counters atomically up front: with
        # two lanes building packets concurrently, the old read-at-top /
        # increment-at-bottom pattern spanned the whole build (incl. the CRC
        # loop), so two frames could share a cmd_idx.
        #
        # [review 2026-08-31, L7] Why that matters -- the original comment here
        # said "the firmware rejects a duplicate cmd_idx", which is NOT true:
        # there is no duplicate-cmd_idx rejection anywhere in the MCU RX path.
        # The allocation is still load-bearing, for two other reasons:
        #   1. the firmware's reply-retry queue matches ACKs on (cmd, cmd_idx)
        #      (_frame.c:432-437), so two outstanding frames sharing a pair
        #      cross-match each other's ACKs and one reply retransmits until
        #      MSG_TRY_MSG;
        #   2. this host now matches REPLIES on (cmd, cmd_idx) too -- see
        #      _Pending -- so cmd_idx uniqueness is the precondition of the
        #      whole anti-aliasing scheme.
        with self.idx_lock:
            msg_idx = self.msg_idx if msg_idx_override is None else msg_idx_override
            cmd_idx = self.cmd_idx if cmd_idx_override is None else cmd_idx_override
            if msg_idx_override is None:
                self.msg_idx = (self.msg_idx + 1) & 0xFFFF
            if cmd_idx_override is None:
                self.cmd_idx = (self.cmd_idx + 1) & 0xFFFF

        ba = bytearray()
        ba.extend(struct.pack('>H', Frame.HEAD))
        # Placeholder for length, to be updated later
        ba.extend(struct.pack('>H', 0))
        ba.extend(struct.pack('>H', msg_idx))
        ba.extend(struct.pack('>H', cmd_idx))
        ba.extend(struct.pack('>H', cmd))
        ba.extend(struct.pack('>B', frame_type))
        if buf is not None:
            ba.extend(buf)

        # Update length field with total length of headers + data (like C++)
        headers_plus_data_len = len(ba)
        struct.pack_into('>H', ba, 2, headers_plus_data_len)

        crc = self._crc32(ba)
        ba.extend(struct.pack('>I', crc))  # swap bytes to network order

        return bytes(ba)

    def is_port_open(self) -> bool:
        """True when a write would actually reach the wire.

        [review 2026-08-31, A4] The one condition `_w()` gates on, exposed so
        wait loops can bail on a vanished port instead of hot-spinning on
        `_w() -> False` (an unplugged FTDI, or `_listen_thread_fn` having
        already cleared `is_running` after a SerialException)."""
        return bool(self.serial and self.serial.is_open)

    def _w(self, data: bytes):
        """Equivalent to _w. Just writes data."""
        if self.serial and self.serial.is_open:
            # print(f"Sending  {len(data)} bytes > {data.hex(' ')}")
            with self.tx_lock:  # keep packets from interleaving on the wire
                self.serial.write(data)
            return True
        return False

    # [WP-LANES] Cap on the per-cmd lock map. Command ids come from a fixed
    # set in practice; the Raw/Advanced UI can send arbitrary ones, so prune
    # (only locks nobody holds) instead of growing without bound.
    _MAX_CMD_LOCKS = 512

    def _cmd_lock_entry(self, cmd: int) -> list:
        """Reserve the in-flight guard for one command id, creating it on
        first use. Returns the `[RLock, users]` entry with `users` already
        incremented -- `_wr` decrements it again in its finally block, and
        pruning only ever drops entries nobody has reserved."""
        with self._cmd_locks_guard:
            entry = self._cmd_locks.get(cmd)
            if entry is None:
                if len(self._cmd_locks) >= self._MAX_CMD_LOCKS:
                    self._cmd_locks = {c: e for c, e in self._cmd_locks.items()
                                       if e[1] > 0}
                entry = self._cmd_locks.setdefault(cmd, [threading.RLock(), 0])
            entry[1] += 1
            return entry

    # Absolute ceiling on one _wr wait, however many "still working" signals
    # the device sends. Shared by both matching paths.
    _MAX_PROGRESS_EXTEND_S = 60.0

    @staticmethod
    def frame_cmd_idx(wbuf: bytes, cmd: int) -> int | None:
        """The cmd_idx carried by `wbuf`, or None if it is not our frame.

        [review 2026-08-31, A11] Layout, from `_make_cmd_packet`:
            [0:2] 0x7CF1  [2:4] len  [4:6] msg_idx  [6:8] cmd_idx
            [8:10] cmd    [10] ftype  ... payload ...  [-4:] CRC32
        Reading it back off the packet -- rather than threading a second
        return value through ~200 generated call sites -- is what makes the
        (cmd, cmd_idx) matching a pure transport change with no regeneration
        and no call-site churn. Anything that is not a well-formed frame for
        this exact `cmd` (a hand-rolled buffer, a test marker) returns None
        and falls back to the legacy cmd-id-only wait.
        """
        if wbuf is None or len(wbuf) < Frame.HEAD_SIZE:
            return None
        try:
            head, = struct.unpack('>H', wbuf[0:2])
            frame_cmd, = struct.unpack('>H', wbuf[8:10])
        except struct.error:
            return None
        if head != Frame.HEAD or frame_cmd != cmd:
            return None
        return struct.unpack('>H', wbuf[6:8])[0]

    def take_busy(self) -> tuple[int, float] | None:
        """Drain this thread's "the board refused it" mark, if any.

        [review 2026-08-31, A10] `_wr` keeps returning None for a BUSY so no
        existing call site changes behaviour, and records the rejection here
        instead. Keyed by thread id, so the lane thread that made the call is
        the one that reads it back -- see SerialWorker._run_lane, which turns
        it into a "BUSY" job result rather than a "TIMEOUT".
        """
        return self._busy_marks.pop(threading.get_ident(), None)

    def _note_busy(self, cmd: int) -> None:
        self._busy_marks[threading.get_ident()] = (cmd, time.time())
        log.info("cmd 0x%04X refused by the device (RESP_BUSY)", cmd)

    def _resolve_pending(self, cmd: int, cmd_idx: int, ftype: int,
                         data: bytes) -> None:
        """Hand one received frame to the request that owns (cmd, cmd_idx).

        Called from the RX thread for EVERY frame. See _Pending for why the
        pair, not the command id alone, is the right key. Idempotent: the
        firmware retransmits un-ACKed `zgsw_rep` replies with the same
        (cmd, cmd_idx) (`_frame.c:389-392`), and a retransmission must resolve
        its waiter exactly once.
        """
        with self._pending_lock:
            p = self._pending.get((cmd, cmd_idx))
            if p is None:
                if ftype in (Frame.RESP_OK, Frame.REQ):
                    # Device-pushed frames (PMT stream, alarm notify) run the
                    # board's OWN cmd_idx sequence and legitimately match
                    # nothing; so does a reply whose requester already left.
                    log.debug("unmatched frame cmd=0x%04X idx=%d ftype=0x%02X "
                              "-> dispatch only", cmd, cmd_idx, ftype)
                if ftype == Frame.REQ:
                    # ...but a device-pushed REQ on a cmd someone IS waiting
                    # on still means "still working", exactly as the old
                    # (Frame.REQ, cmd) marker did. Extend those waits.
                    for key, other in self._pending.items():
                        if key[0] == cmd:
                            other.progress = True
                return
            if p.event.is_set():
                return  # already resolved; a retransmission is a no-op
            if ftype == Frame.ACK_OK:
                p.progress = True
                return
            if ftype == Frame.REQ:
                p.progress = True
                return
            if ftype == Frame.RESP_BUSY:
                p.busy = True
            elif ftype == Frame.RESP_FAIL:
                p.failed = True
                p.value = None
            elif ftype == Frame.RESP_OK:
                if len(data) < p.min_len:
                    # An immediate empty ACK that precedes the real answer
                    # (CLEAR_ALARM does exactly this). Keep it as a fallback
                    # but keep waiting for the frame that carries the payload.
                    p.short = data
                    return
                p.value = data
            else:
                p.value = None  # RESP_ERR / UNKNOWN / TIMEOUT: same as FAIL
            p.event.set()

    def _wr(self, wbuf: bytes, cmd: int, timeout_s: float = 1.0,
            min_len: int = 0):
        """
        Writes a command frame and waits for ITS reply.

        [review 2026-08-31, A11] Replies are matched on (cmd, cmd_idx) when
        `wbuf` is a frame this transport built -- which is every real caller,
        since they all go through `_make_cmd_packet`. A late reply to a
        request that already timed out therefore has no waiter and is dropped
        (logged, still dispatched) instead of being served to the next request
        for the same command id. Anything else falls back to the legacy
        cmd-id-only wait below.

        [WP-LANES] Still serialized per command id. With (cmd, cmd_idx)
        matching the guard is no longer load-bearing for correctness, but it
        is kept for now because (a) the legacy path still needs it and (b)
        retiring it changes lane scheduling for commands that carry both a
        short and a long operation (MOTOR_CONTROL 0x11B0 is move AND stop) --
        a bench-validated change, not a desk one. Single-threaded callers are
        unaffected (uncontended RLock).

        `min_len` resolves the wait only on a reply of at least that many
        bytes; shorter RESP_OK frames are kept as a fallback and returned only
        if nothing longer arrives. For commands that answer with an immediate
        empty ACK followed by the real payload (CLEAR_ALARM, alarm.c:277 then
        alarm.c:120-133). Ignored on the legacy path.
        """
        entry = self._cmd_lock_entry(cmd)
        entry[0].acquire()
        try:
            cmd_idx = self.frame_cmd_idx(wbuf, cmd)
            if cmd_idx is None:
                return self._wr_locked_legacy(wbuf, cmd, timeout_s)
            result = self._wr_locked_by_idx(wbuf, cmd, cmd_idx, timeout_s,
                                            min_len)
            if result is BUSY:
                self._note_busy(cmd)
                return None
            return result
        finally:
            # [review 2026-08-31, L1] RELEASE FIRST, then drop the user count.
            # The other order left a window between `entry[1] -= 1` and
            # `entry[0].release()` in which the entry has users == 0, so
            # _cmd_lock_entry's prune (`{c: e for c, e in ... if e[1] > 0}`)
            # could drop it and a third thread setdefault a FRESH RLock for
            # the same cmd -- entering _wr_locked concurrently with a caller
            # that has not released yet, which is exactly what the in-flight
            # guard exists to prevent. Reaching it needs > 512 distinct cmd
            # ids, which only the Raw/Advanced tab can produce.
            entry[0].release()
            with self._cmd_locks_guard:
                entry[1] -= 1

    def _wr_locked_by_idx(self, wbuf: bytes, cmd: int, cmd_idx: int,
                          timeout_s: float = 1.0, min_len: int = 0):
        """Write-and-wait matched on (cmd, cmd_idx). See _Pending.

        Registers the waiter BEFORE writing, so a reply that comes back faster
        than this thread is rescheduled cannot miss it, and pops it in a
        finally so a timed-out request leaves nothing behind for a late reply
        to land in.
        """
        p = _Pending(cmd, cmd_idx, min_len=min_len)
        key = (cmd, cmd_idx)
        with self._pending_lock:
            self._pending[key] = p
        try:
            if not self._w(wbuf):
                return None  # Write failed (port closed)

            absolute_start = time.monotonic()
            start_time = absolute_start
            while True:
                remaining = timeout_s - (time.monotonic() - start_time)
                if remaining <= 0:
                    break
                # Event-driven: the reply resolves the wait the moment it
                # lands, instead of up to a 10 ms poll tick later. The cap
                # keeps "still working" extensions responsive.
                if p.event.wait(timeout=min(0.05, remaining)):
                    break
                with self._pending_lock:
                    progressed = p.progress
                    p.progress = False
                # An ACK, or a device-pushed REQ on this cmd, means the board
                # is still working: reset the timer, but respect the absolute
                # ceiling, exactly as the old marker scheme did.
                if progressed and (time.monotonic() - absolute_start
                                   < self._MAX_PROGRESS_EXTEND_S):
                    start_time = time.monotonic()

            if p.event.is_set():
                if p.busy:
                    return BUSY
                return p.value
            if p.short is not None:
                # Only the immediate ACK arrived; hand it back so callers see
                # today's behaviour rather than a spurious timeout.
                log.warning("Command %X idx %d: only a short (%dB) reply, "
                            "expected >= %dB", cmd, cmd_idx, len(p.short),
                            min_len)
                return p.short
        finally:
            with self._pending_lock:
                self._pending.pop(key, None)

        log.warning(f"Command {cmd:X} idx {cmd_idx} timed out!")
        if self.on_error:
            self.on_error(-2, f"Timeout for cmd {cmd:X}")
        return None  # Timeout

    def _wr_locked_legacy(self, wbuf: bytes, cmd: int, timeout_s: float = 1.0):
        """The pre-cmd_idx write-and-wait, matched on the command id ALONE.

        Kept verbatim (bar the A10 BUSY change) as the fallback for a `wbuf`
        that is not a frame this transport built. It carries the A11 aliasing
        weakness by construction -- a late reply lands in `response_map[cmd]`
        and is claimed by the next request for that id -- which is exactly why
        every real caller now takes `_wr_locked_by_idx`.
        """

        # Clear any old response / stale busy-req markers for this command
        with self.response_lock:
            self.response_map.pop(cmd, None)
            self.response_map.pop((Frame.REQ, cmd), None)
            self.response_map.pop((Frame.RESP_BUSY, cmd), None)

        if not self._w(wbuf):
            return None  # Write failed

        # absolute maximum wait even if the device keeps signalling progress
        max_busy_s = self._MAX_PROGRESS_EXTEND_S
        absolute_start = time.time()
        start_time = absolute_start
        while time.time() - start_time < timeout_s:
            with self.response_lock:
                if self.response_map.get(Frame.ACK_OK, 0x0000) == cmd:
                    start_time = time.time()  # reset timer on ACK
                    self.response_map.pop(Frame.ACK_OK)
                # Only THIS cmd's req marker may extend THIS wait; it is
                # consumed once, so markers left by unrelated / device-pushed
                # frames never poison us. [A10] BUSY no longer extends
                # anything -- it resolves the wait, below, via the sentinel.
                req = self.response_map.pop((Frame.REQ, cmd), None) is not None
                if req:
                    if time.time() - absolute_start < max_busy_s:
                        start_time = time.time()  # reset timer, but respect absolute limit
                if cmd in self.response_map:
                    value = self.response_map.pop(cmd)
                    if value is BUSY:
                        self._note_busy(cmd)
                        return None
                    return value

            time.sleep(0.01)  # Poll for response

        log.warning(f"Command {cmd:X} timed out!")
        if self.on_error:
            self.on_error(-2, f"Timeout for cmd {cmd:X}")
        return None  # Timeout

    # Back-compat alias: some scripts call the internal directly.
    _wr_locked = _wr_locked_legacy

    def _ack(self, cmd: int, msg_idx: int, cmd_idx: int, frame_type: int = Frame.ACK_OK):
        """Sends an ACK back"""
        send_packet = self._make_cmd_packet(
            cmd, b'', frame_type, msg_idx, cmd_idx)
        self._w(send_packet)

    def _get_time_buffer(self) -> bytes:
        """Gets the time buffer"""
        now = time.localtime()
        return struct.pack('BBBBBB',
                           (now.tm_year - 2000) & 0xff,
                           now.tm_mon,
                           now.tm_mday,
                           now.tm_hour,
                           now.tm_min, now.tm_sec)

    def _update_board_connected(self, board: str, connected: bool):
        if board == 'signal':
            self.sig_board_connected = connected
            return connected
        elif board == 'motor':
            self.motor_board_connected = connected
            return connected
        else:
            return False

    def _is_connected(self, board: str):
        if board == 'signal':
            return self.sig_board_connected
        elif board == 'motor':
            return self.motor_board_connected
        else:
            return False

    # --- Public API Functions ---
    def BoardLogin(self, board: str = 'signal', timeout_s: float = 2.0):
        """Board login"""
        if board == 'signal':
            cmd = SignalBoard.LOGIN
        elif board == 'motor':
            cmd = MotorBoard.LOGIN
        else:
            return None
        buf = self._get_time_buffer()
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=timeout_s)
        if response is not None:
            connected = self._update_board_connected(board, response[0] == 0)
            # [WP-L 2026-08-27] Firmware from this date appends the same
            # "module;hw;sw;" identity string as VERSION after the status
            # byte; legacy firmware replies 1 byte and lands in the fallback.
            if len(response) > 1:
                ident = response[1:].decode('ascii', errors='replace').strip('\x00;')
                self.login_identity[board] = ident
                log.info("%s login identity: %s", board, ident)
            if board == 'signal' and connected:
                # Auto-adapt to the provisioned channel count right after
                # login; board_channels/board_n_chips remain available even
                # if this particular query fails (lazy retry on next access).
                self._query_board_channels()
            return connected
        return self._update_board_connected(board, False)

    def login_with_retry(self, board: str = 'signal', attempts: int = 3,
                         backoff_s: float = 0.5, timeout_s: float = 3.0,
                         wait_version_s: float = 0.0) -> bool:
        """Robust login for the fragile just-after-open serial window.

        Login is idempotent firmware-side (sets the RTC, starts the status
        thread, arms alarm push; no other command is login-gated), so
        retrying is always safe. `wait_version_s` > 0 first polls the
        read-only VERSION command until the board answers (or the budget
        runs out) before spending login attempts — use it on
        reconnect-after-reset paths where boot logs share the UART.
        """
        if wait_version_s > 0:
            deadline = time.time() + wait_version_s
            while time.time() < deadline:
                # [review 2026-08-31, A4] Bail the instant the port is gone.
                # _w() returns False immediately on a closed port and
                # _wr_locked then returns None without waiting, so on an
                # unplugged FTDI this loop is NOT self-limiting: measured
                # 253,524 GetBoardVersion calls/second, 100 % CPU, for the
                # whole 12 s attach_motor budget -- on the lane the E-STOP
                # used to share.
                if not self.is_port_open():
                    log.warning("%s version wait aborted: port is closed", board)
                    return False
                v = self.GetBoardVersion(board, timeout_s=1.0) or {}
                if v.get('software_version'):
                    break
                # ...and never spin even when the port IS open but the board
                # answers instantly-negatively (RESP_FAIL parks None at once).
                time.sleep(0.2)
        for attempt in range(attempts):
            if self.BoardLogin(board, timeout_s=timeout_s):
                return True
            if attempt < attempts - 1:
                time.sleep(backoff_s * (attempt + 1))
        return False

    def _query_board_channels(self) -> None:
        """Query CMD_BOARD_CHANNELS_GET (0x1240) and cache the result.

        Called automatically after a successful signal-board login (see
        BoardLogin above); also invoked lazily by the board_channels /
        board_n_chips properties if the cache is still empty, so code that
        never calls BoardLogin directly (or logs in before this driver
        version) still gets a correct value on first use.

        On timeout/failure (legacy firmware without 0x1240) defaults to the
        pre-expansion board: 120 channels / 8 HC595 chips per chain.
        """
        packet = self._make_cmd_packet(CMD_BOARD_CHANNELS_GET)
        resp = self._wr(packet, CMD_BOARD_CHANNELS_GET, timeout_s=2.0)
        if resp is not None and len(resp) >= 3:
            channels, n_chips = struct.unpack('>HB', resp[:3])
            self._board_channels = channels
            self._board_n_chips = n_chips
            self._legacy_fw = False
        else:
            log.warning("BOARD_CHANNELS_GET timed out/failed; "
                        "assuming legacy 120-channel board (8 chips/chain)")
            self._board_channels = 120
            self._board_n_chips = 8
            self._legacy_fw = True

    @property
    def board_channels(self) -> int:
        """Number of provisioned electrode channels (120 or 200).

        Cached from CMD_BOARD_CHANNELS_GET; queried automatically after
        signal-board login, or lazily here on first access.
        """
        if self._board_channels is None:
            self._query_board_channels()
        return self._board_channels

    @property
    def board_n_chips(self) -> int:
        """Number of HC595 chips per chain (8 for 120-ch, 13 for 200-ch board)."""
        if self._board_n_chips is None:
            self._query_board_channels()
        return self._board_n_chips

    def set_board_channels(self, n: int, retries: int = 3) -> bool:
        """Provision the board's electrode channel count (0x1241).

        This is a **provisioning** command: the firmware persists ``n`` to
        EEPROM (EasyFlash env ``brd_ch``) and, per the firmware spec, clears
        all electrode outputs as part of applying the new channel mapping.
        Intended for one-time setup of a new board, not routine use.

        Robustness: the firmware already EEPROM-read-back-verifies the write
        before replying, and the SET is idempotent, so the only realistic
        failure mode is a dropped/corrupted *reply* (e.g. toggling modes
        rapidly on a noisy link). Rather than trust the SET echo, each attempt
        fires the SET and then confirms the **actual applied value** via an
        independent GET (0x1240) -- sidestepping the lost-reply problem -- and
        retries the pair up to ``retries`` times.

        Args:
            n: New channel count, must be 120 or 200.
            retries: Max SET+verify attempts before giving up.

        Returns:
            bool: True once a GET confirms the board is at ``n``.
        """
        if n not in (120, 200):
            raise ValueError(f"board_channels must be 120 or 200, got {n}")
        if not self.sig_board_connected:
            log.error("Signal board not connected")
            return False
        set_pkt = self._make_cmd_packet(CMD_BOARD_CHANNELS_SET, struct.pack('>H', n))
        for attempt in range(retries):
            # Fire the SET (best-effort; its echo may be lost -- we don't rely on it).
            self._wr(set_pkt, CMD_BOARD_CHANNELS_SET, timeout_s=3.0)
            time.sleep(0.15)
            # Authoritative confirm via an independent GET (0x1240). Do NOT use the
            # board_channels property here -- it defaults to 120 on a failed query,
            # which would falsely "confirm" n==120. Parse the GET reply directly.
            g = self._wr(self._make_cmd_packet(CMD_BOARD_CHANNELS_GET),
                         CMD_BOARD_CHANNELS_GET, timeout_s=2.0)
            if g is not None and len(g) >= 3:
                channels, n_chips = struct.unpack('>HB', g[:3])
                if channels == n:
                    self._board_channels = channels
                    self._board_n_chips = n_chips
                    return True
            if attempt + 1 < retries:
                log.warning(f"set_board_channels({n}) unconfirmed "
                            f"(attempt {attempt + 1}/{retries}); retrying")
        return False

    def get_app_baud(self) -> int | None:
        """Query the app UART baud rate currently persisted on the board (0x1246).

        Note this is the *provisioned* rate (EasyFlash env ``app_baud``),
        which is what will be used after the next reboot -- it is not
        necessarily the rate the host is talking to the board at right now
        if a set_app_baud() call hasn't been followed by a reboot yet.

        Returns:
            Baud rate in Hz, or None on timeout/failure (e.g. firmware
            predates 0x1246).
        """
        if not self.sig_board_connected:
            log.error("Signal board not connected")
            return None
        packet = self._make_cmd_packet(CMD_APP_BAUD_GET)
        resp = self._wr(packet, CMD_APP_BAUD_GET, timeout_s=2.0)
        if resp is not None and len(resp) >= 4:
            return struct.unpack('>I', resp[:4])[0]
        return None

    def set_app_baud(self, baud: int) -> bool:
        """Provision the app UART baud rate (0x1247).

        This is a **provisioning** command: the firmware persists ``baud``
        to EEPROM (EasyFlash env ``app_baud``) and echoes it back over the
        connection at the CURRENT baud -- the new rate does **not** take
        effect immediately. It only applies after the board reboots, at
        which point the host must reconnect at the new baud (e.g. via
        init_autodetect(), which will find it automatically).

        Args:
            baud: Requested rate; must be one of APP_BAUD_WHITELIST
                (115200, 230400, 460800, 921600).

        Returns:
            bool: True if the firmware echoed back the requested value.

        Raises:
            ValueError: If `baud` is not in APP_BAUD_WHITELIST.
        """
        if baud not in APP_BAUD_WHITELIST:
            raise ValueError(f"app_baud must be one of {APP_BAUD_WHITELIST}, got {baud}")
        if not self.sig_board_connected:
            log.error("Signal board not connected")
            return False
        buf = struct.pack('>I', baud)
        packet = self._make_cmd_packet(CMD_APP_BAUD_SET, buf)
        resp = self._wr(packet, CMD_APP_BAUD_SET, timeout_s=3.0)
        if resp is not None and len(resp) >= 4:
            echoed, = struct.unpack('>I', resp[:4])
            if echoed == baud:
                log.info(f"app_baud provisioned to {baud}; effective after reboot")
                return True
        return False

    def read_uid(self, use_cache: bool = True) -> str | None:
        """Read the STM32 factory UID (0x1245) as a lowercase hex string.

        12 raw bytes (three 32-bit factory-UID words) returned verbatim as
        24 lowercase hex characters -- used e.g. to key persistent per-board
        capacitance calibration files (see session.py save_cap_cal /
        load_cap_cal). Cached after the first successful read; pass
        use_cache=False to force a re-query.

        Returns:
            Lowercase hex UID string, or None if the board is unreachable or
            predates 0x1245 (old firmware) -- callers should fall back to a
            generic key such as "default" in that case.
        """
        if use_cache and self._uid_hex is not None:
            return self._uid_hex
        if not self.sig_board_connected:
            return None
        packet = self._make_cmd_packet(CMD_READ_UID)
        resp = self._wr(packet, CMD_READ_UID, timeout_s=2.0)
        if resp is not None and len(resp) >= 12:
            self._uid_hex = resp[:12].hex()
            return self._uid_hex
        return None

    def GetBoardVersion(self, board: str = 'signal',
                        timeout_s: float = 1.0) -> str:
        """Get signal or motor board version.

        `timeout_s` is worth raising for the motor board: its VERSION reply is
        CAN-routed through the signal board and can take longer than 1 s.
        """
        if board == 'signal':
            cmd = SignalBoard.VERSION
        elif board == 'motor':
            cmd = MotorBoard.VERSION
        else:
            return None

        packet = self._make_cmd_packet(cmd)
        version = self._wr(packet, cmd, timeout_s=timeout_s)
        if version is not None:
            version = version.decode('utf8')
            parts = version.split(';')
            if len(parts) >= 3:
                version = {
                    'serial_number': parts[0],
                    'hardware_version': parts[1],
                    'software_version': parts[2]
                }
            else:
                version = {
                    'version': version
                }
        else:
            version = {
                'version': 'unknown'
            }
        return version

    def GetBoardStatus(self, board: str = 'signal'):
        """Get signal or motor board status. Returns raw response bytes or None on timeout."""
        if board == 'signal':
            cmd = SignalBoard.STATUS
        elif board == 'motor':
            cmd = MotorBoard.STATUS
        else:
            return None
        packet = self._make_cmd_packet(cmd)
        return self._wr(packet, cmd, timeout_s=3.0)

    def ResetBoard(self, board: str = 'signal'):
        """Reset signal or motor board"""
        if board == 'signal':
            cmd = SignalBoard.HW_RESET
        elif board == 'motor':
            cmd = MotorBoard.HW_RESET
        else:
            return None
        packet = self._make_cmd_packet(cmd)
        self._w(packet)
        return True

    def RebootBoard(self, board: str = 'signal'):
        """Reboot signal or motor board"""
        if board == 'signal':
            cmd = SignalBoard.RESET
            self.sig_board_connected = False
        elif board == 'motor':
            cmd = MotorBoard.RESET
            self.motor_board_connected = False
        else:
            return None
        packet = self._make_cmd_packet(cmd)
        self._w(packet)

        time.sleep(3)
        # [WP-L] reconnect-after-reset: poll read-only VERSION until the board
        # answers (boot logs share the UART), then log in with retries.
        return self.login_with_retry(board, attempts=2, timeout_s=5,
                                     wait_version_s=5.0)

    # --- Convenience Functions ---
    def login(self):
        """Replicating login"""
        signal_response = self.login_with_retry('signal', attempts=2)
        motor_response = self.login_with_retry('motor', attempts=2)
        return signal_response, motor_response

    def getVersions(self):
        """Gets version from a specific board"""
        signal_version = None
        motor_version = None

        if self.sig_board_connected:
            signal_version = self.GetBoardVersion('signal')
        if self.motor_board_connected:
            motor_version = self.GetBoardVersion('motor')
        return signal_version, motor_version

    def selfCheck(self):
        """Initiates hardware self-check"""
        if self.sig_board_connected:
            self.ResetBoard('signal')
        if self.motor_board_connected:
            self.ResetBoard('motor')
        return True

    def getStatus(self):
        """Replicating getStatus for _sys_status1"""
        signal_status = None
        motor_status = None
        if self.sig_board_connected:
            signal_status = self.GetBoardStatus('signal')
        if self.motor_board_connected:
            motor_status = self.GetBoardStatus('motor')
        return signal_status, motor_status

    # # --- Configuration ---
    def setAlarmLevel(self, board: str = 'signal', level: int = 0):
        """Set alarm reporting level on specified board."""
        if board == 'motor':
            if not self.motor_board_connected: return False
            cmd = MotorBoard.SET_ALARM_LEVEL
        else:
            if not self.sig_board_connected: return False
            cmd = SignalBoard.SET_ALARM_LEVEL
        buf = struct.pack('B', level)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setLogLevel(self, board: str = 'signal', level: int = 0):
        """Set log reporting level on specified board."""
        if board == 'motor':
            if not self.motor_board_connected: return False
            cmd = MotorBoard.SET_LOG_LEVEL
        else:
            if not self.sig_board_connected: return False
            cmd = SignalBoard.SET_LOG_LEVEL
        buf = struct.pack('B', level)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    # # --- Capacitance ---
    def calibrateCapacitors(self):
        """Run capacitance calibration. Returns raw response bytes."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.CAP_CALIBRATE
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=30)
        if response is not None:
            data = struct.unpack('>HHH', response)
            return {
                '10pF': data[0]/10,
                '100pF': data[1]/10,
                '470pF': data[2]/10
            }
        return None

    def _collect_cap_stream(self, n: int, switch_time_ms: int,
                            first_packet_timeout_s: float = 5.0) -> bytes | None:
        """Collect the CAP_READ_ALL (0x1232) per-channel stream (board_channels > 120).

        On boards with board_channels > 120 the 0x1232 scan's own final
        summary reply would exceed the 128-byte ZGSW frame limit and is
        silently dropped by the firmware transport -- but the per-channel
        packets streamed *during* the scan (cmd ROUTE_POWER_CMD, payload
        [u8 total, u8 idx_1based, u8 cap_pf]) each fit easily and still
        arrive. This subscribes to ROUTE_POWER_CMD, fires the 0x1232 request
        fire-and-forget (no reply is ever awaited via _wr/response_map), and
        assembles the stream into an `n`-byte array via _CapStreamAssembler.

        Completion conditions (either one ends collection):
          - all `n` channels have been seen at least once, or
          - no packet has arrived for `switch_time_ms*5 + 2000` ms (a
            stalled/partial scan) -- in this case whatever was collected is
            returned (missing channels stay 0), not None; this is the
            scan-appears-finished heuristic, distinct from total failure.

        Total failure (returns None, meaning "the stream mechanism itself
        isn't working -- fall back to the chunked 0x1235 path"): zero
        packets received within the first `first_packet_timeout_s` seconds.

        Always restores the previous ROUTE_POWER_CMD subscriber (or
        unsubscribes if there wasn't one) before returning, including on
        exception.

        Args:
            n: Expected channel count (self.board_channels at call time).
            switch_time_ms: Settle time per channel; also sets the
                inactivity timeout (switch_time_ms*5 + 2000 ms).
            first_packet_timeout_s: How long to wait for the very first
                packet before giving up and returning None.

        Returns:
            bytes of length n (pF per channel, 0-255), or None if the stream
            produced zero packets.
        """
        assembler = _CapStreamAssembler(n)
        packet_event = threading.Event()

        def _on_stream_packet(cmd: int, data: bytes) -> None:
            if len(data) < 3:
                return
            total, idx, cap_pf = struct.unpack('>BBB', data[:3])
            assembler.feed(total, idx, cap_pf)
            packet_event.set()

        # Save any pre-existing ROUTE_POWER_CMD subscriber so this collection
        # window restores it instead of silently dropping it.
        with self._subscribers_lock:
            prev_subscriber = self._subscribers.get(ROUTE_POWER_CMD)
        self.subscribe(ROUTE_POWER_CMD, _on_stream_packet)
        try:
            buf = struct.pack('>H', switch_time_ms)
            packet = self._make_cmd_packet(SignalBoard.CAP_READ_ALL, buf)
            if not self._w(packet):
                return None

            inactivity_timeout_s = (switch_time_ms * 5 + 2000) / 1000.0
            first_packet_received = False
            while True:
                if assembler.is_complete():
                    break
                timeout = (inactivity_timeout_s if first_packet_received
                          else first_packet_timeout_s)
                got_packet = packet_event.wait(timeout=timeout)
                packet_event.clear()
                if got_packet:
                    first_packet_received = True
                    continue
                if not first_packet_received:
                    log.warning(f"0x1232 stream: no packets within "
                                f"{first_packet_timeout_s}s; triggering "
                                f"chunked-scan fallback")
                    return None
                log.warning(f"0x1232 stream: stalled at "
                            f"{assembler.n_received}/{n} channels -- no "
                            f"packet for {inactivity_timeout_s}s")
                break

            if assembler.n_received < n:
                log.warning(f"0x1232 stream: incomplete "
                            f"({assembler.n_received}/{n} channels)")
            return assembler.to_bytes()
        finally:
            if prev_subscriber is not None:
                self.subscribe(ROUTE_POWER_CMD, prev_subscriber)
            else:
                self.unsubscribe(ROUTE_POWER_CMD)

    def readAllChannels(self, switch_time_ms: int = 20) -> bytes | None:
        """Read capacitance on all board_channels channels (120 or 200).

        On a 120-channel board this uses the legacy self-test scan
        CMD_CAP_READ_ALL (0x1232): firmware performs its own HV setup and
        returns one 120-byte per-channel pF summary (121-byte frame, fits
        the 128-byte ZGSW response limit) -- unchanged from before.

        On a board with board_channels > 120 the 0x1232 final summary would
        be a 201-byte frame, which exceeds ZGSW_MSG_MAX_SIZE=128 and is
        silently dropped by the firmware transport (__zgsw_transmit). The
        scan still runs on-device and streams one packet per channel as it
        completes (ROUTE_POWER_CMD, see _collect_cap_stream) -- this method
        collects that stream first. Only if the stream mechanism produces
        zero packets (e.g. very old firmware, or a transport issue) does it
        fall back to channelCapacitances() over every channel (0x1235,
        chunked to <=31 channels per request), packing the pF values into a
        byte array. **Both the streamed 0x1232 scan and the 0x1235 fallback
        measure with the board's CURRENT HV/frequency settings** (no
        self-test HV ramp on the >120 path) -- on a 200-channel board,
        callers must configure actuation (set_voltage/set_frequency) before
        calling this for a meaningful reading.

        Args:
            switch_time_ms: Settle time per channel (ms). Used on the
                120-channel path (0x1232 timeout) and on the >120 path (sets
                both the on-device switch time and the stream's inactivity
                timeout); ignored by the 0x1235 fallback itself.

        Returns:
            bytes of length board_channels (one byte per channel,
            capacitance in pF, clamped to 0-255) or None on failure. On a
            200-channel board, channels never measured (stalled scan, or a
            chunk that failed during fallback) read as 0.
        """
        if not self.sig_board_connected:
            return None

        n = self.board_channels
        if n == 120:
            cmd = SignalBoard.CAP_READ_ALL
            buf = struct.pack('>H', switch_time_ms)
            packet = self._make_cmd_packet(cmd, buf)
            timeout = max(5.0, (n * switch_time_ms) / 1000.0 + 10.0)
            return self._wr(packet, cmd, timeout_s=timeout)

        # board_channels > 120: 0x1232's final reply can never fit the
        # 128-byte ZGSW frame -- but the per-channel stream still works.
        streamed = self._collect_cap_stream(n, switch_time_ms)
        if streamed is not None:
            return streamed

        log.info("0x1232 stream produced no packets; falling back to "
                 "chunked 0x1235 scan (CURRENT HV/frequency, no self-test "
                 "ramp)")
        results = self.channelCapacitances(list(range(n)))
        out = bytearray(n)
        for ch, val in results.items():
            out[ch] = max(0, min(255, int(round(val))))
        return bytes(out)

    def channelCapacitances(self, channels: list[int]) -> dict[int, float]:
        """
        Measure capacitance on the given channels via CMD_CHANNEL_CAPACITANCES
        (0x1235), without altering the board's current HV/frequency actuation.

        Chunks the request into groups of at most 31 channels: the ZGSW
        response frame limit is 128 bytes (ZGSW_MSG_MAX_SIZE), and the
        subset reply is ``[u8 n, n x float32 BE]`` -- 31 channels gives
        ``1 + 31*4 = 125 <= 128``; the firmware also fails requests with
        ``n > 31``. Each chunk sends ``[u8 len, *channels]`` and parses the
        reply back onto that chunk's requested channel order.

        Args:
            channels: Channel indices to measure (0 <= ch < board_channels).
                May be any length; internally split into <=31-channel chunks.

        Returns:
            Dict mapping channel -> capacitance in pF. If a chunk fails or
            times out, a warning is logged and that chunk is skipped -- the
            returned dict contains whatever chunks succeeded.
        """
        if not self.sig_board_connected:
            log.error("Signal board not connected")
            return {}

        n_total = self.board_channels
        channels = list(channels)
        for ch in channels:
            if not (0 <= ch < n_total):
                raise ValueError(f"channel {ch} out of range [0, {n_total})")

        results: dict[int, float] = {}
        chunk_size = 31
        for start in range(0, len(channels), chunk_size):
            chunk = channels[start:start + chunk_size]
            buf = struct.pack('>B', len(chunk)) + bytes(chunk)
            packet = self._make_cmd_packet(CMD_CHANNEL_CAPACITANCES, buf)
            timeout = max(10.0, len(chunk) * 0.2 + 5.0)
            resp = self._wr(packet, CMD_CHANNEL_CAPACITANCES, timeout_s=timeout)
            if resp is None or len(resp) < 1:
                log.warning(f"channelCapacitances: chunk at offset {start} "
                            f"({len(chunk)} channels) failed/timed out")
                continue
            n_resp = resp[0]
            if n_resp != len(chunk):
                log.warning(f"channelCapacitances: chunk at offset {start} "
                            f"returned n={n_resp}, expected {len(chunk)}")
                n_resp = min(n_resp, len(chunk))
            expected_len = 1 + n_resp * 4
            if len(resp) < expected_len:
                log.warning(f"channelCapacitances: chunk at offset {start} "
                            f"reply too short ({len(resp)} < {expected_len})")
                continue
            values = struct.unpack(f'>{n_resp}f', resp[1:expected_len])
            for ch, val in zip(chunk[:n_resp], values):
                results[ch] = val

        return results

    def measureCapacitanceFull(self, n_averages: int = 1) -> dict | None:
        """Measure capacitance of currently active electrodes (full result).

        Parses the complete 21-byte CMD_MEASURE_CAPACITANCE (0x122F) response,
        returning a dict with cap_pf plus the signal-quality statistics
        (proportion, mode, n_total, n_high, n_low, n_dropped, elapsed_us).

        Falls back gracefully to {'cap_pf': ...} for legacy firmware that only
        returns the 4-byte capacitance float. Returns None on failure.

        Args:
            n_averages: Number of measurements to average.
        """
        if not self.sig_board_connected:
            return None
        cmd = 0x122F  # CMD_MEASURE_CAPACITANCE
        buf = struct.pack('>H', n_averages)
        packet = self._make_cmd_packet(cmd, buf)
        resp = self._wr(packet, cmd, timeout_s=3.0)
        if resp is None:
            return None
        full_size = ctypes.sizeof(CapacitanceMeasurement)
        if len(resp) >= full_size:
            return CapacitanceMeasurement.from_buffer_copy(resp[:full_size]).to_dict()
        if len(resp) >= 4:
            # Legacy firmware: only the cap_pf float is returned.
            return {'cap_pf': struct.unpack('>f', resp[:4])[0]}
        return None

    def measureCapacitance(self, n_averages: int = 1) -> float | None:
        """Measure capacitance of currently active electrodes.

        Uses the DropBot formula: C = amplitude / V_hv * C_cal.
        Returns capacitance in pF, or None on failure. For the full result
        (signal-quality stats), use measureCapacitanceFull().

        Args:
            n_averages: Number of measurements to average.
        """
        result = self.measureCapacitanceFull(n_averages)
        return result['cap_pf'] if result is not None else None

    # # --- High-Voltage and Electrodes ---
    def hv_test(self):
        """Test HV at 5 voltage levels. Returns raw response bytes."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.HV_TEST
        # High-voltage test: send u8[5]={40,80,120,160,200} → resp u8[8] actual voltages
        buf = struct.pack('>5B', 40, 80, 120, 160, 200)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=30)
        if response is not None:
            return {
                '40V': response[0],
                '80V': response[1],
                '120V': response[2],
                '160V': response[3],
                '200V': response[4]
            }
        return None

    def detect_shorts(self):
        """Detect chip presence and short circuit. Returns raw response bytes."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.LOADED_SHORT_DETECT
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd)
        if response is not None:
            return {
                'chip_loaded': response[0] == 1,
                'chip_short': response[1] == 1
            }
        return None

    def set_voltage(self, voltage: int):
        """Set HV electrode voltage (0-255)."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.ELECTRODE_SET_VOLT
        # voltage is a 8-bit value (unsigned char)
        buf = struct.pack('>B', min(max(voltage, 0), 255))
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    @property
    def voltage(self) -> int | None:
        """Read current HV voltage from board status (field index 14: hv_vol)."""
        status = self.GetBoardStatus('signal')
        if status is not None and len(status) >= 30:
            return struct.unpack('>H', status[28:30])[0]
        return None

    @voltage.setter
    def voltage(self, voltage: int):
        self.set_voltage(voltage)

    def set_frequency(self, frequency: int):
        """Set electrode actuation frequency in Hz."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.ELECTRODE_SET_FREQ
        # frequency is a 16-bit value (unsigned short) in big-endian
        buf = struct.pack('>H', min(max(frequency, 0), 65535))
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    @property
    def frequency(self) -> int | None:
        """Read current HV frequency from board status (field index 15: hv_freq)."""
        status = self.GetBoardStatus('signal')
        if status is not None and len(status) >= 32:
            return struct.unpack('>H', status[30:32])[0]
        return None

    @frequency.setter
    def frequency(self, frequency: int):
        self.set_frequency(frequency)

    def electrode_states(self, states: bytes):
        """Set electrode channel states from 120-element boolean array."""
        if not self.sig_board_connected:
            return False
        if not states:
            return False
        if len(states) != 16:
            return False
        cmd = SignalBoard.ELECTRODE_STATE
        packet = self._make_cmd_packet(cmd, states)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setElectrodeStates(self, electrode_states: np.ndarray | list | tuple):
        """
        Set electrode states from a board_channels-element boolean array.

        Sends the channel-indexed bitmap command CMD_ELECTRODE_STATE_CH
        (0x1242): payload is ``(board_channels+7)//8`` bytes, LSB-first (bit
        for channel ``ch`` is ``buf[ch>>3] >> (ch&7) & 1``). The firmware
        owns the chain/bit wiring map, so the host stays board-agnostic.

        Fallback: if board_channels == 120 and the 0x1242 write fails/times
        out (e.g. legacy firmware that predates the channel-bitmap command),
        falls back to the legacy 16-byte HC595-chain-packed CMD_ELECTRODE_STATE
        (0x1225) path via electrode_states().

        Args:
            electrode_states: board_channels boolean values (True = active)

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.sig_board_connected:
            log.error("Signal board not connected")
            return False

        n = self.board_channels
        states_arr = np.asarray(electrode_states, dtype=bool)
        if states_arr.shape != (n,):
            log.error(f"electrode_states must have length {n}, got {states_arr.shape}")
            return False

        n_bytes = (n + 7) // 8
        packed = np.packbits(states_arr, bitorder='little').tobytes()
        # np.packbits pads to a whole number of bytes for len(states_arr) --
        # already exactly n_bytes here since bitorder='little' packs LSB-first
        # per byte in array order; truncate/pad defensively regardless.
        if len(packed) < n_bytes:
            packed = packed + b'\x00' * (n_bytes - len(packed))
        else:
            packed = packed[:n_bytes]

        legacy = self._legacy_fw and n == 120
        if not legacy:
            cmd = CMD_ELECTRODE_STATE_CH
            packet = self._make_cmd_packet(cmd, packed)
            resp = self._wr(packet, cmd, timeout_s=2.0)
            if resp is not None:
                return True

        if n == 120:
            if not legacy:
                log.warning("0x1242 ELECTRODE_STATE_CH failed/timed out; "
                            "falling back to legacy 16-byte chain-packed protocol")
                self._legacy_fw = True  # skip the 2 s timeout on future calls
            left = 0   # uint64: channels 0-59
            right = 0  # uint64: channels 60-119
            for ch in range(120):
                if electrode_states[ch]:
                    if ch < 60:
                        left |= (1 << ch)
                    else:
                        right |= (1 << (ch - 60))
            payload = struct.pack('<QQ', left, right)
            return self.electrode_states(payload)

        return False

    def getElectrodeStates(self) -> np.ndarray | None:
        """
        Read back current electrode states as a board_channels-element boolean array.

        Prefers the channel-indexed bitmap read CMD_ELECTRODE_STATE_READ_CH
        (0x1243): response is ``(board_channels+7)//8`` bytes, LSB-first.
        Falls back to the legacy 16-byte chain-packed CMD_ELECTRODE_STATE_READ
        (0x1220) via getElectrodeStatesFromBytes() if 0x1243 fails/times out
        (only meaningful when board_channels == 120).

        Returns:
            np.ndarray of board_channels bools, or None on failure.
        """
        if not self.sig_board_connected:
            log.error("Signal board not connected")
            return None

        n = self.board_channels
        n_bytes = (n + 7) // 8
        legacy = self._legacy_fw and n == 120
        if not legacy:
            cmd = CMD_ELECTRODE_STATE_READ_CH
            packet = self._make_cmd_packet(cmd)
            resp = self._wr(packet, cmd, timeout_s=2.0)
            if resp is not None and len(resp) >= n_bytes:
                bits = np.unpackbits(
                    np.frombuffer(resp[:n_bytes], dtype=np.uint8), bitorder='little'
                )
                return bits[:n].astype(bool)

        if n == 120:
            if not legacy:
                log.warning("0x1243 ELECTRODE_STATE_READ_CH failed/timed out; "
                            "falling back to legacy 16-byte chain-packed protocol")
                self._legacy_fw = True  # skip the 2 s timeout on future calls
            packet = self._make_cmd_packet(CMD_ELECTRODE_STATE_READ)
            resp = self._wr(packet, CMD_ELECTRODE_STATE_READ, timeout_s=2.0)
            if resp is not None and len(resp) >= 16:
                return self.getElectrodeStatesFromBytes(resp[:16])

        return None

    def getElectrodeStatesFromBytes(self, electrode_bytes: bytes) -> np.ndarray:
        """
        Convert electrode state bytes back to numpy array.

        Layout: bytes 0-7 = left cascade (ch 0-59), bytes 8-15 = right (ch 60-119).

        Args:
            electrode_bytes: 16-byte array from electrode state response

        Returns:
            np.ndarray: Array of 120 boolean values
        """
        if len(electrode_bytes) != 16:
            raise ValueError(f"electrode_bytes must be 16 bytes, got {len(electrode_bytes)}")

        left, right = struct.unpack('<QQ', electrode_bytes)
        states = np.zeros(120, dtype=bool)

        for ch in range(60):
            if left & (1 << ch):
                states[ch] = True
        for ch in range(60):
            if right & (1 << ch):
                states[60 + ch] = True

        return states

    # Electrode state usage examples (bot.board_channels is 120 or 200):
    # # Set specific electrodes active
    # electrode_states = np.zeros(bot.board_channels, dtype=bool)
    # electrode_states[[10, 20, 30]] = True  # Activate electrodes 10, 20, 30
    # bot.setElectrodeStates(electrode_states)
    #
    # # Set all electrodes inactive
    # bot.setElectrodeStates(np.zeros(bot.board_channels, dtype=bool))
    #
    # # Set all electrodes active
    # bot.setElectrodeStates(np.ones(bot.board_channels, dtype=bool))
    #
    # # Read back current states (channel-indexed bitmap, board-agnostic)
    # states_array = bot.getElectrodeStates()
    #
    # # Convert legacy 16-byte chain-packed bytes back to numpy array
    # states_array = bot.getElectrodeStatesFromBytes(some_16_byte_data)

    # --- Parameter Management ---
    def _param_cmd_echoed(self, cmd: int, key: str, payload: bytes,
                          timeout_s: float = 5.0, attempts: int = 2):
        """Send a params-family command and verify the reply ECHOES the key.

        The firmware's SET/GET/PRESET replies all start with the key + NUL,
        and its resend queue re-emits un-ACKed replies -- without the echo
        check a stale resend of a PREVIOUS command's reply can be mistaken
        for this one's (field-observed aliasing, 2026-08-01). Drains stale
        replies before each attempt; retries once on mismatch/timeout.
        Returns the raw reply bytes on success, None on failure."""
        for _ in range(attempts):
            with self.response_lock:
                self.response_map.pop(cmd, None)
            packet = self._make_cmd_packet(cmd, payload)
            resp = self._wr(packet, cmd, timeout_s=timeout_s)
            if resp is not None and resp.split(b'\x00', 1)[0] == key.encode('utf-8'):
                return resp
            time.sleep(0.5)  # let any straggler resends land, drained next loop
        return None

    def setParams(self, board: str, param_name: str, value: bytes):
        """Set a parameter (RAM) on the specified board.

        Args:
            board: 'signal' or 'motor'
            param_name: Flash key (e.g., '_dp_model')
            value: Raw bytes to write (must match firmware struct size)

        Note: writes RAM only -- call presetParams(board, param_name) to
        persist to EasyFlash. [2026-08-01] No longer silently no-ops when the
        login flow hasn't set the *_board_connected flag: the command is sent
        regardless (a genuinely absent board just times out) and the reply
        must echo the key.
        """
        if board == 'signal':
            cmd = SignalBoard.SET_PARAMS
        elif board == 'motor':
            cmd = MotorBoard.SET_PARAMS
        else:
            return False
        connected = self.sig_board_connected if board == 'signal' else self.motor_board_connected
        if not connected:
            log.warning(f"setParams({board}, {param_name}): board not marked "
                        "connected (no login yet?) -- attempting anyway")
        payload = param_name.encode('utf-8') + b'\x00' + value
        return self._param_cmd_echoed(cmd, param_name, payload, timeout_s=3.0) is not None

    def getBoardParameter(self, board: str = 'signal', param : str = None):
        """Read a single parameter from the specified board by name."""
        if board == 'signal':
            board = SignalBoard
        elif board == 'motor':
            board = MotorBoard
        else:
            return None
        cmd = board.GET_PARAMS

        if param is not None:
            if param not in board.PARAMS:
                raise ValueError(f"Invalid parameter: {param}")

            param = board.PARAMS[param]
        payload = param.encode('utf-8') + b'\x00'
        # [2026-08-01] echo-verified: without this, a resend-queue straggler
        # from the PREVIOUS param read can alias this one (field-observed:
        # a padl read returning the flu blob).
        return self._param_cmd_echoed(cmd, param, payload, timeout_s=5.0)

    def getParams(self):
        """Read all parameters from both boards. Returns nested dict."""
        params = {}
        if self.motor_board_connected:
            params['motor_board'] = {}
            for param in MotorBoard.PARAMS:
                response = self.getBoardParameter('motor', param)
                if response is None:
                    continue
                # split(separator, max_splits=1) returns [part1, part2]
                parts = response.split(b'\x00', 1)
                if len(parts) == 2:
                    name_bytes, raw_big = parts
                    # Decode the name
                    struct_name_resp = name_bytes.decode('utf-8')

                    # A. Unpack as Big Endian Ints (>)
                    if struct_name_resp == '_dp_model':
                        values = ProductModel.from_dynamic_buffer(raw_big)
                    elif struct_name_resp == '_dp_temp':
                        values = TempCtrlParams.from_buffer_copy(raw_big)
                    elif struct_name_resp == '_dp_magnet':
                        values = MagnetParams.from_buffer_copy(raw_big)
                    elif struct_name_resp == '_dp_pmt':
                        values = PMTPositionParams.from_buffer_copy(raw_big)
                    elif struct_name_resp == '_dp_chip':
                        values = TrayPositionParams.from_buffer_copy(raw_big)
                    elif struct_name_resp == '_dp_tpos':
                        values = HeaterPositionParams.from_buffer_copy(raw_big)
                    elif struct_name_resp == '_dp_flu':
                        values = FilterPositionParams.from_buffer_copy(raw_big)
                    elif 'mt' in struct_name_resp:
                        # [L3] dynamic, so a legacy 56/64 B blob decodes
                        # instead of raising, and a 68 B one keeps its last
                        # three fields instead of being silently truncated.
                        values = MotorPositionParams.from_dynamic_buffer(raw_big)
                    else:
                        count = len(raw_big) // 4
                        values = struct.unpack(f'>{count}i', raw_big)
                        if len(values) == 1:
                            values = values[0]

                    if isinstance(values, ctypes.Structure):
                        values = values.to_dict()

                    params['motor_board'][param] = values

        if self.sig_board_connected:
            params['signal_board'] = {}
            for param in SignalBoard.PARAMS:
                response = self.getBoardParameter('signal', param)
                if response is None:
                    continue
                parts = response.split(b'\x00', 1)
                if len(parts) == 2:
                    name_bytes, raw_big = parts
                    # Decode the name
                    struct_name_resp = name_bytes.decode('utf-8')
                    if struct_name_resp == 'g_temp_params':
                        values = TempCtrlParams.from_buffer_copy(raw_big)
                    elif struct_name_resp == '_dp_model':
                        values = ProductModel.from_dynamic_buffer(raw_big)
                    else:
                        count = len(raw_big) // 4
                        values = struct.unpack(f'>{count}i', raw_big)
                        if len(values) == 1:
                            values = values[0]

                    if isinstance(values, ctypes.Structure):
                        values = values.to_dict()

                    params['signal_board'][param] = values

        return params

    # # --- Hardware Debug ---
    def readTempSensors(self):
        """Read all 5 temperature sensors. Returns raw response bytes (5x u16 BE, *100)."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.READ_TEMP_SENSORS
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        return None

    def setBuzzer(self, on: bool = True):
        """Control buzzer. on=True activates, on=False deactivates."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.BUZZER_CTRL
        buf = struct.pack('>B', 1 if on else 0)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setFan(self, on: bool = True, board: str = 'motor'):
        """Control fan on specified board.

        Args:
            on: True to enable, False to disable.
            board: 'motor' (instrument fans on WPI board) or 'signal' (MCU board fan pin).
        """
        if board == 'signal':
            if not self.sig_board_connected:
                return False
            cmd = SignalBoard.FAN_CTRL
            buf = struct.pack('>B', 1 if on else 0)
            packet = self._make_cmd_packet(cmd, buf)
            return self._wr(packet, cmd, timeout_s=2.0) is not None
        else:
            if not self.motor_board_connected:
                return False
            cmd = MotorBoard.FAN_CTRL
            buf = struct.pack('>B', 1 if on else 0)
            packet = self._make_cmd_packet(cmd, buf)
            return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setPower(self, on: bool = True):
        """Control system power pin. on=True enables, on=False disables."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.POWER_CTRL
        buf = struct.pack('>B', 1 if on else 0)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def readAdcData(self):
        """Read 8-channel ADC data. Returns raw response bytes (8x u16 BE, mV*100)."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.READ_ADC_DATA
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        return None

    def setCapMatch(self, c10pfOn: bool = True, c100pfOn: bool = True, c470pfOn: bool = True, gain: int = 0):
        """Set capacitance matching switches (10pF, 100pF, 470pF) and feedback gain selector.

        Args:
            c10pfOn: Enable 10pF calibration capacitor
            c100pfOn: Enable 100pF calibration capacitor
            c470pfOn: Enable 470pF calibration capacitor
            gain: Feedback gain selector (0=5K/BACK1, 1=50K/BACK2, 2=500K/BACK3)
        """
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.CAP_MATCH
        # Firmware cap_cali_set_direct(cap470, cap100, cap10) — data_buf[0]=470, [1]=100, [2]=10
        buf = struct.pack('>BBBB',
                          1 if c470pfOn else 0,
                          1 if c100pfOn else 0,
                          1 if c10pfOn else 0,
                          gain)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setHvPwmFreq(self, freq: int = 0):
        """Set HV PWM frequency in Hz. 0 stops PWM."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.HV_PWM_FREQ
        buf = struct.pack('>I', freq)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setHvValue(self, value: int = 0):
        """Set HV voltage value. Returns readback response."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.HV_VALUE
        buf = struct.pack('>H', value)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setDdsPot(self, action: int = 0, value: int = 0):
        """Control DDS digital potentiometer. action: 0=reset, 1=set value."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.DDS_POT
        buf = struct.pack('>BH', action, value)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setDdsWave(self, wave: int = 0, freq: int = 0):
        """Configure DDS waveform. wave: 0=sine, 1=triangle, 2=square. freq in Hz."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.DDS_WAVE
        buf = struct.pack('>BI', wave, freq)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setDacVoltage(self, voltage: int = 0):
        """Set DAC output voltage. Returns readback response."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.DAC_SET_VOLT
        buf = struct.pack('>H', voltage)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    # --- Temperature Control (Signal Board) ---
    def set_temp_target(self, target_c: float, channel: int = 0):
        """Set heater target temperature in degrees C."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.TEMP_SET_TARGET
        temp_val = int(target_c * 100)
        buf = struct.pack('>Bh', channel, temp_val)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def set_temp_control(self, on: bool, channel: int = 0):
        """Enable or disable heater control."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.TEMP_START_STOP
        buf = struct.pack('>BB', channel, 1 if on else 0)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def get_temp_info(self, channel: int = 0):
        """Read current temperature, target, and heater output.
        Returns (current_c, target_c, output_pct) or None."""
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.TEMP_READ_INFO
        buf = struct.pack('>B', channel)
        packet = self._make_cmd_packet(cmd, buf)
        resp = self._wr(packet, cmd, timeout_s=3.0)
        if resp and len(resp) >= 7:
            ch, cur, tgt, out = struct.unpack('>Bhhh', resp[:7])
            return (cur / 100.0, tgt / 100.0, out / 100.0)
        return None

    def get_temp_params(self, channel: int = 0):
        """Read PID parameters. Returns dict or None."""
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.TEMP_READ_PARAMS
        buf = struct.pack('>B', channel)
        packet = self._make_cmd_packet(cmd, buf)
        resp = self._wr(packet, cmd, timeout_s=3.0)
        if resp and len(resp) >= 9:
            ch, kp, ki, kd, t = struct.unpack('>Bhhhh', resp[:9])
            return {'kp': kp / 100.0, 'ki': ki / 100.0, 'kd': kd / 100.0, 'period_ms': t}
        return None

    def set_temp_params(self, kp: float, ki: float, kd: float, period_ms: int, channel: int = 0):
        """Set PID control parameters."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.TEMP_SET_PARAMS
        buf = struct.pack('>Bhhhh', channel, int(kp * 100), int(ki * 100), int(kd * 100), period_ms)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setTempHeatPWMDebug(self, heat1_percent: int = 0, heat2_percent: int = 0):
        """Directly set heater PWM duty cycles (debug). 0-100%."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.TEMP_HEAT_PWM
        buf = struct.pack('>BB', min(heat1_percent, 100), min(heat2_percent, 100))
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    # --- PMT (Signal Board) ---
    def pmt_acquire(self):
        """Start PMT ADC sampling. Returns packet count or None."""
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.PMT_ACQUIRE_START
        packet = self._make_cmd_packet(cmd)
        resp = self._wr(packet, cmd, timeout_s=10.0)
        if resp and len(resp) >= 2:
            return struct.unpack('<H', resp[:2])[0]
        return None

    def pmt_set_gain(self, gain: int):
        """Set PMT gain (0-255, via MCP41010 potentiometer)."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.PMT_GAIN_SET
        buf = struct.pack('>B', min(max(gain, 0), 255))
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def pmt_power(self, on: bool):
        """Control PMT power supply. Returns actual power state or None."""
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.PMT_POWER
        buf = struct.pack('>B', 1 if on else 0)
        packet = self._make_cmd_packet(cmd, buf)
        resp = self._wr(packet, cmd, timeout_s=3.0)
        if resp and len(resp) >= 1:
            return resp[0] == 1
        return None

    def pmt_start_debug(self, sample_limit: int = 1000):
        """Start PMT debug sampling (no motor motion). Returns echo of sample limit."""
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.PMT_START_DEBUG
        buf = struct.pack('<H', min(max(sample_limit, 0), 5000))
        packet = self._make_cmd_packet(cmd, buf)
        resp = self._wr(packet, cmd, timeout_s=5.0)
        if resp and len(resp) >= 2:
            return struct.unpack('<H', resp[:2])[0]
        return None

    def pmt_stop_debug(self):
        """Stop PMT debug sampling."""
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.PMT_STOP_DEBUG
        packet = self._make_cmd_packet(cmd)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def pmt_upload_debug(self):
        """Upload buffered PMT debug samples. Returns packet count or None."""
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.PMT_DATA_UPLOAD_DEBUG
        packet = self._make_cmd_packet(cmd)
        resp = self._wr(packet, cmd, timeout_s=10.0)
        if resp and len(resp) >= 2:
            return struct.unpack('<H', resp[:2])[0]
        return None

    # --- PMT multi-packet upload collector [WP-PMT 2026-08-28] ---
    def _collect_pmt_packets(self, cmd: int, packet_cmd: int, payload: bytes = b'',
                             *, first_packet_timeout_s: float = 30.0,
                             packet_timeout_s: float = 5.0,
                             sample_limit: int | None = None,
                             max_total_s: float = 180.0,
                             abort_event: "threading.Event | None" = None,
                             on_progress: Callable[[int, int], None] | None = None
                             ) -> PmtCapture:
        """Send `cmd` and collect the 128-byte PMT upload packets it produces.

        See the protocol notes above _PmtPacketAssembler for the packet
        format and why this cannot go through _wr(): the packets arrive as
        RESP_OK frames under one cmd key, so response_map keeps only the LAST
        one. This subscribes to the packet cmd (and, when it differs, to the
        request cmd for its [packet_count u16 LE] reply), fires the request
        fire-and-forget with _w(), and assembles the stream.

        Deliberately does NOT take the per-cmd _wr in-flight guard: nothing
        here waits on response_map, so it composes with a concurrent _wr()
        for another command on the other lane. Do not run two collections for
        the same packet_cmd concurrently (subscribe() is one callback per
        cmd) -- in this UI both entry points are single, operator-driven
        buttons on the slow lane.

        Completion (any one ends the collection):
          * every index 0..total_packets-1 seen (total_packets from the
            packet headers / the count reply)  -> complete
          * `abort_event` set                   -> aborted, partial result
          * no first frame within first_packet_timeout_s (the acquire reply
            only comes when sampling COMPLETES, ~10.3 s) -> partial/empty
          * no further packet for packet_timeout_s (packets are paced 50 ms
            apart by the firmware) -> partial result
          * the device answered RESP_BUSY (sampling already running) -> busy
          * the device answered RESP_FAIL -> error
          * `max_total_s` elapsed overall -> error. Belt-and-braces against
            the reply-aliasing history: duplicate/aliased frames keep
            refreshing the inter-packet deadline without ever advancing
            n_received, so the per-packet timeout alone cannot bound this
            loop. Default 180 s >> the ~19 s a full acquire+upload takes.

        Always returns a PmtCapture (never None): a partial upload is a
        result to report, not a failure to swallow.
        """
        assembler = _PmtPacketAssembler()
        state_lock = threading.Lock()
        frame_event = threading.Event()
        saw_frame = [False]

        def _on_packet(_cmd: int, data: bytes) -> None:
            with state_lock:
                saw_frame[0] = True
                if len(data) == 2 and assembler.expected_total is None:
                    # the command's own [packet_count u16 LE] reply, which on
                    # the debug path shares this cmd id with the packets
                    assembler.set_expected(struct.unpack('<H', data)[0])
                else:
                    assembler.feed(data)
            frame_event.set()

        def _on_count(_cmd: int, data: bytes) -> None:
            if len(data) >= 2:
                with state_lock:
                    saw_frame[0] = True
                    assembler.set_expected(struct.unpack('<H', data[:2])[0])
                frame_event.set()

        cmds = [packet_cmd] if packet_cmd == cmd else [packet_cmd, cmd]
        # Snapshot the displaced subscribers and install ours in ONE critical
        # section: doing it in two steps leaves a window in which another
        # caller's subscribe() lands between them and is then clobbered by our
        # restore below. Writes the dict directly rather than calling
        # subscribe() because that would re-take this same (non-reentrant) lock.
        with self._subscribers_lock:
            prev = {c: self._subscribers.get(c) for c in cmds}
            self._subscribers[packet_cmd] = _on_packet
            if packet_cmd != cmd:
                self._subscribers[cmd] = _on_count

        start = time.time()
        aborted = False
        busy = False
        error: str | None = None
        try:
            # Clear stale markers for this cmd so a BUSY/FAIL seen below is ours.
            with self.response_lock:
                self.response_map.pop((Frame.RESP_BUSY, cmd), None)
                self.response_map.pop(cmd, None)
            if not self._w(self._make_cmd_packet(cmd, payload)):
                error = "serial write failed"
            else:
                last_rx = start
                reported = -1
                while True:
                    with state_lock:
                        done = assembler.is_complete()
                        n_now = assembler.n_received
                        n_exp = assembler.expected_total or 0
                    if done:
                        break
                    if abort_event is not None and abort_event.is_set():
                        aborted = True
                        break
                    if time.time() - start > max_total_s:
                        error = (f"gave up after {max_total_s:.0f}s "
                                 f"({n_now}/{n_exp} packets)")
                        break
                    if n_now != reported:
                        reported = n_now
                        if on_progress is not None:
                            try:
                                on_progress(n_now, n_exp)
                            except Exception:
                                log.exception("PMT collector on_progress raised")
                    got = frame_event.wait(timeout=0.2)
                    frame_event.clear()
                    now = time.time()
                    if got:
                        last_rx = now
                        continue
                    with self.response_lock:
                        if self.response_map.pop((Frame.RESP_BUSY, cmd), None) is not None:
                            busy = True
                        # RESP_FAIL parks a None under the cmd key and does NOT
                        # dispatch, so it is invisible to the subscribers above
                        # -- without this the caller would wait out the full
                        # first-packet timeout for an answer already given.
                        elif cmd in self.response_map and self.response_map[cmd] is None:
                            self.response_map.pop(cmd, None)
                            error = "device replied FAIL"
                    if busy or error:
                        break
                    with state_lock:
                        any_frame = saw_frame[0]
                    if not any_frame:
                        if now - start > first_packet_timeout_s:
                            error = (f"no reply within {first_packet_timeout_s:.0f}s")
                            break
                    elif now - last_rx > packet_timeout_s:
                        log.warning(f"PMT upload 0x{packet_cmd:04X}: stalled at "
                                    f"{assembler.n_received}/"
                                    f"{assembler.expected_total or 0} packets")
                        break
        finally:
            with self._subscribers_lock:     # symmetric with the install above
                for c in cmds:
                    if prev.get(c) is not None:
                        self._subscribers[c] = prev[c]
                    else:
                        self._subscribers.pop(c, None)

        with state_lock:
            capture = PmtCapture(
                samples=assembler.to_samples(sample_limit),
                n_received=assembler.n_received,
                n_expected=assembler.expected_total or 0,
                missing=assembler.missing(),
                aborted=aborted, busy=busy, error=error,
                elapsed_s=time.time() - start)
        if not capture.complete:
            log.warning(f"PMT upload 0x{packet_cmd:04X} incomplete: {capture.summary()}")
        return capture

    def pmt_acquire_collect(self, first_packet_timeout_s: float = 30.0,
                            packet_timeout_s: float = 5.0,
                            sample_limit: int | None = PMT_ACQUIRE_BUFFER_SAMPLES,
                            max_total_s: float = 180.0,
                            abort_event: "threading.Event | None" = None,
                            on_progress: Callable[[int, int], None] | None = None
                            ) -> PmtCapture | None:
        """Run CMD_PMT_ACQUIRE_START (0x1227) and collect the 0x1228 upload.

        The firmware replies (packet count) only when sampling COMPLETES --
        a full-buffer run is 10240 samples at 1 kHz (~10.3 s) -- and then
        ships ~166 packets 50 ms apart (~8.3 s), so the default first-frame
        timeout is 30 s.

        `sample_limit` defaults to the firmware's ADC_BUFFER_SIZE, which a
        completed acquisition always fills; it trims the zero padding of the
        final packet. Pass None to keep every decoded value including that
        padding.
        """
        if not self.sig_board_connected:
            return None
        return self._collect_pmt_packets(
            SignalBoard.PMT_ACQUIRE_START, SignalBoard.PMT_DATA_REPORT,
            first_packet_timeout_s=first_packet_timeout_s,
            packet_timeout_s=packet_timeout_s, sample_limit=sample_limit,
            max_total_s=max_total_s,
            abort_event=abort_event, on_progress=on_progress)

    def pmt_upload_debug_collect(self, sample_limit: int | None = None,
                                 first_packet_timeout_s: float = 10.0,
                                 packet_timeout_s: float = 5.0,
                                 max_total_s: float = 180.0,
                                 abort_event: "threading.Event | None" = None,
                                 on_progress: Callable[[int, int], None] | None = None
                                 ) -> PmtCapture | None:
        """Run CMD_PMT_DATA_UPLOAD_DEBUG (0x122E) and collect its packets.

        Both the packet-count reply and the packets themselves come back on
        0x122E (told apart by length); pass the sample limit that was given
        to pmt_start_debug() to trim the final packet's zero padding.
        """
        if not self.sig_board_connected:
            return None
        return self._collect_pmt_packets(
            SignalBoard.PMT_DATA_UPLOAD_DEBUG, SignalBoard.PMT_DATA_UPLOAD_DEBUG,
            first_packet_timeout_s=first_packet_timeout_s,
            packet_timeout_s=packet_timeout_s, sample_limit=sample_limit,
            max_total_s=max_total_s,
            abort_event=abort_event, on_progress=on_progress)

    # --- PMT Motor (Motor Board) ---
    def pmt_motor_ctrl(self, position: int):
        """Move PMT motor to position (1-5). Returns current location byte."""
        if not self.motor_board_connected:
            return None
        cmd = MotorBoard.PMT_CTRL
        buf = struct.pack('>B', position)
        packet = self._make_cmd_packet(cmd, buf)
        resp = self._wr(packet, cmd, timeout_s=30.0)
        if resp and len(resp) >= 1:
            return resp[0]
        return None

    def pmt_motor_read(self):
        """Query current PMT motor position. Returns location byte."""
        if not self.motor_board_connected:
            return None
        cmd = MotorBoard.PMT_READ
        packet = self._make_cmd_packet(cmd)
        resp = self._wr(packet, cmd, timeout_s=5.0)
        if resp and len(resp) >= 1:
            return resp[0]
        return None

    def pmt_motor_set_speed(self, speed: int):
        """Set PMT motor speed."""
        if not self.motor_board_connected:
            return False
        cmd = MotorBoard.PMT_MT_SPEED_SET
        buf = struct.pack('>i', speed)
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    # --- Capacitance & Short Detection (Signal Board) ---
    def cap_short_detect(self):
        """Detect capacitor short circuit. Returns 0=ok, 1=short, or None."""
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.CAP_SHORT_DETECT
        packet = self._make_cmd_packet(cmd)
        resp = self._wr(packet, cmd, timeout_s=5.0)
        if resp and len(resp) >= 1:
            return resp[0]
        return None

    def short_circuit_detect(self):
        """Full board_channels-channel short circuit detection (legacy SHORT_CIRCUIT_DETECT).

        Returns bytes of length board_channels (120 or 200) or None. For a
        subset scan or the channel-indexed 0x1244 protocol, use short_detect().
        """
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.SHORT_CIRCUIT_DETECT
        packet = self._make_cmd_packet(cmd)
        resp = self._wr(packet, cmd, timeout_s=30.0)
        n = self.board_channels
        if resp and len(resp) >= n:
            return resp[:n]
        return None

    def short_detect(self, channels: list[int] | None = None) -> list[int]:
        """Short-detect a channel subset (or all channels) via CMD_SHORT_DETECT_CH (0x1244).

        Args:
            channels: Channels to test (0 <= ch < board_channels). None (default)
                tests all board_channels channels (payload n=0).

        Returns:
            List of channel indices found shorted. Empty list on failure/timeout.
        """
        if not self.sig_board_connected:
            log.error("Signal board not connected")
            return []
        n_total = self.board_channels
        if channels is None:
            buf = struct.pack('>B', 0)
        else:
            channels = list(channels)
            for ch in channels:
                if not (0 <= ch < n_total):
                    raise ValueError(f"channel {ch} out of range [0, {n_total})")
            buf = struct.pack('>B', len(channels)) + bytes(channels)
        packet = self._make_cmd_packet(CMD_SHORT_DETECT_CH, buf)
        # Full-board scan walks every channel (like calibrateCapacitors); use
        # a generous timeout.
        resp = self._wr(packet, CMD_SHORT_DETECT_CH, timeout_s=30.0)
        if resp is None or len(resp) < 1:
            return []
        n_shorted = resp[0]
        return list(resp[1:1 + n_shorted])

    # --- Alarm & Log (both boards) ---
    def clearAlarm(self, board: str, alarm_code: str):
        """Confirm/clear alarm by 5-char code (e.g., '04001')."""
        if board == 'signal':
            if not self.sig_board_connected: return False
            cmd = SignalBoard.CLEAR_ALARM
        elif board == 'motor':
            if not self.motor_board_connected: return False
            cmd = MotorBoard.CLEAR_ALARM
        else:
            return False
        buf = alarm_code[:5].encode('ascii').ljust(5, b'\x00')
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def presetParams(self, board: str = 'signal', param_name: str = None):
        """Save parameter(s) to flash (persist across reboots).

        The firmware PRESET_PARAMS handler saves ONE flash key per call and
        requires that key in the payload (it does save_env(data_buf)). So we must
        send the key; an empty payload silently fails. If param_name (a flash key
        like '_mt_y_dp') is given, save just that one, otherwise save all of the
        board's known parameters.
        """
        if board == 'signal':
            board_cls = SignalBoard
        elif board == 'motor':
            board_cls = MotorBoard
        else:
            return False
        connected = self.sig_board_connected if board == 'signal' else self.motor_board_connected
        if not connected:
            log.warning(f"presetParams({board}): board not marked connected "
                        "(no login yet?) -- attempting anyway")
        cmd = board_cls.PRESET_PARAMS
        keys = [param_name] if param_name else list(board_cls.PARAMS.values())
        ok = True
        for key in keys:
            payload = key.encode('utf-8') + b'\x00'
            if self._param_cmd_echoed(cmd, key, payload, timeout_s=5.0) is None:
                log.warning(f"presetParams: persisting {key} failed")
                ok = False
        return ok

    # --- Event Streaming (Signal Board) ---
    def set_event_mask(self, mask: int):
        """Set event streaming mask. Use SignalBoard.EVT_* constants.
        mask=0 disables streaming. Returns echoed mask or None."""
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.SET_REPORT_CYCLE
        buf = struct.pack('>I', mask)
        packet = self._make_cmd_packet(cmd, buf)
        resp = self._wr(packet, cmd, timeout_s=3.0)
        if resp and len(resp) >= 4:
            return struct.unpack('>I', resp[:4])[0]
        return None

    def set_report_interval(self, interval_ms: int):
        """Set event streaming interval in milliseconds (100-60000).
        Returns echoed interval or None."""
        if not self.sig_board_connected:
            return None
        cmd = SignalBoard.SET_REPORT_CYCLE2
        buf = struct.pack('>I', interval_ms)
        packet = self._make_cmd_packet(cmd, buf)
        resp = self._wr(packet, cmd, timeout_s=3.0)
        if resp and len(resp) >= 4:
            return struct.unpack('>I', resp[:4])[0]
        return None

    def setLEDIntensity(self, intensity: int = 0, fluorescence=True):
        """Set LED brightness. fluorescence=True for fluorescence LED, False for illumination."""
        if not self.sig_board_connected:
            return False
        if fluorescence:
            cmd = SignalBoard.FLUORESCENCE_CTRL
        else:
            cmd = SignalBoard.ILLUMINATION_CTRL
        intensity = min(max(0, intensity), 100)
        buf = struct.pack('>H', int(intensity/2))
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    def setBoxLight(self, state: str = "off"):
        """Control RGB indicator light. state: color code."""
        if not self.sig_board_connected:
            return False
        states = {"off": 0, "red": 1, "green": 2, "yellow": 3}

        cmd = SignalBoard.RGB_LIGHT_CTRL
        buf = struct.pack('>B', states.get(state, 0))
        packet = self._make_cmd_packet(cmd, buf)
        return self._wr(packet, cmd, timeout_s=2.0) is not None

    # # --- Motor Control ---
    def queryMotorOptoSensors(self):
        """Query all motor opto-coupler sensor states. Returns dict of sensor pairs."""
        if not self.motor_board_connected:
            return False
        cmd = MotorBoard.MOTOR_OPTO_QUERY
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)

        if response is not None:
            if len(response) < 12:
                log.error(f"Motor opto sensors response length is too short: {len(response)}")
                return None  # short frame: indexing below would raise

            with self.response_lock:  # Protect motor state from concurrent access
                    for i in range(0, 12, 2):
                        self.motors.get_motor(i//2).opto_sensors = (response[i], response[i+1])
            return self.motors.opto_sensors()
        return None

    def queryMotorHomed(self):
        """Query which motors have been homed since power-up.

        Returns dict {motor_name: bool}; True if that motor completed homing.
        """
        if not self.motor_board_connected:
            return False
        cmd = MotorBoard.MOTOR_HOMED_QUERY
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            if len(response) < 6:
                log.error(f"Motor homed response length is too short: {len(response)}")
                return None
            return {self.motors.get_motor(i).name: bool(response[i]) for i in range(6)}
        return None

    def queryMotorPosition(self, motor_id:str|int):
        """Query motor position by ID or name. Returns position in steps."""
        if not self.motor_board_connected:
            return False
        if isinstance(motor_id, str):
            motor = self.motors.get_motor_by_name(motor_id)
        elif isinstance(motor_id, int):
            motor = self.motors.get_motor(motor_id)
        else:
            raise ValueError(f"Invalid motor: {motor_id}")
        if motor is None:
            raise ValueError(f"Motor not found: {motor_id}")

        cmd = MotorBoard.MOTOR_POSITION_QUERY
        buf = struct.pack('B', motor.id)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            # response is 5 bytes long, 1 byte motor id, 4 bytes position
            if len(response) != 5:
                log.error(f"Motor position response length is too short: {len(response)}")
                return None
            motor_id = response[0]
            if motor_id != motor.id:
                log.error(f"Motor ID mismatch: {motor_id} != {motor.id}")
                return None
            motor.position = struct.unpack('>i', response[1:5])[0]
            if motor.position <= -10000000:
                motor.error = "Error: Motor position out of range: {motor.position}"
            else:
                motor.error = None
            return motor.position
        return response

    def getMotorPositions(self):
        """Query all motor positions. Returns dict of motor positions."""
        if not self.motor_board_connected:
            return False
        for motor in self.motors.motors:
            self.queryMotorPosition(motor.id)
        return self.motors.positions()

    def motorAction(self, motor_id: str|int, action:str, distance:int):
        """Execute motor action. action: abs/rel/stop/home. Returns position or error."""
        if not self.motor_board_connected:
            return False
        if isinstance(motor_id, str):
            motor = self.motors.get_motor_by_name(motor_id)
        elif isinstance(motor_id, int):
            motor = self.motors.get_motor(motor_id)
        else:
            raise ValueError(f"Invalid motor: {motor_id}")
        if motor is None:
            raise ValueError(f"Motor not found: {motor_id}")

        if action == 'relative':
            action = MotorBoard.MOTOR_ACTION_RELATIVE
        elif action == 'absolute':
            action = MotorBoard.MOTOR_ACTION_ABSOLUTE
        elif action == 'stop':
            action = MotorBoard.MOTOR_ACTION_STOP
        elif action == 'home':
            action = MotorBoard.MOTOR_ACTION_HOME
        else:
            raise ValueError(f"Invalid action: {action}")

        cmd = MotorBoard.MOTOR_CONTROL
        buf = struct.pack('>BBi', motor.id, action, distance)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=100)
        if response is not None:
            # response is 6 bytes long, 1 byte motor id, 1 byte move result, 4 bytes position
            if len(response) != 6:
                log.error(f"Motor control response length is too short: {len(response)}")
                return None
            motor_id = response[0]
            if motor_id != motor.id:
                log.error(f"Motor ID mismatch: {motor_id} != {motor.id}")
                return None
            motor.status = response[1]
            motor.position = struct.unpack('>i', response[2:6])[0]
            if motor.position <= -10000000:
                motor.error = f"Position outside of allowed range: {motor.position}"
                return motor.error
            else:
                motor.error = None
            if motor.status == "Normal":
                return motor.position
            else:
                if motor.status == "Error":
                    return motor.error
                else:
                    return motor.status
        return None

    def motorRelativeMove(self, motor_id: str|int, distance:int):
        """Move motor by relative distance in steps."""
        return self.motorAction(motor_id, 'relative', distance)

    def motorAbsoluteMove(self, motor_id: str|int, position:int):
        """Move motor to absolute position in steps."""
        return self.motorAction(motor_id, 'absolute', position)

    def motorStop(self, motor_id: str|int):
        """Stop motor immediately."""
        return self.motorAction(motor_id, 'stop', 0)

    def motorHome(self, motor_id: str|int):
        """Home motor (move to origin switch)."""
        return self.motorAction(motor_id, 'home', 0)

    def setMotorSpeed(self, motor_id: str|int, speed:int):
        """Set a motor's RUN speed (used for normal moves), in um/s. Returns the
        accepted speed, or None on failure.

        === Speeding motors up (notes for the UI settings panel) ===
        Each motor has two speeds in its `_mt_*_dp` params: `bspd` (homing speed)
        and `rspd` (run speed). Normal moves -- tray in/out, PMT/magnet/filter
        positioning -- use the RUN speed. This call sets it at RUNTIME only; it
        is NOT persisted and reverts to the flashed `rspd` on reboot. To change
        the default permanently, write `rspd` via SET_PARAMS + PRESET_PARAMS
        (flash key e.g. `_mt_cabin_dp`, the int32 at offset 52, big-endian).

        Units are um/s (38000 = 38 mm/s). Measured tray (motor 0) ceiling:
        ~40 mm/s moves cleanly, ~42 stalls. The steppers are OPEN-LOOP, so a
        stall still advances the reported position counter to the target --
        verify a speed bump physically, never from queryMotorPosition alone.

        CAUTION -- homing shares the run speed: the homing routine's
        "leave-origin" phase also runs at `run_spd`, so do NOT persist a high
        `rspd` (it makes homing run fast and it can slam/stall -- learned the
        hard way). The safe pattern for a fast move is:
            setMotorSpeed(id, fast) -> do the move -> setMotorSpeed(id, default)
        i.e. raise the speed only for the stroke and restore the default right
        after, so any home command always runs at the default. A settings panel
        should expose per-motor run speed, apply it via this method immediately
        before each move, restore the default after, and leave homing alone.
        """
        # Motor speed is in um/s
        if not self.motor_board_connected:
            return False
        if isinstance(motor_id, str):
            motor = self.motors.get_motor_by_name(motor_id)
        elif isinstance(motor_id, int):
            motor = self.motors.get_motor(motor_id)
        else:
            raise ValueError(f"Invalid motor: {motor_id}")
        if motor is None:
            raise ValueError(f"Motor not found: {motor_id}")

        cmd = MotorBoard.MOTOR_SPEED_SET
        buf = struct.pack('>Bi', motor.id, speed)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            # The response is 5 bytes long, 1 byte motor id, 4 bytes speed
            if len(response) != 5:
                log.error(f"Motor speed response length is too short: {len(response)}")
                return None
            motor_id = response[0]
            if motor_id != motor.id:
                log.error(f"Motor ID mismatch: {motor_id} != {motor.id}")
                return None
            motor.speed = struct.unpack('>i', response[1:5])[0]
            return motor.speed
        return None

    # --- Motor Macros ---
    def setTray(self, state: bool):
        """Control chip tray. state: 0=in, 1=out.

        Tri-state result: False = moved OK, True = the board reported an
        error, None = no/short reply (timeout). A timeout must NOT report
        itself as success, which the old `return False` did.
        """
        cmd = MotorBoard.CHIP_CABIN_CTRL
        buf = struct.pack('B', state & 0xFF)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=300)
        if response is None or len(response) <= MOTOR_STATUS_INDEX:
            return None
        return response[MOTOR_STATUS_INDEX] == 0xFF  # False:ok True:error

    def getTray(self):
        """Read chip tray position. Returns status byte."""
        cmd =  MotorBoard.CHIP_CABIN_READ
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            if len(response) > MOTOR_STATUS_INDEX:
                return response[MOTOR_STATUS_INDEX]
        else:
            return None

    def setMagnet(self, state: bool):
        """Control magnet. state: 0=disengage (retract), 1=engage (press chip). Returns error status."""
        cmd = MotorBoard.MAG_CTRL
        buf = struct.pack('B', state & 0xFF)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        else:
            return False

    def getMagnet(self):
        """Read magnet position. Returns status byte."""
        cmd =  MotorBoard.MAG_READ
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            if len(response) > MOTOR_STATUS_INDEX:
                return response[MOTOR_STATUS_INDEX]
        else:
            return None

    def setPogo(self, state: bool):
        """Control pogo pin plates. state: 0=press, 1=release. Returns error status."""
        cmd = MotorBoard.PUSHPAD_CTRL
        buf = struct.pack('B', state & 0xFF)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        else:
            return False

    def getPogo(self):
        """Read pogo pin plate position. Returns status byte."""
        cmd =  MotorBoard.PUSHPAD_READ
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            if len(response) > MOTOR_STATUS_INDEX:
                return response[MOTOR_STATUS_INDEX]
        else:
            return None

    def setFilter(self, pos: int):
        """Set fluorescence filter position (0-4). Returns error status."""
        cmd = MotorBoard.FLUORESCENCE_CTRL
        buf = struct.pack('B', pos & 0xFF)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        else:
            return False

    def getFilter(self):
        """Read fluorescence filter position. Returns status byte."""
        cmd =  MotorBoard.FLUORESCENCE_READ
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            if len(response) > MOTOR_STATUS_INDEX:
                return response[MOTOR_STATUS_INDEX]
        else:
            return None


    # --- Fan & Power Control (Motor Board) ---

    def motorBoardPowerCtrl(self, on: bool):
        """Control motor board power. on=True resets/powers on, on=False powers off."""
        if not self.motor_board_connected:
            return False
        cmd = MotorBoard.POWER_CTRL
        buf = struct.pack('>B', 1 if on else 0)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)
        return True

    # --- Motor Reset Commands ---
    def resetChipTrayAndMagnet(self):
        """Reset chip tray and magnet motors to home position."""
        if not self.motor_board_connected:
            return False
        cmd = MotorBoard.CABIN_MAG_RESET
        packet = self._make_cmd_packet(cmd)
        return self._wr(packet, cmd, timeout_s=60.0) is not None

    def resetPMTMotor(self):
        """Reset PMT motor to home position."""
        if not self.motor_board_connected:
            return False
        cmd = MotorBoard.PMT_RESET
        packet = self._make_cmd_packet(cmd)
        return self._wr(packet, cmd, timeout_s=30.0) is not None

    def resetFluorescenceFilter(self):
        """Reset fluorescence filter motor to home position."""
        if not self.motor_board_connected:
            return False
        cmd = MotorBoard.FLU_RESET
        packet = self._make_cmd_packet(cmd)
        return self._wr(packet, cmd, timeout_s=30.0) is not None

    def resetPogoPlates(self):
        """Reset pogo pin plate motors to home position."""
        if not self.motor_board_connected:
            return False
        cmd = MotorBoard.PUSHPAD_RESET
        packet = self._make_cmd_packet(cmd)
        return self._wr(packet, cmd, timeout_s=30.0) is not None

    # --- Firmware Upgrade ---
    def performFirmwareUpgrade(self, board: str = 'signal',
                               firmware_data: bytes = b'',
                               module_id: int = 0x00,
                               upgrade_type: int = 0x01,
                               progress_callback=None,
                               flash_baud: int = 0):
        """Complete firmware upgrade process
        Args:
            board: 'signal' or 'motor'
            firmware_data: Raw firmware binary data
            module_id: Module ID (default 0x00)
            upgrade_type: Upgrade type (default 0x01 for signal board, 0x02 for bootloader)
            progress_callback: Optional callback(sent_frames, total_frames)
            flash_baud: Optional transfer baud for the bootloader session only
                (whitelist: 230400/460800/921600; 0 = classic 115200).
                Signal board (direct serial) only; requires bootloader >=
                DroDribt-0.0.6+flash-baud. The switch lives entirely inside the
                bootloader's transfer session — any reset returns to 115200,
                so normal operation is unaffected. Older bootloaders ignore
                the extension bytes and the flash simply runs at 115200.
        Returns:
            True on success, False on failure
        """

        # Step 0: Backup all parameters before flashing
        if board != 'signal' and board != 'motor':
            return False

        if not firmware_data:
            log.error("Empty firmware data")
            return False

        saved_params = {}
        param_source = SignalBoard if board == 'signal' else MotorBoard
        log.info(f"Backing up {board} board parameters before upgrade...")
        for friendly_name, flash_key in param_source.PARAMS.items():
            resp = self.getBoardParameter(board, friendly_name)
            if resp is not None:
                parts = resp.split(b'\x00', 1)
                if len(parts) == 2:
                    saved_params[flash_key] = parts[1]  # raw bytes after name
                    log.debug(f"  Backed up {friendly_name} ({flash_key}): {len(parts[1])} bytes")
        log.info(f"Backed up {len(saved_params)} parameters")

        # Step 1: Prepare/Handshake

        # Check if the board is in bootloader mode
        # version = self.GetBoardVersion(board)
        # if 'boot' in version.lower():
        #     print(f"{board} board is in bootloader mode")
        # else:
        cmd_handshake = SignalBoard.FW_PREPARE if board == 'signal' else MotorBoard.FW_PREPARE
        buf = struct.pack('BB', module_id, upgrade_type)
        send_packet = self._make_cmd_packet(cmd_handshake, buf)

        # FW_PREPARE (== bootloader UPGRADE_HANDSHAKE, 0x_80) is consumed by the
        # running APP, which sets the update flag and resets into the bootloader
        # WITHOUT replying. The bootloader then proactively emits one handshake
        # reply after erasing the app — but on the CAN-routed motor path that single
        # reply is easily lost in the post-reset CAN re-sync window, so a single
        # send times out. Re-sending FW_PREPARE re-triggers the bootloader's
        # UPGRADE_HANDSHAKE handler (it re-arms BOOT_NEED_UPDATE and replies again),
        # so retry until the ready reply lands. Direct-serial signal flashes
        # normally succeed on the first attempt.
        prepare_attempts = 1 if board == 'signal' else 15
        resp = None
        for attempt in range(prepare_attempts):
            resp = self._wr(send_packet, cmd_handshake, timeout_s=6.0)
            if resp and len(resp) > 1:
                break
            if attempt == 0:
                # Let the app set the flag (1s) + reset + bootloader boot + first
                # app-area erase settle before the bootloader can answer a re-send.
                time.sleep(2.0)
            if board != 'signal':
                log.info(f"Waiting for {board} bootloader handshake "
                         f"(attempt {attempt + 1}/{prepare_attempts})...")
        if resp and len(resp) > 1:
            prepare_status = resp[1]
            if prepare_status == 0:
                log.info(f"{board.capitalize()} board is ready for upgrade")
            else:
                log.error(f"{board.capitalize()} board not ready for upgrade (status: {prepare_status})")
                return False
        else:
            log.error("Failed to send handshake frame")
            return False

        # Step 1b: Optional high-baud transfer session (signal/direct-serial only).
        # The bootloader is now up at 115200 and has already erased once. A
        # SECOND FW_PREPARE carrying [module, type, baud u32 BE] re-arms it
        # (BOOT_DELAY 1s -> re-erase -> ready reply at 115200) and THEN the
        # bootloader re-bauds its upgrade serial; we switch our side after the
        # ready reply lands. Fail-safe: on any timeout/reset the bootloader
        # falls back to 115200 by construction, and we restore our port below.
        baud_switched = False
        _FLASH_BAUD_WHITELIST = (230400, 460800, 921600)
        if flash_baud and board == 'signal':
            if flash_baud not in _FLASH_BAUD_WHITELIST:
                log.warning(f"flash_baud {flash_baud} not in whitelist "
                            f"{_FLASH_BAUD_WHITELIST}; flashing at 115200")
            else:
                log.info(f"Requesting transfer baud {flash_baud}...")
                buf = struct.pack('>BBI', module_id, upgrade_type, flash_baud)
                send_packet = self._make_cmd_packet(cmd_handshake, buf)
                # 1s BOOT_DELAY + full app-area re-erase before the reply.
                resp = self._wr(send_packet, cmd_handshake, timeout_s=20.0)
                if resp and len(resp) > 1 and resp[1] == 0:
                    time.sleep(0.05)  # let the bootloader's rebaud settle
                    self.serial.baudrate = flash_baud
                    self.serial.reset_input_buffer()
                    baud_switched = True
                    log.info(f"Transfer running at {flash_baud} baud")
                else:
                    log.warning("High-baud handshake got no ready reply; "
                                "continuing at 115200 (bootloader may predate "
                                "the baud extension)")
        elif flash_baud and board != 'signal':
            log.info("flash_baud ignored for motor board (CAN-routed path)")

        def _restore_baud():
            nonlocal baud_switched
            if baud_switched:
                try:
                    self.serial.baudrate = 115200
                    self.serial.reset_input_buffer()
                finally:
                    baud_switched = False
                log.info("Serial restored to 115200")

        # Step 2: Prepare firmware data with CRC
        crc_data = firmware_data + struct.pack('>I', self._crc32(firmware_data))

        # Step 3: Send firmware in chunks
        CHUNK_SIZE = 1024  # Match C++ default
        total_frames = (len(crc_data) + CHUNK_SIZE - 1) // CHUNK_SIZE

        cmd_transfer = SignalBoard.FW_TRANSFER if board == 'signal' else MotorBoard.FW_TRANSFER

        for frame_idx in tqdm(range(total_frames),
                              desc=f"Uploading firmware to {board.capitalize()} board",
                              unit="frames"):
            offset = frame_idx * CHUNK_SIZE
            chunk_size = min(CHUNK_SIZE, len(crc_data) - offset)
            chunk = crc_data[offset:offset + chunk_size]

            # Build transfer packet: module_id(1) + total_frames(2) + seq_num(2) + data
            buf = struct.pack('>BHH', module_id,
                              total_frames, frame_idx) + chunk

            send_packet = self._make_cmd_packet(cmd_transfer, buf)

            # Per-frame retry. The motor path routes each frame host->MCU serial
            # ->CAN->motor; a 1KB chunk fragments into ~130 one-shot (no CAN-layer
            # retransmit) 8-byte frames, so an occasional dropped fragment/ACK
            # must be retried here rather than aborting the whole flash.
            # NOTE: the bootloader's per-frame write is NOT idempotent (it writes
            # at a running address and the seq-number check is disabled), so a
            # retry after a *lost ACK* (frame written but ACK dropped) double-writes
            # and shifts the image. That is caught by the end-to-end image CRC32 the
            # bootloader verifies before jumping (app_crc_check) — a corrupted flash
            # reports FAIL and is simply re-run; there is no silent-bad-flash path.
            # So retry can only recover genuine drops, never make the result worse.
            # (Proper fix if drops prove common: idx-addressed idempotent writes +
            # re-ACK on duplicate in the bootloader.) Signal/serial normally
            # succeeds on attempt 1; keep a couple of retries there too.
            frame_attempts = 6 if board != 'signal' else 3
            resp = None
            for attempt in range(frame_attempts):
                resp = self._wr(send_packet, cmd_transfer, timeout_s=30.0)
                if resp is not None:
                    break
                log.warning(f"Frame {frame_idx + 1}/{total_frames} no ACK "
                            f"(attempt {attempt + 1}/{frame_attempts}), retrying...")

            if resp is None and baud_switched:
                # [fallback 2026-08-01] The high-baud session ran out of
                # retries on this frame (marginal link at speed). The
                # bootloader is still listening at the high baud and only
                # returns to 115200 after its ~120 s inactivity reset — a naive
                # immediate classic retry would talk 115200 at a 921600
                # bootloader and look bricked (field incident). Recover
                # automatically in the SAME session: drop our port to 115200,
                # wait out the bootloader's timeout reset, re-handshake (which
                # re-erases the app area), and redo the transfer classic from
                # frame 0. [2026-08-27] This applies at ANY frame index — a
                # link that dies mid-image must not abandon the bootloader at
                # the high baud.
                log.warning(f"High-baud transfer stalled at frame "
                            f"{frame_idx + 1}/{total_frames}; falling back to 115200")
                # Fast path (bootloader >= 2026-08-01): command the session
                # back down — handshake sent AT the high baud with 115200 in
                # the baud-extension bytes; the ready reply arrives at the
                # high baud, THEN the bootloader re-bauds down.
                resp2 = None
                hs_down = self._make_cmd_packet(
                    cmd_handshake, struct.pack('>BBI', module_id, upgrade_type, 115200))
                r = self._wr(hs_down, cmd_handshake, timeout_s=20.0)
                _restore_baud()
                if r and len(r) > 1 and r[1] == 0:
                    log.info("Bootloader commanded back to 115200 (fast downshift)")
                    resp2 = r
                else:
                    # Old bootloader (ignores the downshift) or reply lost:
                    # wait out its ~120 s inactivity reset.
                    log.info("Fast downshift unavailable; waiting for the "
                             "bootloader's ~120 s inactivity reset...")
                    deadline = time.time() + 150
                    while time.time() < deadline:
                        time.sleep(10)
                        hs = self._make_cmd_packet(cmd_handshake,
                                                   struct.pack('BB', module_id, upgrade_type))
                        resp2 = self._wr(hs, cmd_handshake, timeout_s=12.0)
                        if resp2 and len(resp2) > 1 and resp2[1] == 0:
                            break
                        resp2 = None
                if resp2 is None:
                    log.error("Bootloader did not come back at 115200; aborting")
                    return False
                log.info("Bootloader back at 115200 — restarting transfer (classic)")
                for retry_idx in range(total_frames):
                    offset2 = retry_idx * CHUNK_SIZE
                    chunk2 = crc_data[offset2:offset2 + min(CHUNK_SIZE, len(crc_data) - offset2)]
                    buf2 = struct.pack('>BHH', module_id, total_frames, retry_idx) + chunk2
                    pkt2 = self._make_cmd_packet(cmd_transfer, buf2)
                    r2 = None
                    for a2 in range(3):
                        r2 = self._wr(pkt2, cmd_transfer, timeout_s=30.0)
                        if r2 is not None:
                            break
                        log.warning(f"[fallback] frame {retry_idx + 1}/{total_frames} retry {a2 + 1}/3")
                    if r2 is None:
                        log.error(f"[fallback] frame {retry_idx + 1} failed; aborting")
                        return False
                    if progress_callback:
                        progress_callback(retry_idx + 1, total_frames)
                resp = r2  # fall through to finalize
                break      # exit the outer frame loop; transfer done

            if resp is None:
                log.error(f"Failed to send frame {frame_idx + 1}/{total_frames} "
                          f"after {frame_attempts} attempts")
                _restore_baud()
                return False

            if progress_callback:
                progress_callback(frame_idx + 1, total_frames)

        log.info("All frames sent. Finalizing upgrade...")

        # Step 4: Finalize upgrade
        # wait until the board responds with 0x00
        cmd_result = SignalBoard.FW_RESULT if board == 'signal' else MotorBoard.FW_RESULT

        start_time = time.time()
        resp = None
        while time.time() - start_time < 10:
            if cmd_result in self.response_map:
                resp = self.response_map.pop(cmd_result)
                break
            time.sleep(0.01)

        # The bootloader's final CRC verdict (just consumed above, still at the
        # transfer baud) is followed by its reset — after which BOTH sides must
        # be back at 115200 for the app re-login. Success or fail, restore now.
        _restore_baud()

        if resp and len(resp) >= 1 and resp[0] == 0:
            log.info("Firmware upgrade completed successfully")
            if board == 'motor':
                # The motor reboots into the new app after the flash. With
                # WP1-era firmware (async retrying CAN bring-up, HW-validated
                # 2026-07-27 rounds 2-3) the motor re-syncs the routing link BY
                # ITSELF within seconds — no power-cycle needed. Poll for it;
                # fall back to advice only if it genuinely doesn't return
                # (e.g. pre-WP1 motor firmware).
                log.info("Firmware written and verified. Motor rebooting; waiting for CAN re-sync...")
                recovered = False
                for _ in range(20):  # up to ~60s
                    time.sleep(3)
                    if self.BoardLogin('motor', timeout_s=2):
                        recovered = True
                        break
                if recovered:
                    log.info("Motor back online (CAN link re-synced automatically).")
                    version = self.GetBoardVersion('motor') or {}
                    log.info(f"Motor firmware now: {version.get('software_version')}")
                else:
                    log.warning("Motor did not re-sync within 60s. If it stays "
                                "unreachable, power-cycle both boards together "
                                "(params are preserved on the board).")
            else:
                log.info(f"Rebooting {board.capitalize()} board...")
                self.RebootBoard(board)
                # [WP-L] Re-login after reboot: wait for VERSION first so the
                # login isn't lost into the boot-log window, then retry.
                time.sleep(2)
                self.login_with_retry(board, attempts=3, wait_version_s=8.0)

            version = self.GetBoardVersion(board)
            if version is None:
                log.error(f"Failed to get {board.capitalize()} board version")
            else:
                log.info(f"{board.capitalize()} board firmware updated to: {version.get('software_version')}")

            # Step 5: Restore backed-up parameters
            if saved_params:
                log.info(f"Restoring {len(saved_params)} parameters to {board} board...")
                cmd_get = param_source.GET_PARAMS
                for flash_key, raw_value in saved_params.items():
                    # The new firmware generation may serve a different blob
                    # size for this key. Read what it serves NOW and overlay
                    # the stored bytes on the front, keeping its own tail
                    # (same merge as params_tool.restore); raw-writing an
                    # old-size blob would leave new fields as garbage.
                    reply = self._param_cmd_echoed(
                        cmd_get, flash_key, flash_key.encode('utf-8') + b'\x00',
                        timeout_s=5.0)
                    if reply is None:
                        log.warning(f"  {flash_key} not served by the new "
                                    "firmware -- skipped")
                        continue
                    current = reply[len(flash_key) + 1:]
                    value = raw_value[:len(current)] + current[len(raw_value):]
                    if len(raw_value) != len(current):
                        log.info(f"  {flash_key}: {len(raw_value)}B -> "
                                 f"{len(current)}B merged")
                    if self.setParams(board, flash_key, value):
                        log.debug(f"  Restored {flash_key}")
                    else:
                        log.warning(f"  Failed to restore {flash_key}")
                # Persist to flash
                self.presetParams(board)
                log.info("Parameters restored and saved to flash")

            return True
        else:
            if resp is None:
                log.error(f"Firmware upgrade finalization timed out")
                return False
            log.error(f"Firmware upgrade finalization failed (response: {resp[0]})")
            return False

    def upgradeFirmware(self, file_path: str | Path, ignore_version: bool = True):
        """Upgrade firmware from a .bin file. Auto-detects board from filename."""
        if not isinstance(file_path, (str, Path)):
            raise ValueError("file_path must be a string or Path")
        elif isinstance(file_path, str):
            file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path.absolute()}")
        try:
            with open(file_path, 'rb') as f:
                firmware_data = f.read()
            # Tags are variable width (DroSIG_1.0.1.23, DroDri_1.0.0.9, ...);
            # a fixed-width slice truncates or over-reads. Same pattern as
            # flash_firmware.detect_board.
            m = re.search(rb'Dro(SIG|Dri)_[0-9]+(?:\.[0-9]+){0,3}', firmware_data)
            if m:
                board = 'signal' if m.group(1) == b'SIG' else 'motor'
                fw_version = m.group(0).decode('utf8', 'replace')
            else:
                # Need to ask user to select board
                fw_version = None
                choice = input(f"Please select board: 1. Signal Board, 2. Motor Board")
                if choice == '1':
                    board = 'signal'
                elif choice == '2':
                    board = 'motor'
                else:
                    raise ValueError(f"Invalid choice: {choice}")
        except Exception as e:
            raise ValueError(f"Failed to read firmware file: {e}")

        if not self._is_connected(board):
            log.error(f"{board.capitalize()} board is not connected")
            return False

        if not ignore_version and fw_version is not None:
            version = self.GetBoardVersion(board)
            if version is None:
                log.error(f"Failed to get {board.capitalize()} board version")
                return False
            current_fw_version = version.get('software_version')
            if current_fw_version == fw_version:
                print(f"{board.capitalize()} board is already up to date")
                user_input = input(f"Do you want to proceed with upgrade? (y/n): ")
                if user_input.lower() == 'y':
                    print(f"Proceeding with upgrade...")
                else:
                    print(f"Skipping upgrade...")
                    return False
            else:
                current_fw_version_num = tuple(map(int,current_fw_version.split('_')[-1].split('.')))
                fw_version_num = tuple(map(int,fw_version.split('_')[-1].split('.')))
                if current_fw_version_num < fw_version_num:
                    print(f"Current firmware version is older than new firmware version, proceeding with upgrade...")
                else:
                    print(f"Current firmware version {current_fw_version} is newer than new firmware version {fw_version}, downgrade detected!")
                    user_input = input(f"Do you want to proceed with downgrade? (y/n): ")
                    if user_input.lower() == 'y':
                        print(f"Proceeding with downgrade...")
                    else:
                        print(f"Skipping downgrade...")
                        return False
                print(f"Current firmware version: {current_fw_version}")
                print(f"New firmware version: {fw_version}")
                print("Proceeding with upgrade...")

        return self.performFirmwareUpgrade(board=board, firmware_data=firmware_data)