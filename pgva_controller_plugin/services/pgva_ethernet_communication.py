"""
Ethernet communication service for Festo PGVA device.
Handles Modbus TCP communication with the PGVA pressure/vacuum generator.
"""
import time
from typing import Dict
from logger.logger_service import get_logger
from .pgva_status_parser import PGVAStatusParser
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
from ..consts import (
    PGVA_PRESSURE_ACTUAL_MBAR, PGVA_VACUUM_ACTUAL_MBAR,
    PGVA_OUTPUT_PRESSURE_ACTUAL_MBAR, PGVA_PRESSURE_THRESHOLD_MBAR,
    PGVA_VACUUM_THRESHOLD_MBAR, PGVA_OUTPUT_PRESSURE_MBAR,
    PGVA_STATUS, PGVA_WARNING, PGVA_ERROR, PGVA_MANUAL_TRIGGER,
    PGVA_TRIGGER_ACTUATION_TIME, PGVA_CMD_TRIGGER, PGVA_DISABLE_PUMP, 
    PGVA_CMD_DISABLE, PGVA_CMD_ENABLE, PGVA_STORE_TO_EEPROM, 
    PGVA_FIRMWARE_VERSION, PGVA_FIRMWARE_SUB_VERSION, PGVA_FIRMWARE_BUILD, 
    PGVA_TRIGGER_COUNTER, PGVA_PUMP_COUNTER, PGVA_LIFE_COUNTER
)

logger = get_logger(__name__)


