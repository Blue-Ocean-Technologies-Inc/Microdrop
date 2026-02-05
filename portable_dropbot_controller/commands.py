class Frame:
    # --------------------------------------------------------
    # Frame Header Constants
    # --------------------------------------------------------
    HEAD = 0x7CF1  # Frame header
    HEAD0 = HEAD >> 8  # First byte of frame header
    HEAD1 = HEAD & 0xFF  # Second byte of frame header
    HEAD_SIZE = 11  # Frame header size (bytes)
    TYPE_INDEX = 10  # Frame type/index field

    # --------------------------------------------------------
    # ACK Frame Results
    # --------------------------------------------------------
    ACK_OK = 0x00  # ACK frame: command checksum passed
    ACK_FAIL = 0x01  # ACK frame: command checksum failed

    # --------------------------------------------------------
    # Request Frame (Active Command Frames)
    # --------------------------------------------------------
    REQ = 0xFF  # Request frame

    # --------------------------------------------------------
    # Response Frames (Passive Command Frames)
    # --------------------------------------------------------
    RESP_OK = 0xF0  # Response: success
    RESP_FAIL = 0xF1  # Response: failure
    RESP_BUSY = 0xF2  # Response: system busy
    RESP_ERR = 0xF3  # Response: command error
    RESP_UNKNOWN = 0xF4  # Response: unknown command
    RESP_TIMEOUT = 0xF5  # Response: timeout

    # -----------------------------------------
    # General status / error codes
    # -----------------------------------------
    FAULT = 0xFFFFFFFF  # Fault state

    # --------------------------------------------------------
    # Frame Index Macros
    # --------------------------------------------------------
    frame_idx = 0

    def idx(self):
        """Increment frame index, wrap around at 0xFFFF"""
        self.frame_idx = (self.frame_idx + 1) % 0xFFFF
        return self.frame_idx

    @staticmethod
    def to_str(ftype: int) -> str:
        return {
            Frame.REQ: "REQUEST",
            Frame.ACK_OK: "ACK OK",
            Frame.ACK_FAIL: "ACK FAIL",
            Frame.RESP_OK: "SUCCESS",
            Frame.RESP_FAIL: "FAIL",
            Frame.RESP_BUSY: "BUSY",
            Frame.RESP_ERR: "CMD ERROR",
            Frame.RESP_UNKNOWN: "UNKNOWN CMD",
            Frame.RESP_TIMEOUT: "TIMEOUT",
        }.get(ftype, "FAIL")


class MotorBoard:
    HEAD = 0x11
    # -------------------------------
    # Main Board Commands
    # -------------------------------
    RESET = (HEAD << 8) | 0x00  # MCU reset
    LOGIN = (HEAD << 8) | 0x01  # Handshake login
    VERSION = (HEAD << 8) | 0x02  # Firmware version
    HW_RESET = (HEAD << 8) | 0x03  # Hardware reset self-test
    STATUS = (HEAD << 8) | 0x04  # System status

    # -----------------------------------------
    # Chip cabin door commands
    # -----------------------------------------
    CHIP_CABIN_CTRL = (
        HEAD << 8
    ) | 0x20  # Chip tray control (u8: 0 in, 1 out) → returns status
    CHIP_CABIN_READ = (HEAD << 8) | 0x21  # Chip tray status read

    # -------------------------------
    # Magnet Commands
    # -------------------------------
    MAG_CTRL = (
        HEAD << 8
    ) | 0x22  # Magnet control (u8: 0 press, 1 release) → returns status
    MAG_READ = (HEAD << 8) | 0x23  # Read magnet status → returns status

    # -------------------------------
    # Push pad commands
    # -------------------------------
    PUSHPAD_CTRL = (
        HEAD << 8
    ) | 0x24  # Push pad control (u8: 0 press, 1 release) → returns status
    PUSHPAD_READ = (HEAD << 8) | 0x25  # Read push pad status → returns status

    # -------------------------------
    # Fluorescence commands
    # -------------------------------
    FLUORESCENCE_CTRL = (
        HEAD << 8
    ) | 0x26  # Fluorescence control (u8: 0 channel 1, 1 channel 2, 2 channel 3, 3 channel 4, 4 channel 5) → returns status
    FLUORESCENCE_READ = (HEAD << 8) | 0x27  # Read fluorescence status → returns status

    # -------------------------------
    # PMT commands
    # -------------------------------
    PMT_CTRL = (HEAD << 8) | 0x28  # PMT control (u8: 0 start, 1 stop) → returns status
    PMT_READ = (HEAD << 8) | 0x29  # Read PMT status → returns status

    # -------------------------------
    # Motor Control Commands
    # -------------------------------
    MOTOR_CONTROL = (HEAD << 8) | 0xB0  # Motor control command
    MOTOR_SPEED_SET = (HEAD << 8) | 0xB1  # Motor speed setting
    MOTOR_POSITION_QUERY = (HEAD << 8) | 0xB3  # Query motor position
    MOTOR_OPTO_QUERY = (
        HEAD << 8
    ) | 0xB4  # Query all motor opto-isolators, returns u8[12]

    MOTOR_ACTION_ABSOLUTE = 0
    MOTOR_ACTION_RELATIVE = 1
    MOTOR_ACTION_STOP = 3
    MOTOR_ACTION_HOME = 4

    # -------------------------------
    # Parameter Commands
    # -------------------------------
    SET_PARAMS = (HEAD << 8) | 0x60  # Set parameters
    GET_PARAMS = (HEAD << 8) | 0x61  # Get parameters
    PRESET_PARAMS = (HEAD << 8) | 0x62  # Preset parameters

    PARAMS = {
        "filter_defaults": "_dp_flu",
        "tray_defaults": "_dp_chip",
        "magnet_defaults": "_dp_magic",
        "pmt_defaults": "_dp_pmt",
        "pogo_defaults": "_dp_pushpad",
        #   'heater': '_dp_temp',                # TEC parameters (not used)
        #   'temperature_defaults': '_dp_tpos',  # TEC position (not used)
        "product_model": "_dp_model",
        "tray_motor": "_mt_cabin_dp",
        "pmt_motor": "_mt_y_dp",
        "magnet_motor": "_mt_z_dp",
        "filter_motor": "_mt_flu_dp",
        "pogo_motor_left": "_mt_padl_dp",
        "pogo_motor_right": "_mt_padr_dp",
    }

    # -------------------------------
    # Firmware Upgrade Commands
    # -------------------------------
    FW_PREPARE = (HEAD << 8) | 0x80
    FW_TRANSFER = (HEAD << 8) | 0x81
    FW_RESULT = (HEAD << 8) | 0x82


