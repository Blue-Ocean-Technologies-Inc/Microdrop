import serial
import threading
import collections
import struct
import time
import ctypes

import numpy as np

from tqdm import tqdm
from pathlib import Path
from enum import IntEnum
from .commands import Frame, MotorBoard, SignalBoard, Alarms


# For parsing status responses
class SysStatusMotorBoard(ctypes.Structure):
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


class SysStatusSignalBoard(ctypes.BigEndianStructure):
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
                ("cap_match", ctypes.c_uint16)
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
        fields['box_led_state'] = box_led_state[fields['box_led_state']]
        return fields


class ProductModel(ctypes.BigEndianStructure):
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


class QuadraticParams(ctypes.BigEndianStructure):
    _fields_ = [("a", ctypes.c_float),
                ("b", ctypes.c_float),
                ("c", ctypes.c_float)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}


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


class MagnetParams(ctypes.BigEndianStructure):
    _fields_ = [("z_up", ctypes.c_int32),
                ("z_down", ctypes.c_int32),
                ("y_0", ctypes.c_int32),
                ("y_space", ctypes.c_int32)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}


class PMTPositionParams(ctypes.BigEndianStructure):
    _fields_ = [("pos", ctypes.c_int32 * 5)]

    def to_dict(self):
        return {f"pmt_pos_{i}": val for i, val in enumerate(list(self.pos))}


class FilterPositionParams(ctypes.BigEndianStructure):
    _fields_ = [("pos", ctypes.c_int32 * 5)]

    def to_dict(self):
        return {f"filter_pos_{i}": val for i, val in enumerate(list(self.pos))}


class TrayPositionParams(ctypes.BigEndianStructure):
    _fields_ = [("out_pos", ctypes.c_int32),
                ("mag_pos", ctypes.c_int32),
                ("in_pos", ctypes.c_int32)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}


class HeaterPositionParams(ctypes.BigEndianStructure):
    _fields_ = [("z_pos", ctypes.c_int32),
                ("y_pos", ctypes.c_int32)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}


