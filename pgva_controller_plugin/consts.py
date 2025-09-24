# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# PGVA Default Settings
PGVA_DEFAULT_IP = "192.168.0.1"
PGVA_DEFAULT_PORT = 502  # Modbus TCP port
PGVA_DEFAULT_UNIT_ID = 0

# PGVA Communication Timeouts
PGVA_CONNECTION_TIMEOUT = 5.0  # seconds
PGVA_READ_TIMEOUT = 2.0  # seconds
PGVA_WRITE_TIMEOUT = 2.0  # seconds

# PGVA Modbus Register Addresses (from PGVA documentation)
# Input Parameters (Read-only)
PGVA_VACUUM_ACTUAL_INC = 0x100  # Current vacuum pressure in Inc units
PGVA_PRESSURE_ACTUAL_INC = 0x101  # Current pressure in Inc units
PGVA_OUTPUT_PRESSURE_ACTUAL_INC = 0x102  # Output pressure in Inc units
PGVA_FIRMWARE_VERSION = 0x103  # Firmware version
PGVA_FIRMWARE_SUB_VERSION = 0x104  # Firmware sub-version
PGVA_FIRMWARE_BUILD = 0x105  # Firmware build version
PGVA_STATUS = 0x106  # Current status (16 bits)
PGVA_TRIGGER_COUNTER = 0x107  # Number of trigger activations
PGVA_PUMP_COUNTER = 0x109  # Total pump runtime in seconds
PGVA_LIFE_COUNTER = 0x10B  # Product runtime in minutes
PGVA_VACUUM_ACTUAL_MBAR = 0x10D  # Current vacuum pressure in mbar
PGVA_PRESSURE_ACTUAL_MBAR = 0x10E  # Current pressure in mbar
PGVA_OUTPUT_PRESSURE_ACTUAL_MBAR = 0x10F  # Output pressure in mbar
PGVA_LAST_MODBUS_ERROR = 0x113  # Last Modbus error
PGVA_EXTERNAL_SENSOR_SIGNAL = 0x116  # Raw external sensor data
PGVA_WARNING = 0x119  # Warning word (16 bits)
PGVA_ERROR = 0x11A  # Error word (16 bits)

# Holding Parameters (Read/Write)
PGVA_TRIGGER_ACTUATION_TIME = 0x1000  # Trigger signal active time (msec)
PGVA_VACUUM_THRESHOLD_INC = 0x1001  # Vacuum threshold in Inc units
PGVA_PRESSURE_THRESHOLD_INC = 0x1002  # Pressure threshold in Inc units
PGVA_OUTPUT_PRESSURE_INC = 0x1003  # Output pressure in Inc units
PGVA_VACUUM_THRESHOLD_MBAR = 0x100E  # Vacuum threshold in mbar
PGVA_PRESSURE_THRESHOLD_MBAR = 0x100F  # Pressure threshold in mbar
PGVA_OUTPUT_PRESSURE_MBAR = 0x1010  # Output pressure in mbar
PGVA_MANUAL_TRIGGER = 0x1011  # Manual trigger enable/disable
PGVA_ACTIVATE_EXTERNAL_PRESSURE_SENSOR = 0x1014  # External sensor enable
PGVA_ENABLE_EXHAUST_VALVE = 0x1016  # Exhaust valve enable
PGVA_EXHAUST_VALVE_VOLUME = 0x1017  # Exhaust valve volume (ml)
PGVA_DISABLE_PUMP = 0x1018  # Pump enable/disable
PGVA_STORE_TO_EEPROM = 0x1064  # Save parameters to EEPROM
PGVA_EXTERNAL_SENSOR_VERIFICATION = 0x10CB  # External sensor verification

# Connection Parameters
PGVA_IP_ADDRESS = 0x3000  # Active IP address
PGVA_GATEWAY_ADDRESS = 0x3002  # Active gateway address
PGVA_NETMASK = 0x3004  # Active subnet mask
PGVA_MAC_ADDRESS = 0x3006  # MAC address (read-only)

# Connection Characteristics
PGVA_MODBUS_TCP_PORT = 0x100C  # TCP port for Modbus communication
PGVA_MODBUS_UNIT_ID = 0x100D  # Modbus device ID
PGVA_DHCP_SELECT = 0x1013  # DHCP/static IP selection

# External Sensor Parameters
PGVA_EXT_SENSOR_PRESSURE_LOW_LIMIT = 0x13E8  # External sensor pressure low limit
PGVA_EXT_SENSOR_PRESSURE_HIGH_LIMIT = 0x13EA  # External sensor pressure high limit
PGVA_EXT_SENSOR_VOLTAGE_LOW_LIMIT = 0x13EC  # External sensor voltage low limit
PGVA_EXT_SENSOR_VOLTAGE_HIGH_LIMIT = 0x13EE  # External sensor voltage high limit

# PGVA Control Commands
PGVA_CMD_ENABLE = 0x01
PGVA_CMD_DISABLE = 0x00
PGVA_CMD_TRIGGER = 0x01

# Topics published by this plugin
PGVA_CONNECTED = 'pgva/signals/connected'
PGVA_DISCONNECTED = 'pgva/signals/disconnected'
PGVA_PRESSURE_UPDATED = 'pgva/signals/pressure_updated'
PGVA_VACUUM_UPDATED = 'pgva/signals/vacuum_updated'
PGVA_OUTPUT_PRESSURE_UPDATED = 'pgva/signals/output_pressure_updated'
PGVA_STATUS_UPDATED = 'pgva/signals/status_updated'
PGVA_WARNINGS_UPDATED = 'pgva/signals/warnings_updated'
PGVA_ERRORS_UPDATED = 'pgva/signals/errors_updated'
PGVA_COMPREHENSIVE_STATUS_UPDATED = 'pgva/signals/comprehensive_status_updated'
PGVA_HEALTH_CHECK_UPDATED = 'pgva/signals/health_check_updated'
PGVA_DEVICE_INFO_UPDATED = 'pgva/signals/device_info_updated'
PGVA_ERROR_SIGNAL = 'pgva/signals/error'

# PGVA Service Topics -- Offered by this plugin
SET_PRESSURE = "pgva/requests/set_pressure"
SET_VACUUM = "pgva/requests/set_vacuum"
SET_OUTPUT_PRESSURE = "pgva/requests/set_output_pressure"
GET_PRESSURE = "pgva/requests/get_pressure"
GET_VACUUM = "pgva/requests/get_vacuum"
GET_OUTPUT_PRESSURE = "pgva/requests/get_output_pressure"
GET_STATUS = "pgva/requests/get_status"
GET_WARNINGS = "pgva/requests/get_warnings"
GET_ERRORS = "pgva/requests/get_errors"
GET_COMPREHENSIVE_STATUS = "pgva/requests/get_comprehensive_status"
GET_HEALTH_CHECK = "pgva/requests/get_health_check"
GET_DEVICE_INFO = "pgva/requests/get_device_info"
ENABLE_PGVA = "pgva/requests/enable"
DISABLE_PGVA = "pgva/requests/disable"
RESET_PGVA = "pgva/requests/reset"
TRIGGER_MANUAL = "pgva/requests/trigger_manual"
STORE_TO_EEPROM = "pgva/requests/store_to_eeprom"
CONNECT_PGVA = "pgva/requests/connect"
DISCONNECT_PGVA = "pgva/requests/disconnect"