class SignalBoard:
    HEAD = 0x12
    # -------------------------------
    # Main Board Commands
    # -------------------------------
    RESET = (HEAD << 8) | 0x00  # MCU reset
    LOGIN = (HEAD << 8) | 0x01  # Handshake login
    VERSION = (HEAD << 8) | 0x02  # Firmware version
    HW_RESET = (HEAD << 8) | 0x03  # Hardware reset self-test
    STATUS = (HEAD << 8) | 0x04  # System status

    # -------------------------------
    # Data Reporting Commands
    # -------------------------------
    DATA_REPORT = (HEAD << 8) | 0x05  # Data reporting command
    SET_REPORT_CYCLE = (HEAD << 8) | 0xF6  # Set data reporting period
    SET_REPORT_CYCLE2 = (HEAD << 8) | 0xF7  # Set data reporting period 2

    # -------------------------------
    # Temperature Control Commands
    # -------------------------------
    TEMP_SET_TARGET = (HEAD << 8) | 0x10  # Set target temperature
    TEMP_START_STOP = (HEAD << 8) | 0x11  # Start/stop temperature control
    TEMP_READ_INFO = (HEAD << 8) | 0x12  # Read temperature control info
    TEMP_READ_PARAMS = (HEAD << 8) | 0x13  # Read control parameters
    TEMP_SET_PARAMS = (HEAD << 8) | 0x14  # Set control parameters
    TEMP_SET_AUTO_REPORT = (
        HEAD << 8
    ) | 0x15  # Enable/disable auto temperature reporting
    TEMP_AUTO_REPORT = (
        HEAD << 8
    ) | 0x16  # Automatic temperature report (device → host)

    # -------------------------------
    # Lighting Control Commands
    # -------------------------------
    RGB_LIGHT_CTRL = (HEAD << 8) | 0x21  # RGB light control
    ILLUMINATION_CTRL = (HEAD << 8) | 0x22  # Illumination light control
    FLUORESCENCE_CTRL = (HEAD << 8) | 0x23  # Fluorescence light control

    # -------------------------------
    # Electrode Signal Commands
    # -------------------------------
    ELECTRODE_SET_VOLT = (HEAD << 8) | 0x24  # Set electrode signal voltage
    ELECTRODE_STATE = (HEAD << 8) | 0x25  # Electrode signal output
    ELECTRODE_SET_FREQ = (HEAD << 8) | 0x26  # Set electrode signal frequency

    # -------------------------------
    # PMT
    # -------------------------------
    PMT_ACQUIRE_START = (
        HEAD << 8
    ) | 0x27  # Host → device: u16 total packets (big-endian). Device ACKs or starts immediately.
    PMT_DATA_REPORT = (
        HEAD << 8
    ) | 0x28  # Device → host: u16 total, u16 index, u16[62] samples (big-endian)
    PMT_GAIN_SET = (HEAD << 8) | 0x29  # Host sets gain: u8 gain value
    PMT_STATUS_REPORT = (
        HEAD << 8
    ) | 0x2A  # Device reports status: u8 state (0 start, 1 finished, 2 aborted)

    # -------------------------------
    # Capacitance / HV / Chip Loaded / Short Detection
    # -------------------------------
    CAP_CALIBRATE = (
        HEAD << 8
    ) | 0x31  # Capacitance calibration → returns u16(10pF), u16(100pF), u16(470pF)
    CAP_READ_ALL = (
        HEAD << 8
    ) | 0x32  # Capacitance read → returns u8[120] values (one-shot)
    HV_TEST = (
        HEAD << 8
    ) | 0x33  # High-voltage test: send u8[5]={40,80,120,160,200} → resp u8[8] actual voltages
    CAP_PROGRESS_REPORT = (
        HEAD << 8
    ) | 0x34  # Capacitance detection progress: data[0]=index, data[1]=value
    LOADED_SHORT_DETECT = (
        HEAD << 8
    ) | 0xAC  # Chip load status & short detection → returns u8 chip loaded (0/1), u8 short(0/1)

    # -------------------------------
    # Parameter Commands
    # -------------------------------
    SET_PARAMS = (HEAD << 8) | 0x60  # Set parameters
    GET_PARAMS = (HEAD << 8) | 0x61  # Get parameters
    PRESET_PARAMS = (HEAD << 8) | 0x62  # Preset parameters

    PARAMS = {"product_model": "_dp_model", "heater": "g_temp_params"}

    # -------------------------------
    # Alarm Commands
    # -------------------------------
    SET_ALARM_LEVEL = (HEAD << 8) | 0x73  # Set alarm level
    REPORT_ALARM = (HEAD << 8) | 0x72  # Report alarm

    # -------------------------------
    # Log Commands
    # -------------------------------
    SET_LOG_LEVEL = (HEAD << 8) | 0x71  # Set log level
    REPORT_LOG = (HEAD << 8) | 0x70  # Report log

    # -------------------------------
    # Firmware Upgrade Commands
    # -------------------------------
    FW_PREPARE = (HEAD << 8) | 0x80
    FW_TRANSFER = (HEAD << 8) | 0x81
    FW_RESULT = (HEAD << 8) | 0x82

    # -------------------------------
    # Hardware Debug Commands (0x12A0 – 0x12AB)
    # -------------------------------
    READ_TEMP_SENSORS = (
        HEAD << 8
    ) | 0xA0  # Read temperature sensors s16[5], scaled ×100
    TEMP_HEAT_PWM = (
        HEAD << 8
    ) | 0xA1  # Temp control heater PWM debug (u8 heater1 %, u8 heater2 %)
    BUZZER_CTRL = (HEAD << 8) | 0xA2  # Buzzer: u8 0=on, 1=off
    FAN_CTRL = (HEAD << 8) | 0xA3  # Fan: u8 0=on, 1=off
    POWER_CTRL = (HEAD << 8) | 0xA4  # Power: u8 0=on, 1=off
    READ_ADC_DATA = (HEAD << 8) | 0xA5  # Read ADC data u16[8], scaled ×100
    CAP_MATCH = (
        HEAD << 8
    ) | 0xA6  # Capacitance matching: u8 10pF, u8 100pF, u8 470pF switches
    HV_PWM_FREQ = (HEAD << 8) | 0xA7  # High-voltage PWM frequency u32 Hz
    HV_VALUE = (HEAD << 8) | 0xA8  # HV value u16 input → resp: u16 HV×100, u32 PWM freq
    DDS_POT = (
        HEAD << 8
    ) | 0xA9  # DDS digital potentiometer: u8(0 reset /1 set), u16 value → echo
    DDS_WAVE = (
        HEAD << 8
    ) | 0xAA  # DDS waveform: u8(0 sine /1 triangle /2 square), u32 frequency Hz
    DAC_SET_VOLT = (HEAD << 8) | 0xAB  # DAC voltage set u16 → resp: u16 feedback ×100

    # -----------------------------------------
    # Motor-related commands
    # -----------------------------------------
    REQ_MT_CTRL = (HEAD << 8) | 0xB0  # Motor control command
    REQ_MT_SET_SPD = (HEAD << 8) | 0xB1  # Motor speed setting
    REQ_MT_GET_POS = (HEAD << 8) | 0xB3  # Query motor position