class PGVAEthernetCommunication:
    """
    Handles ethernet communication with Festo PGVA device using Modbus TCP.
    """
    
    def __init__(self, ip_address: str = "192.168.0.1", port: int = 502,
                 unit_id: int = 0):
        """
        Initialize PGVA ethernet communication.
        
        Args:
            ip_address: IP address of the PGVA device
            port: Port number for Modbus TCP communication
            unit_id: Modbus unit ID for the device
        """
        self.ip_address = ip_address
        self.port = port
        self.unit_id = unit_id
        self.connected = False
        self.client = ModbusTcpClient(host=ip_address, port=port)
        logger.info("Using pymodbus for PGVA communication")
        
    def connect(self, timeout: float = 5.0) -> bool:
        """
        Establish connection to the PGVA device.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.connected = self.client.connect()
            if self.connected:
                logger.info(f"Connected to PGVA at {self.ip_address}:"
                            f"{self.port}")
            else:
                logger.error("Failed to connect to PGVA")
            return self.connected
        except Exception as e:
            logger.error(f"Failed to connect to PGVA: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the PGVA device."""
        try:
            if self.client:
                self.client.close()
                logger.info("Disconnected from PGVA")
        except Exception as e:
            logger.error(f"Error disconnecting from PGVA: {e}")
        finally:
            self.connected = False

    def read_pressure_mbar(self) -> float:
        """
        Read current pressure from PGVA device in mbar.
        
        Returns:
            Current pressure value in mbar
        """
        try:
            result = self.client.read_input_registers(
                address=PGVA_PRESSURE_ACTUAL_MBAR, count=1)
            if result.isError():
                raise ModbusException(f"Error reading pressure: {result}")
            return float(result.registers[0])
        except Exception as e:
            logger.error(f"Error reading pressure: {e}")
            raise
    
    def read_vacuum_mbar(self) -> float:
        """
        Read current vacuum from PGVA device in mbar.
        Vacuum values are negative, so we need to convert from unsigned to signed.
        
        Returns:
            Current vacuum value in mbar (negative value)
        """
        try:
            result = self.client.read_input_registers(
                address=PGVA_VACUUM_ACTUAL_MBAR, count=1)
            if result.isError():
                raise ModbusException(f"Error reading vacuum: {result}")
            
            # Convert from unsigned 16-bit to signed 16-bit
            raw_value = result.registers[0]
            if raw_value > 32767:
                signed_value = raw_value - 65536
            else:
                signed_value = raw_value
            
            return float(signed_value)
        except Exception as e:
            logger.error(f"Error reading vacuum: {e}")
            raise
    
    def read_output_pressure_mbar(self) -> float:
        """
        Read current output pressure from PGVA device in mbar.
        Output pressure can be negative (vacuum) or positive (pressure),
        so we need to convert from unsigned to signed.
        
        Returns:
            Current output pressure value in mbar (can be negative or positive)
        """
        try:
            result = self.client.read_input_registers(
                address=PGVA_OUTPUT_PRESSURE_ACTUAL_MBAR, count=1)
            if result.isError():
                raise ModbusException(f"Error reading output pressure: "
                                      f"{result}")
            
            # Convert from unsigned 16-bit to signed 16-bit
            raw_value = result.registers[0]
            if raw_value > 32767:
                signed_value = raw_value - 65536
            else:
                signed_value = raw_value
            
            return float(signed_value)
        except Exception as e:
            logger.error(f"Error reading output pressure: {e}")
            raise
    
    def set_pressure_threshold_mbar(self, pressure: float) -> bool:
        """
        Set pressure threshold on PGVA device in mbar.
        
        Args:
            pressure: Pressure threshold value in mbar (200-1000 mbar)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.client.write_register(
                address=PGVA_PRESSURE_THRESHOLD_MBAR, value=int(pressure))
            if result.isError():
                raise ModbusException(f"Error setting pressure threshold: "
                                      f"{result}")
            return True
        except Exception as e:
            logger.error(f"Error setting pressure threshold: {e}")
            return False
    
    def set_vacuum_threshold_mbar(self, vacuum: float) -> bool:
        """
        Set vacuum threshold on PGVA device in mbar.
        
        Args:
            vacuum: Vacuum threshold value in mbar (-200 to -900 mbar)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.client.write_register(
                address=PGVA_VACUUM_THRESHOLD_MBAR, value=int(vacuum))
            if result.isError():
                raise ModbusException(f"Error setting vacuum threshold: "
                                      f"{result}")
            return True
        except Exception as e:
            logger.error(f"Error setting vacuum threshold: {e}")
            return False
    
    def set_output_pressure_mbar(self, pressure: float) -> bool:
        """
        Set output pressure on PGVA device in mbar.
        
        Args:
            pressure: Output pressure value in mbar (-450 to 450 mbar)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert signed pressure to unsigned 16-bit value for Modbus
            # The PGVA expects pressure values in the range -450 to +450 mbar
            # We need to convert this to a 16-bit unsigned value
            if pressure < 0:
                # For negative values, convert to unsigned representation
                # -450 mbar becomes 65086 (65536 - 450)
                modbus_value = int(65536 + pressure)
            else:
                # For positive values, use as-is
                modbus_value = int(pressure)
            
            result = self.client.write_register(
                address=PGVA_OUTPUT_PRESSURE_MBAR, value=modbus_value)
            if result.isError():
                raise ModbusException(f"Error setting output pressure: "
                                      f"{result}")
            
            logger.info(f"Set output pressure to {pressure} mbar (Modbus value: {modbus_value})")
            return True
        except Exception as e:
            logger.error(f"Error setting output pressure: {e}")
            return False
    
    def get_status(self) -> int:
        """
        Read device status from PGVA.
        
        Returns:
            Device status value (16-bit status word)
        """
        try:
            result = self.client.read_input_registers(
                address=PGVA_STATUS, count=1)
            if result.isError():
                raise ModbusException(f"Error reading status: {result}")
            return int(result.registers[0])
        except Exception as e:
            logger.error(f"Error reading status: {e}")
            raise
    
    def get_warnings(self) -> int:
        """
        Read device warnings from PGVA.
        
        Returns:
            Warning word (16 bits)
        """
        try:
            result = self.client.read_input_registers(
                address=PGVA_WARNING, count=1)
            if result.isError():
                raise ModbusException(f"Error reading warnings: {result}")
            return int(result.registers[0])
        except Exception as e:
            logger.error(f"Error reading warnings: {e}")
            raise
    
    def get_errors(self) -> int:
        """
        Read device errors from PGVA.
        
        Returns:
            Error word (16 bits)
        """
        try:
            result = self.client.read_input_registers(
                address=PGVA_ERROR, count=1)
            if result.isError():
                raise ModbusException(f"Error reading errors: {result}")
            return int(result.registers[0])
        except Exception as e:
            logger.error(f"Error reading errors: {e}")
            raise
    
    def trigger_manual(self) -> bool:
        """
        Trigger manual operation of the PGVA device.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.client.write_register(
                address=PGVA_MANUAL_TRIGGER, value=PGVA_CMD_TRIGGER)
            if result.isError():
                raise ModbusException(f"Error triggering manual: "
                                      f"{result}")
            return True
        except Exception as e:
            logger.error(f"Error triggering manual: {e}")
            return False
    
    def enable_pump(self) -> bool:
        """
        Enable the pump on PGVA device.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.client.write_register(
                address=PGVA_DISABLE_PUMP, value=PGVA_CMD_DISABLE)
            if result.isError():
                raise ModbusException(f"Error enabling pump: {result}")
            return True
        except Exception as e:
            logger.error(f"Error enabling pump: {e}")
            return False
    
    def disable_pump(self) -> bool:
        """
        Disable the pump on PGVA device.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.client.write_register(
                address=PGVA_DISABLE_PUMP, value=PGVA_CMD_ENABLE)
            if result.isError():
                raise ModbusException(f"Error disabling pump: {result}")
            return True
        except Exception as e:
            logger.error(f"Error disabling pump: {e}")
            return False
    
    def store_to_eeprom(self) -> bool:
        """
        Store current parameters to EEPROM.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.client.write_register(
                address=PGVA_STORE_TO_EEPROM, value=PGVA_CMD_ENABLE)
            if result.isError():
                raise ModbusException(f"Error storing to EEPROM: "
                                      f"{result}")
            return True
        except Exception as e:
            logger.error(f"Error storing to EEPROM: {e}")
            return False
    
    def get_comprehensive_status(self) -> Dict:
        """
        Get comprehensive device status including status, warnings, and errors.
        
        Returns:
            Dictionary containing parsed status, warnings, and errors
        """
        try:
            status_value = self.get_status()
            warning_value = self.get_warnings()
            error_value = self.get_errors()
            
            # Parse the status information
            parsed_status = PGVAStatusParser.parse_status_word(status_value)
            parsed_warnings = PGVAStatusParser.parse_warning_word(
                warning_value)
            parsed_errors = PGVAStatusParser.parse_error_word(error_value)
            
            # Create comprehensive status report
            comprehensive_status = {
                "status": parsed_status,
                "warnings": parsed_warnings,
                "errors": parsed_errors,
                "summary": PGVAStatusParser.get_status_summary(
                    status_value, warning_value, error_value),
                "is_healthy": (parsed_errors["count"] == 0 and
                               parsed_errors["modbus_count"] == 0),
                "has_warnings": parsed_warnings["count"] > 0,
                "has_errors": (parsed_errors["count"] > 0 or
                               parsed_errors["modbus_count"] > 0)
            }
            
            return comprehensive_status
            
        except Exception as e:
            logger.error(f"Error getting comprehensive status: {e}")
            return {
                "status": {"raw_value": 0, "bits": {}, "pump_state": "Unknown",
                           "summary": ["Error reading status"]},
                "warnings": {"raw_value": 0, "warnings": [], "count": 0},
                "errors": {"raw_value": 0, "errors": [], "modbus_errors": [],
                           "count": 0, "modbus_count": 0},
                "summary": "Error reading device status",
                "is_healthy": False,
                "has_warnings": False,
                "has_errors": True
            }
    
    def get_device_info(self) -> Dict:
        """
        Get device information including firmware version and counters.
        
        Returns:
            Dictionary containing device information
        """
        try:
            device_info = {}
            
            # Read firmware information
            fw_version = self.client.read_input_registers(
                address=PGVA_FIRMWARE_VERSION, count=1)
            fw_sub_version = self.client.read_input_registers(
                address=PGVA_FIRMWARE_SUB_VERSION, count=1)
            fw_build = self.client.read_input_registers(
                address=PGVA_FIRMWARE_BUILD, count=1)
            
            if not fw_version.isError():
                device_info["firmware_version"] = fw_version.registers[0]
            if not fw_sub_version.isError():
                device_info["firmware_sub_version"] = fw_sub_version.registers[0]
            if not fw_build.isError():
                device_info["firmware_build"] = fw_build.registers[0]
                
            # Read counters
            trigger_counter = self.client.read_input_registers(
                address=PGVA_TRIGGER_COUNTER, count=1)
            pump_counter = self.client.read_input_registers(
                address=PGVA_PUMP_COUNTER, count=1)
            life_counter = self.client.read_input_registers(
                address=PGVA_LIFE_COUNTER, count=1)
            
            if not trigger_counter.isError():
                device_info["trigger_count"] = trigger_counter.registers[0]
            if not pump_counter.isError():
                device_info["pump_runtime_seconds"] = pump_counter.registers[0]
            if not life_counter.isError():
                device_info["life_runtime_minutes"] = life_counter.registers[0]
            
            return device_info
            
        except Exception as e:
            logger.error(f"Error getting device info: {e}")
            return {}
    
    def check_device_health(self) -> Dict:
        """
        Perform a comprehensive health check of the device.
        
        Returns:
            Dictionary containing health check results
        """
        try:
            # Get comprehensive status
            status = self.get_comprehensive_status()
            
            # Get device info
            device_info = self.get_device_info()
            
            # Perform health assessment
            health_check = {
                "timestamp": __import__('datetime').datetime.now().isoformat(),
                "overall_health": ("Healthy" if status["is_healthy"]
                                   else "Unhealthy"),
                "status_summary": status["summary"],
                "has_warnings": status["has_warnings"],
                "has_errors": status["has_errors"],
                "error_count": status["errors"]["count"],
                "modbus_error_count": status["errors"]["modbus_count"],
                "warning_count": status["warnings"]["count"],
                "pump_state": status["status"]["pump_state"],
                "device_info": device_info,
                "recommendations": []
            }
            
            # Add recommendations based on status
            if status["has_errors"]:
                health_check["recommendations"].append(
                    "Device has errors - check error details")
                
            if status["has_warnings"]:
                health_check["recommendations"].append(
                    "Device has warnings - review warning details")
                
            if status["status"]["bits"].get(3, {}).get("value") == 1:
                health_check["recommendations"].append(
                    "Pressure below threshold - check system")
                
            if status["status"]["bits"].get(4, {}).get("value") == 1:
                health_check["recommendations"].append(
                    "Vacuum below threshold - check system")
                
            if status["status"]["bits"].get(5, {}).get("value") == 1:
                health_check["recommendations"].append(
                    "EEPROM write pending - wait for completion")
            
            return health_check
            
        except Exception as e:
            logger.error(f"Error performing health check: {e}")
            return {
                "timestamp": __import__('datetime').datetime.now().isoformat(),
                "overall_health": "Unknown",
                "status_summary": "Error performing health check",
                "has_warnings": False,
                "has_errors": True,
                "error_count": 1,
                "modbus_error_count": 0,
                "warning_count": 0,
                "pump_state": "Unknown",
                "device_info": {},
                "recommendations": ["Check device connection and "
                                    "communication"]
            }
    
    def actuate_trigger(self, time_ms: int) -> bool:
        """
        Set the trigger actuation time.
        Args:
            time_ms: Time in milliseconds (5-65535)
        Returns:
            True if successful, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to PGVA device")
            return False
        
        if not (5 <= time_ms <= 65535):
            logger.error(f"Trigger actuation time {time_ms} ms is out of range (5-65535)")
            return False
        
        try:
            result = self.client.write_register(address=PGVA_TRIGGER_ACTUATION_TIME, value=time_ms)
            if result.isError():
                logger.error(f"Failed to set trigger actuation time: {result}")
                return False
            
            logger.info(f"Actuated trigger for {time_ms} ms")
            return True
        except ModbusException as e:
            logger.error(f"Modbus error setting trigger actuation time: {e}")
            return False
        except Exception as e:
            logger.error(f"Error setting trigger actuation time: {e}")
            return False
    
    def activate_manual_trigger(self) -> bool:
        """
        Activate the manual trigger.
        Returns:
            True if successful, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to PGVA device")
            return False
        
        try:
            result = self.client.write_register(address=PGVA_MANUAL_TRIGGER, value=PGVA_CMD_TRIGGER)
            if result.isError():
                logger.error(f"Failed to activate manual trigger: {result}")
                return False
            
            logger.info("Activated manual trigger")
            return True
        except ModbusException as e:
            logger.error(f"Modbus error activating manual trigger: {e}")
            return False
        except Exception as e:
            logger.error(f"Error activating manual trigger: {e}")
            return False
    
    def deactivate_manual_trigger(self) -> bool:
        """
        Deactivate the manual trigger (close the valve).
        Returns:
            True if successful, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to PGVA device")
            return False
        
        try:
            result = self.client.write_register(address=PGVA_MANUAL_TRIGGER, value=PGVA_CMD_DISABLE)
            if result.isError():
                logger.error(f"Failed to deactivate manual trigger: {result}")
                return False
            
            logger.info("Deactivated manual trigger (valve closed)")
            return True
        except ModbusException as e:
            logger.error(f"Modbus error deactivating manual trigger: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deactivating manual trigger: {e}")
            return False
    
    def close_trigger(self) -> bool:
        """
        Close the trigger valve (alias for deactivate_manual_trigger).
        Returns:
            True if successful, False otherwise
        """
        return self.deactivate_manual_trigger()
    
    def reset_device(self) -> bool:
        """
        Reset the PGVA device to a safe state.
        This performs a soft reset by:
        1. Closing the trigger valve
        2. Setting output pressure to 0
        3. Disabling the pump
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Starting PGVA device reset...")
            
            # Step 1: Close the trigger valve
            if not self.close_trigger():
                logger.warning("Failed to close trigger during reset")
            
            # Step 2: Set output pressure to 0
            if not self.set_output_pressure_mbar(0.0):
                logger.warning("Failed to set output pressure to 0 during reset")
            
            # Step 3: Disable the pump
            if not self.disable_pump():
                logger.warning("Failed to disable pump during reset")
            
            logger.info("PGVA device reset completed")
            return True
            
        except Exception as e:
            logger.error(f"Error during device reset: {e}")
            return False
    
    def perform_aspirate_operation(self, pressure_mbar: float, time_ms: int) -> bool:
        """
        Perform aspirate operation - wait for pressure to be reached, then trigger valve.
        Args:
            pressure_mbar: Aspirate pressure in mbar (-450 to -1)
            time_ms: Trigger actuation time in ms (5-65535)
        Returns:
            True if successful, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to PGVA device")
            return False
        
        # Validate parameters
        if not (-450 <= pressure_mbar <= -1):
            logger.error(f"Aspirate pressure {pressure_mbar} mbar is out of range (-450 to -1)")
            return False
        
        if not (5 <= time_ms <= 65535):
            logger.error(f"Trigger time {time_ms} ms is out of range (5-65535)")
            return False
        
        try:
            logger.info(f"Starting aspirate operation: {pressure_mbar} mbar for {time_ms} ms")
            
            # Step 1: Set the aspirate pressure
            if not self.set_output_pressure_mbar(pressure_mbar):
                logger.error("Failed to set aspirate pressure")
                return False
            
            # Step 2: Wait for pressure to be reached
            logger.info("Waiting for target pressure to be reached...")
            if not self._wait_for_target_pressure():
                logger.error("Timeout waiting for target pressure")
                return False
            
            # Step 3: Set trigger actuation time
            if not self.actuate_trigger(time_ms):
                logger.error("Failed to set trigger actuation time")
                return False
            
            logger.info(f"Aspirate operation completed: {pressure_mbar} mbar for {time_ms} ms")
            return True
        except Exception as e:
            logger.error(f"Error during aspirate operation: {e}")
            return False
    
    def perform_dispense_operation(self, pressure_mbar: float, time_ms: int) -> bool:
        """
        Perform dispense operation - wait for pressure to be reached, then trigger valve.
        Args:
            pressure_mbar: Dispense pressure in mbar (1 to 450)
            time_ms: Trigger actuation time in ms (5-65535)
        Returns:
            True if successful, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to PGVA device")
            return False
        
        # Validate parameters
        if not (1 <= pressure_mbar <= 450):
            logger.error(f"Dispense pressure {pressure_mbar} mbar is out of range (1 to 450)")
            return False
        
        if not (5 <= time_ms <= 65535):
            logger.error(f"Trigger time {time_ms} ms is out of range (5-65535)")
            return False
        
        try:
            logger.info(f"Starting dispense operation: {pressure_mbar} mbar for {time_ms} ms")
            
            # Step 1: Set the dispense pressure
            if not self.set_output_pressure_mbar(pressure_mbar):
                logger.error("Failed to set dispense pressure")
                return False
            
            # Step 2: Wait for pressure to be reached
            logger.info("Waiting for target pressure to be reached...")
            if not self._wait_for_target_pressure():
                logger.error("Timeout waiting for target pressure")
                return False
            
            # Step 3: Set trigger actuation time
            if not self.actuate_trigger(time_ms):
                logger.error("Failed to set trigger actuation time")
                return False
            
            logger.info(f"Dispense operation completed: {pressure_mbar} mbar for {time_ms} ms")
            return True
        except Exception as e:
            logger.error(f"Error during dispense operation: {e}")
            return False
    
    def _wait_for_target_pressure(self, timeout_seconds: int = 30) -> bool:
        """
        Wait for the output pressure to reach the target value.
        """
        
        start_time = time.time()
        elapsed = 0
        while ((elapsed < timeout_seconds) and 
                self.is_building_pressure()):
            time.sleep(0.1)  # Check every 200ms
            elapsed = time.time() - start_time
        
        if elapsed >= timeout_seconds:
            return False
        else:
            logger.info(f"Target pressure reached after {elapsed:.2f} ms")
            return True
    
    def is_building_pressure(self) -> bool:
        """
        Check if the device is currently building pressure (not idle).
        
        Returns:
            True if building pressure, False if idle
        """
        try:
            status = (self.get_status() >> 6) & 1
            # Check bit 6: 0 = In progress, 1 = Achieved
            return not bool(status)
        except Exception as e:
            logger.error(f"Error checking pressure building status: {e}")
            return False