class MotorPositionParams(ctypes.BigEndianStructure):
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
                ("moving_speed", ctypes.c_int32)]

    def to_dict(self):
        return {field[0]: getattr(self, field[0]) for field in self._fields_}


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

        # Threads
        self.listen_thread = None
        self.process_thread = None
        self.msg_idx = 0
        self.cmd_idx = 0

        # --- Callbacks to replace Qt Signals ---
        self.on_ready_read = None  # e.g., on_ready_read(cmd, data)
        self.on_error = None       # e.g., on_error(err_code, cmd_str)
        self.on_alarm = None       # e.g., on_alarm(alarms)

        self.time_buffer = b''
        self.sig_board_connected = False
        self.motor_board_connected = False

        self.motors = Motors()

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

            print(f"Opened {port} at {baudrate} successfully.")
            return True
        except serial.SerialException as e:
            print(f"Error opening serial port: {e}")
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
            print("Serial port closed.")

    # --- Producer Thread ---
    def _listen_thread_fn(self):
        """Reads from serial and puts data into the byte_buffer."""
        print("Listen thread started.")
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
            except serial.SerialException:
                if self.on_error:
                    self.on_error(-1, "Serial port disconnected")
                self.is_running = False  # Stop on error
        print("Listen thread stopped.")

    # --- Consumer Thread ---
    def _process_thread_fn(self):
        """
        Parses the protocol from the byte_buffer.
        This is the equivalent of your 'run()' method.
        """
        print("Process thread started.")
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
            with self.buffer_lock:
                if len(self.byte_buffer) < 4:
                    time.sleep(0.001)  # Not enough data for header yet
                    continue

                # Check for STX_HEAD1
                if self.byte_buffer[1] != Frame.HEAD1:
                    self.byte_buffer.popleft()  # Bad packet, discard STX0
                    continue
                # else:
                # header = f"{(self.byte_buffer[0] << 8) | self.byte_buffer[1]:#04x}"
                # print(f"Found header: {header.upper()} ", end='')

                # Get length field (headers + data length in C++)
                packet_len, = struct.unpack(
                    '>H', bytes(list(self.byte_buffer)[2:4]))

                # Calculate total packet length (like C++: len + 4)
                total_packet_len = packet_len + 4

                if len(self.byte_buffer) < total_packet_len:
                    time.sleep(0.001)  # Not enough data for full packet
                    continue

                # print(f"Packet length: {packet_len} bytes ", end='')

                # If we're here, we have a full packet. Extract it.
                packet_bytes = bytes([self.byte_buffer.popleft()
                                      for _ in range(total_packet_len)])

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
                print(f"CRC Error! Got: {device_crc:X}, Expected: {expected_crc:X}")
                continue

            data = packet_bytes[11:-4]

            # print(f"> response headers: {msg_idx}|{cmd_idx}|{cmd:#04x}|{Frame.to_str(ftype)} ", end='')
            # if len(data) > 0:
            #     print(f"> data: {data.hex('|')}")
            # else:
            #     print("")

            # 5. Process based on ftype
            if ftype == Frame.RESP_OK:
                with self.response_lock:
                    if self.response_map.get(Frame.REQ, 0x0000) == cmd:
                        self.response_map.pop(Frame.REQ)
                    elif self.response_map.get(Frame.RESP_BUSY, 0x0000) == cmd:
                        self.response_map.pop(Frame.RESP_BUSY)
                    self.response_map[cmd] = data
                    # Send an ACK back
                    self._ack(cmd, msg_idx, cmd_idx)
                if cmd & 0xFF == 0x72:
                    if self.on_alarm:
                        alarms = data.decode('utf8').split(';')
                        parsed_alarms = []
                        for alarm in alarms:
                            if alarm.find('A0') != -1 or alarm.find('B0') != -1:
                                idx = alarm.find('A0') if alarm.find('A0') != -1 else alarm.find('B0')
                                parsed_alarms.append(Alarms.to_str(alarm[idx:idx+6]))
                            else:
                                parsed_alarms.append(alarm)
                        self.on_alarm(cmd, parsed_alarms)
                else:
                    if self.on_ready_read:
                        self.on_ready_read(cmd, data)
            elif ftype == Frame.RESP_FAIL:
                # print(f"Error ftype: {Frame.to_str(ftype)} for cmd: {cmd:X}")
                self.response_map[cmd] = None
                if self.on_error:
                    self.on_error(ftype,
                                  f"Device responded with error `{Frame.to_str(ftype)}` for cmd {cmd:X}")
            elif ftype == Frame.ACK_OK:
                with self.response_lock:
                    self.response_map[Frame.ACK_OK] = cmd
            elif ftype == Frame.REQ:
                with self.response_lock:
                    self.response_map[Frame.REQ] = cmd
                    # Send an ACK back
                    self._ack(cmd, msg_idx, cmd_idx)
                if self.on_ready_read:
                    self.on_ready_read(cmd, data)
            elif ftype == Frame.RESP_BUSY:
                with self.response_lock:
                    self.response_map[Frame.RESP_BUSY] = cmd
            else:
                # print(f"cmd: {cmd:X} > data: {data.hex(' ')}")
                self.response_map[cmd] = None
                self._ack(cmd, msg_idx, cmd_idx)
                # print(f"Error ftype: {Frame.to_str(ftype)} for cmd: {cmd:X}")
                if self.on_error:
                    self.on_error(ftype,
                                  f"Device responded with error `{Frame.to_str(ftype)}` for cmd {cmd:X}")

        print("Process thread stopped.")

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

        msg_idx = self.msg_idx if msg_idx_override is None else msg_idx_override
        cmd_idx = self.cmd_idx if cmd_idx_override is None else cmd_idx_override

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

        if msg_idx_override is None:
            self.msg_idx = (self.msg_idx + 1) & 0xFFFF
        if cmd_idx_override is None:
            self.cmd_idx = (self.cmd_idx + 1) & 0xFFFF

        return bytes(ba)

    def _w(self, data: bytes):
        """Equivalent to _w. Just writes data."""
        if self.serial and self.serial.is_open:
            # print(f"Sending  {len(data)} bytes > {data.hex(' ')}")
            self.serial.write(data)
            return True
        return False

    def _wr(self, wbuf: bytes, cmd: int, timeout_s: float = 1.0):
        """
        Equivalent to _wr. Writes data and waits for a response.
        This is a simplified version.
        """

        # Clear any old response for this command
        with self.response_lock:
            if cmd in self.response_map:
                del self.response_map[cmd]

        if not self._w(wbuf):
            return None  # Write failed

        start_time = time.time()
        while time.time() - start_time < timeout_s:
            with self.response_lock:
                if self.response_map.get(Frame.ACK_OK, 0x0000) == cmd:
                    start_time = time.time()  # reset timer to avoid timeout
                    self.response_map.pop(Frame.ACK_OK)
                if (self.response_map.get(Frame.RESP_BUSY, False) or
                        self.response_map.get(Frame.REQ, False)):
                    start_time = time.time()  # reset timer to avoid timeout
                if cmd in self.response_map:
                    # We got a response!
                    # print(f"Got response for cmd {cmd:X}")
                    # print("-"*100)
                    return self.response_map.pop(cmd)

            time.sleep(0.01)  # Poll for response

        print(f"Command {cmd:X} timed out!")
        if self.on_error:
            self.on_error(-2, f"Timeout for cmd {cmd:X}")
        return None  # Timeout

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
            return self._update_board_connected(board, response[0] == 0)
        return self._update_board_connected(board, False)

    def GetBoardVersion(self, board: str = 'signal') -> str:
        """Get signal or motor board version"""
        if board == 'signal':
            cmd = SignalBoard.VERSION
        elif board == 'motor':
            cmd = MotorBoard.VERSION
        else:
            return None

        packet = self._make_cmd_packet(cmd)
        version = self._wr(packet, cmd)
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
        """Get signal or motor board status"""
        if board == 'signal':
            cmd = SignalBoard.STATUS
        elif board == 'motor':
            cmd = MotorBoard.STATUS
        else:
            return None
        packet = self._make_cmd_packet(cmd)
        self._w(packet)

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
        # attempt to login again
        return self.BoardLogin(board, timeout_s=5)

    # --- Convenience Functions ---
    def login(self):
        """Replicating login"""
        signal_response = self.BoardLogin('signal')
        motor_response = self.BoardLogin('motor')
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
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.SET_ALARM_LEVEL
        buf = struct.pack('B', level)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)
        return True

    def setLogLevel(self, board: str = 'signal', level: int = 0):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.SET_LOG_LEVEL
        buf = struct.pack('B', level)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)
        return True

    # # --- Capacitance ---
    def calibrateCapacitors(self):
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

    def readAllChannels(self):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.CAP_READ_ALL
        packet = self._make_cmd_packet(cmd)
        self._w(packet)
        return True

    # # --- High-Voltage and Electrodes ---
    def hv_test(self):
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
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.ELECTRODE_SET_VOLT
        # voltage is a 8-bit value (unsigned char)
        buf = struct.pack('>B', min(max(voltage, 0), 255))
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)
        return True

    @property
    def voltage(self) -> int:
        # TODO: Implement this
        return

    @voltage.setter
    def voltage(self, voltage: int):
        self.set_voltage(voltage)

    def set_frequency(self, frequency: int):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.ELECTRODE_SET_FREQ
        # frequency is a 16-bit value (unsigned short) in big-endian
        buf = struct.pack('>H', min(max(frequency, 0), 65535))
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)
        return True

    @property
    def frequency(self) -> int:
        # TODO: Implement this
        return

    @frequency.setter
    def frequency(self, frequency: int):
        self.set_frequency(frequency)

    def electrode_states(self, states: bytes):
        if not self.sig_board_connected:
            return False
        if not states:
            return False
        if len(states) != 16:
            return False
        cmd = SignalBoard.ELECTRODE_STATE
        packet = self._make_cmd_packet(cmd, states)
        self._w(packet)
        return True

    def setElectrodeStates(self, electrode_states: np.ndarray | list | tuple):
        """
        Convenience function to set electrode states from a numpy array.

        Args:
            electrode_states: numpy array of 120 boolean values representing
                            the state of each electrode (True = active, False = inactive)

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.sig_board_connected:
            print("Error: Signal board not connected")
            return False

        # Convert boolean array to 16-byte payload using same logic as C++
        payload = bytearray(16)  # Initialize 16 bytes to 0

        for electrode_id in range(120):
            if electrode_states[electrode_id]:  # Only process active electrodes
                byte_index = electrode_id // 8  # 0-14 (15 bytes needed for 120 electrodes)
                bit_pos = electrode_id % 8      # 0-7
                payload[byte_index] |= (1 << bit_pos)

        # Send using existing setElecState method
        return self.electrode_states(bytes(payload))

    def getElectrodeStatesFromBytes(self, electrode_bytes: bytes) -> np.ndarray:
        """
        Convert electrode state bytes back to numpy array.

        Args:
            electrode_bytes: 16-byte array from electrode state response

        Returns:
            np.ndarray: Array of 120 boolean values
        """
        if len(electrode_bytes) != 16:
            raise ValueError(f"electrode_bytes must be 16 bytes, got {len(electrode_bytes)}")

        states = np.zeros(120, dtype=bool)

        for electrode_id in range(120):
            byte_index = electrode_id // 8
            bit_pos = electrode_id % 8
            if electrode_bytes[byte_index] & (1 << bit_pos):
                states[electrode_id] = True

        return states

    # Electrode state usage examples:
    # # Set specific electrodes active
    # electrode_states = np.zeros(120, dtype=bool)
    # electrode_states[[10, 20, 30]] = True  # Activate electrodes 10, 20, 30
    # bot.setElectrodeStates(electrode_states)
    #
    # # Set all electrodes inactive
    # bot.setElectrodeStates(np.zeros(120, dtype=bool))
    #
    # # Set all electrodes active
    # bot.setElectrodeStates(np.ones(120, dtype=bool))
    #
    # # Convert byte array back to numpy array
    # states_array = bot.getElectrodeStatesFromBytes(some_byte_data)

    # --- Parameter Management ---
    def setParams(self, params: dict):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.SET_PARAMS
        buf = struct.pack('>B', params)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)
        return True

    def getBoardParameter(self, board: str = 'signal', param : str = None):
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
        packet = self._make_cmd_packet(cmd, payload)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        return None

    def getParams(self):
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
                    elif struct_name_resp == '_dp_magic':
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
                        values = MotorPositionParams.from_buffer_copy(raw_big)
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
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.READ_TEMP_SENSORS
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        return None

    def setTempHeatPWMDebug(self, heat1_percent: int = 0, heat2_percent: int = 0):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.TEMP_HEAT_PWM_DEBUG
        buf = struct.pack('>BB', heat1_percent, heat2_percent)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setBuzzer(self, on: bool = True):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.BUZZER_CTRL
        buf = struct.pack('>B', 1 if on else 0)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setFan(self, on: bool = True):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.FAN_CTRL
        buf = struct.pack('>B', 1 if on else 0)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setPower(self, on: bool = True):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.POWER_CTRL
        buf = struct.pack('>B', 1 if on else 0)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def readAdcData(self):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.READ_ADC_DATA
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        return None

    def setCapMatch(self, c10pfOn: bool = True, c100pfOn: bool = True, c470pfOn: bool = True):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.CAP_MATCH
        buf = struct.pack('>BBB', 1 if c10pfOn else 0, 1 if c100pfOn else 0, 1 if c470pfOn else 0)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setHvPwmFreq(self, freq: int = 0):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.HV_PWM_FREQ
        buf = struct.pack('>I', freq)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setHvValue(self, value: int = 0):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.HV_VALUE
        buf = struct.pack('>H', value)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setDdsPot(self, action: int = 0, value: int = 0):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.DDS_POT
        buf = struct.pack('>BBH', action, value)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setDdsWave(self, wave: int = 0, freq: int = 0):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.DDS_WAVE
        buf = struct.pack('>BBI', wave, freq)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setDacVoltage(self, voltage: int = 0):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.DAC_SET_VOLT
        buf = struct.pack('>H', voltage)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setLEDIntensity(self, intensity: int = 0):
        if not self.sig_board_connected:
            return False
        cmd = SignalBoard.ILLUMINATION_CTRL
        intensity = min(max(0, intensity), 100)
        buf = struct.pack('>B', intensity)
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    def setBoxLight(self, state: str = "off"):
        if not self.sig_board_connected:
            return False
        states = {"off": 0, "red": 1, "green": 2, "yellow": 3}

        cmd = SignalBoard.RGB_LIGHT_CTRL
        buf = struct.pack('>B', states.get(state, 0))
        packet = self._make_cmd_packet(cmd, buf)
        self._w(packet)

    # # --- Motor Control ---
    def queryMotorOptoSensors(self):
        if not self.motor_board_connected:
            return False
        cmd = MotorBoard.MOTOR_OPTO_QUERY
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)

        if response is not None:
            if len(response) < 12:
                print(f"Error: Motor opto sensors response length is too short: {len(response)}")

            for i in range(0, 12, 2):
                self.motors.get_motor(i//2).opto_sensors = (response[i], response[i+1])
            return self.motors.opto_sensors()
        return None

    def queryMotorPosition(self, motor_id:str|int):
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
                print(f"Error: Motor position response length is too short: {len(response)}")
                return None
            motor_id = response[0]
            if motor_id != motor.id:
                print(f"Error: Motor ID mismatch: {motor_id} != {motor.id}")
                return None
            motor.position = struct.unpack('>i', response[1:5])[0]
            if motor.position <= -10000000:
                motor.error = "Error: Motor position out of range: {motor.position}"
            else:
                motor.error = None
            return motor.position
        return response

    def getMotorPositions(self):
        if not self.motor_board_connected:
            return False
        for motor in self.motors.motors:
            self.queryMotorPosition(motor.id)
        return self.motors.positions()

    def motorAction(self, motor_id: str|int, action:str, distance:int):
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
                print(f"Error: Motor control response length is too short: {len(response)}")
                return None
            motor_id = response[0]
            if motor_id != motor.id:
                print(f"Error: Motor ID mismatch: {motor_id} != {motor.id}")
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
        return self.motorAction(motor_id, 'relative', distance)

    def motorAbsoluteMove(self, motor_id: str|int, position:int):
        return self.motorAction(motor_id, 'absolute', position)

    def motorStop(self, motor_id: str|int):
        return self.motorAction(motor_id, 'stop', 0)

    def motorHome(self, motor_id: str|int):
        return self.motorAction(motor_id, 'home', 0)

    def setMotorSpeed(self, motor_id: str|int, speed:int):
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
                print(f"Error: Motor speed response length is too short: {len(response)}")
                return None
            motor_id = response[0]
            if motor_id != motor.id:
                print(f"Error: Motor ID mismatch: {motor_id} != {motor.id}")
                return None
            motor.speed = struct.unpack('>i', response[1:5])[0]
            return motor.speed
        return None

    # --- Motor Macros ---
    def setTray(self, state: bool):
        cmd = MotorBoard.CHIP_CABIN_CTRL
        buf = struct.pack('B', state & 0xFF)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=300)
        if response is not None:
            if len(response) > 11:
                return response[11] == 0xFF # False:ok True:error
        else:
            return False

    def getTray(self):
        cmd =  MotorBoard.CHIP_CABIN_READ
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            if len(response) > 11:
                return response[11]
        else:
            return None

    def setMagnet(self, state: bool):
        cmd = MotorBoard.MAG_CTRL
        buf = struct.pack('B', state & 0xFF)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        else:
            return False

    def getMagnet(self):
        cmd =  MotorBoard.MAG_READ
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            if len(response) > 11:
                return response[11]
        else:
            return None

    def setPogo(self, state: bool):
        cmd = MotorBoard.PUSHPAD_CTRL
        buf = struct.pack('B', state & 0xFF)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        else:
            return False

    def getPogo(self):
        cmd =  MotorBoard.PUSHPAD_READ
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            if len(response) > 11:
                return response[11]
        else:
            return None

    def setFilter(self, pos: int):
        cmd = MotorBoard.FLUORESCENCE_CTRL
        buf = struct.pack('B', pos & 0xFF)
        packet = self._make_cmd_packet(cmd, buf)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            return response
        else:
            return False

    def getFilter(self):
        cmd =  MotorBoard.FLUORESCENCE_READ
        packet = self._make_cmd_packet(cmd)
        response = self._wr(packet, cmd, timeout_s=5)
        if response is not None:
            if len(response) > 11:
                return response[11]
        else:
            return None


    # --- Firmware Upgrade ---
    def performFirmwareUpgrade(self, board: str = 'signal',
                               firmware_data: bytes = b'',
                               module_id: int = 0x00,
                               upgrade_type: int = 0x01,
                               progress_callback=None):
        """Complete firmware upgrade process
        Args:
            board: 'signal' or 'motor'
            firmware_data: Raw firmware binary data
            module_id: Module ID (default 0x00)
            upgrade_type: Upgrade type (default 0x01 for signal board, 0x02 for bootloader)
            progress_callback: Optional callback(sent_frames, total_frames)
        Returns:
            True on success, False on failure
        """

        # Step 1: Prepare/Handshake
        if board != 'signal' and board != 'motor':
            return False

        if not firmware_data:
            print("Error: Empty firmware data")
            return False

        # Check if the board is in bootloader mode
        # version = self.GetBoardVersion(board)
        # if 'boot' in version.lower():
        #     print(f"{board} board is in bootloader mode")
        # else:
        cmd_handshake = SignalBoard.FW_PREPARE if board == 'signal' else MotorBoard.FW_PREPARE
        buf = struct.pack('BB', module_id, upgrade_type)
        send_packet = self._make_cmd_packet(cmd_handshake, buf)
        resp = self._wr(send_packet, cmd_handshake, timeout_s=30.0)
        if resp and len(resp) > 1:
            prepare_status = resp[1]
            if prepare_status == 0:
                print(f"{board.capitalize()} board is ready for upgrade")
            else:
                print(f"Error: {board.capitalize()} board not ready for upgrade (status: {prepare_status})")
                return False
        else:
            print("Error: Failed to send handshake frame")
            return False

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
            resp = self._wr(send_packet, cmd_transfer, timeout_s=30.0)  # Longer timeout

            if resp is None:
                print(f"Error: Failed to send frame {frame_idx + 1}/{total_frames}")
                return False

            if progress_callback:
                progress_callback(frame_idx + 1, total_frames)

        print("All frames sent. Finalizing upgrade...")

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

        if resp and len(resp) >= 1 and resp[0] == 0:
            print("Firmware upgrade completed successfully!")
            print(f"Rebooting {board.capitalize()} board...")
            self.RebootBoard(board)

            version = self.GetBoardVersion(board)
            if version is None:
                print(f"Error: Failed to get {board.capitalize()} board version")
            else:
                print(f"{board.capitalize()} board firmware updated to version: {version.get('software_version')}")
            return True
        else:
            if resp is None:
                print(f"Error: Firmware upgrade finalization timed out")
                return False
            print(f"Error: Firmware upgrade finalization failed (response: {resp[0]})")
            return False

    def upgradeFirmware(self, file_path: str | Path, ignore_version: bool = True):
        if not isinstance(file_path, (str, Path)):
            raise ValueError("file_path must be a string or Path")
        elif isinstance(file_path, str):
            file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path.absolute()}")
        try:
            with open(file_path, 'rb') as f:
                firmware_data = f.read()
            if firmware_data.find(b'DroSIG') != -1:
                board = 'signal'
                fw_idx = firmware_data.find(b'DroSIG')
                fw_version = firmware_data[fw_idx:fw_idx+len(b'DroSIG_0.0.0.0')].decode('utf8')
            elif firmware_data.find(b'DroDri') != -1:
                board = 'motor'
                fw_idx = firmware_data.find(b'DroDri')
                fw_version = firmware_data[fw_idx:fw_idx+len(b'DroDri_0.0.0.0')].decode('utf8')
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
            print(f"Error: {board.capitalize()} board is not connected")
            return False

        if not ignore_version and fw_version is not None:
            version = self.GetBoardVersion(board)
            if version is None:
                print(f"Error: Failed to get {board.capitalize()} board version")
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