class Alarms:
    ALARM_MT_HW_CODE = "A0100"  # Motor board hardware alarm code
    ALARM_MT_TMP_SENS_FAULT = "A0200"  # Signal board temperature sensor fault
    ALARM_MT_CHPIP_STALL = "B0100"  # Motor board chip stall alarm code
    ALARM_MT_OVER_TEMP = "B0102"  # Motor board over temperature alarm code
    ALARM_MT_OVER_CURRENT = "B0101"  # Motor board over current alarm code
    ALARM_MT_OVER_STEP = "B0103"  # Motor board over step alarm code
    ALARM_MT_OPTO_CODE = "B0200"  # Motor board opto alarm code

    @staticmethod
    def to_str(alarm_code: str) -> str:
        return {
            Alarms.ALARM_MT_HW_CODE: "Motor board hardware alarm",
            Alarms.ALARM_MT_TMP_SENS_FAULT: "Temperature sensor fault",
            Alarms.ALARM_MT_CHPIP_STALL: "Chip stall",
            Alarms.ALARM_MT_OVER_TEMP: "Over temperature",
            Alarms.ALARM_MT_OVER_CURRENT: "Over current",
            Alarms.ALARM_MT_OVER_STEP: "Over step",
            Alarms.ALARM_MT_OPTO_CODE: "Endstop triggered",
        }.get(alarm_code, f"Unknown alarm code: {alarm_code}")
