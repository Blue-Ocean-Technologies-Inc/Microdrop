"""
PGVA Status, Warning, and Error Parser
Parses the status, warning, and error words from the Festo PGVA device
according to the official documentation.
"""

from typing import Dict
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


class PGVAStatusParser:
    """
    Parser for PGVA status, warning, and error words.
    Based on the official Festo PGVA documentation.
    """
    
    # Status word bit definitions (Table 32)
    STATUS_BITS = {
        0: {"name": "idle_or_busy", "description": "Idle or busy", "values": {0: "Idle", 1: "Busy"}},
        1: {"name": "pump_state_bit1", "description": "Pump state bit 1", "values": {0: "0", 1: "1"}},
        2: {"name": "pump_state_bit2", "description": "Pump state bit 2", "values": {0: "0", 1: "1"}},
        3: {"name": "pressure", "description": "Pressure", "values": {0: "Nominal", 1: "Below threshold"}},
        4: {"name": "vacuum", "description": "Vacuum", "values": {0: "Nominal", 1: "Below threshold"}},
        5: {"name": "eeprom_write", "description": "EEPROM write", "values": {0: "No write pending", 1: "Write pending"}},
        6: {"name": "target_pressure", "description": "Target pressure", "values": {0: "In progress", 1: "Achieved"}},
        7: {"name": "trigger", "description": "Trigger", "values": {0: "Closed", 1: "Opened"}},
        8: {"name": "reserved_8", "description": "Reserved", "values": {0: "0", 1: "1"}},
        9: {"name": "reserved_9", "description": "Reserved", "values": {0: "0", 1: "1"}},
        10: {"name": "outlet_valve_control", "description": "Outlet valve control", "values": {0: "Disabled", 1: "Enabled"}},
        11: {"name": "outlet_valve", "description": "Outlet valve", "values": {0: "Closed", 1: "Open"}},
        12: {"name": "reserved_12", "description": "Reserved", "values": {0: "0", 1: "1"}},
        13: {"name": "reserved_13", "description": "Reserved", "values": {0: "0", 1: "1"}},
        14: {"name": "reserved_14", "description": "Reserved", "values": {0: "0", 1: "1"}},
        15: {"name": "reserved_15", "description": "Reserved", "values": {0: "0", 1: "1"}},
    }
    
    # Warning word bit definitions (Table 33)
    WARNING_BITS = {
        0: {"name": "abnormal_supply_voltage", "description": "Abnormal supply voltage", 
            "cause": "Power supply outside permissible threshold", "remedy": "Check power supply"},
        1: {"name": "auto_correction_vacuum", "description": "Auto correction of vacuum threshold",
            "cause": "Cannot reach preset threshold, autocorrection performed", 
            "remedy": "Threshold can be adjusted manually, preset value active after restart"},
        2: {"name": "auto_correction_pressure", "description": "Auto correction of pressure threshold",
            "cause": "Cannot reach preset threshold, autocorrection performed",
            "remedy": "Threshold can be adjusted manually, preset value active after restart"},
        3: {"name": "pump_on_during_dispense", "description": "Pump ON during dispense/aspirate",
            "cause": "Pump recharges during aspiration process", 
            "remedy": "Check aspiration result, may vary from previous results"},
        4: {"name": "target_pressure_not_reached", "description": "Target pressure not reached",
            "cause": "Preset output pressure cannot be reached",
            "remedy": "Check system for leakage, check output volume, check sensor config"},
        5: {"name": "vacuum_threshold_high", "description": "Vacuum threshold set above -500 mbar",
            "cause": "Threshold value set to >= -500 mbar", 
            "remedy": "Increase threshold value for full function"},
        6: {"name": "pressure_threshold_low", "description": "Pressure threshold set below 500 mbar",
            "cause": "Threshold value set to <= 500 mbar",
            "remedy": "Increase threshold value for full function"},
        7: {"name": "pump_9_minutes", "description": "Pump ran for 9 minutes",
            "cause": "Pump active for 9 minutes, switched off to avoid overheating",
            "remedy": "Check system for leakage, check output volume"},
        8: {"name": "reserved_8", "description": "Reserved", "cause": "", "remedy": ""},
        9: {"name": "external_sensor_verification", "description": "External sensor verification warning",
            "cause": "Failed to check external sensor",
            "remedy": "Verify sensor configuration of connected sensor"},
        10: {"name": "reserved_10", "description": "Reserved", "cause": "", "remedy": ""},
        11: {"name": "reserved_11", "description": "Reserved", "cause": "", "remedy": ""},
        12: {"name": "reserved_12", "description": "Reserved", "cause": "", "remedy": ""},
        13: {"name": "reserved_13", "description": "Reserved", "cause": "", "remedy": ""},
        14: {"name": "reserved_14", "description": "Reserved", "cause": "", "remedy": ""},
        15: {"name": "reserved_15", "description": "Reserved", "cause": "", "remedy": ""},
    }
    
    # Error word bit definitions (Table 34 & 35)
    ERROR_BITS = {
        0: {"name": "pump_timeout", "description": "Pump timeout error",
            "cause": "Pump active for >= 10 minutes",
            "remedy": "Check system for leakage, check output volume, restart device"},
        1: {"name": "timeout_target_pressure", "description": "Timeout achieving target output pressure",
            "cause": "Output pressure cannot be reached within 8 minutes",
            "remedy": "Check system for leakage, output volume too high"},
        2: {"name": "modbus_error", "description": "Modbus error occurred",
            "cause": "Modbus error occurred",
            "remedy": "Check Modbus command error"},
        3: {"name": "supply_voltage_low", "description": "Supply voltage low",
            "cause": "Power supply too low",
            "remedy": "Check power supply"},
        4: {"name": "supply_voltage_high", "description": "Supply voltage high",
            "cause": "Power supply too high",
            "remedy": "Check power supply"},
        5: {"name": "timeout_external_sensor", "description": "Timeout external sensor verification",
            "cause": "External sensor check timed out",
            "remedy": "Check sensor connection"},
        6: {"name": "reserved_6", "description": "Reserved", "cause": "", "remedy": ""},
        7: {"name": "reserved_7", "description": "Reserved", "cause": "", "remedy": ""},
        8: {"name": "reserved_8", "description": "Reserved", "cause": "", "remedy": ""},
        9: {"name": "reserved_9", "description": "Reserved", "cause": "", "remedy": ""},
        10: {"name": "reserved_10", "description": "Reserved", "cause": "", "remedy": ""},
        11: {"name": "reserved_11", "description": "Reserved", "cause": "", "remedy": ""},
        12: {"name": "reserved_12", "description": "Reserved", "cause": "", "remedy": ""},
        13: {"name": "reserved_13", "description": "Reserved", "cause": "", "remedy": ""},
        14: {"name": "reserved_14", "description": "Reserved", "cause": "", "remedy": ""},
        15: {"name": "reserved_15", "description": "Reserved", "cause": "", "remedy": ""},
    }
    
    # Modbus command error bits (Table 35)
    MODBUS_ERROR_BITS = {
        0: {"name": "output_actuation_time_range", "description": "Output actuation time out of range",
            "cause": "Trigger open time outside input range", "remedy": "Check entered value"},
        1: {"name": "pressure_threshold_range", "description": "Pressure threshold out of range",
            "cause": "Pressure threshold outside input range", "remedy": "Check entered value"},
        2: {"name": "vacuum_threshold_range", "description": "Vacuum threshold out of range",
            "cause": "Vacuum threshold outside input range", "remedy": "Check entered value"},
        3: {"name": "output_pressure_range", "description": "Output pressure out of range",
            "cause": "Output pressure outside input range", "remedy": "Check entered value"},
        4: {"name": "modbus_unit_id_range", "description": "Modbus Unit ID out of range",
            "cause": "Modbus unit ID outside permissible range", "remedy": "Check entered value"},
        5: {"name": "ip_address_restrictions", "description": "IP address does not comply with restrictions",
            "cause": "IP address not within permissible range", "remedy": "Check entered value"},
        6: {"name": "manual_trigger_invalid", "description": "Manual trigger invalid",
            "cause": "Manual trigger input invalid", "remedy": "Check entered value"},
        7: {"name": "incorrect_register_count", "description": "Incorrect number of registers",
            "cause": "Invalid number of registers written", "remedy": "Check entered value"},
        8: {"name": "register_write_protected", "description": "Register cannot be written",
            "cause": "Register is write-protected", "remedy": "Cannot be written to"},
        9: {"name": "dhcp_selection_invalid", "description": "DHCP selection invalid",
            "cause": "Input values outside permissible range", "remedy": "Check entered value"},
        10: {"name": "external_sensor_range_invalid", "description": "External sensor range selection invalid",
            "cause": "Input values outside permissible range", "remedy": "Check entered value"},
        11: {"name": "exhaust_valve_volume_invalid", "description": "Exhaust valve volume invalid",
            "cause": "Input values outside permissible range", "remedy": "Check entered value"},
        12: {"name": "exhaust_enable_invalid", "description": "Exhaust enable invalid",
            "cause": "Input values outside permissible range", "remedy": "Check entered value"},
        13: {"name": "pump_on_off_invalid", "description": "Pump On/Off invalid",
            "cause": "Input values outside permissible range", "remedy": "Check entered value"},
        14: {"name": "reserved_14", "description": "Reserved", "cause": "", "remedy": ""},
        15: {"name": "reserved_15", "description": "Reserved", "cause": "", "remedy": ""},
    }
    
    @staticmethod
    def parse_status_word(status_value: int) -> Dict:
        """
        Parse the PGVA status word (16 bits).
        
        Args:
            status_value: 16-bit status word value
            
        Returns:
            Dictionary containing parsed status information
        """
        result = {
            "raw_value": status_value,
            "bits": {},
            "pump_state": "Unknown",
            "summary": []
        }
        
        # Parse individual bits
        for bit, info in PGVAStatusParser.STATUS_BITS.items():
            bit_value = (status_value >> bit) & 1
            result["bits"][bit] = {
                "name": info["name"],
                "description": info["description"],
                "value": bit_value,
                "text": info["values"].get(bit_value, "Unknown")
            }
        
        # Special handling for pump state (bits 1-2)
        pump_bits = ((status_value >> 1) & 0x03)
        pump_states = {
            0: "Pump is off",
            1: "Pump is building up pressure", 
            2: "Pump is building up vacuum",
            3: "Invalid pump state"
        }
        result["pump_state"] = pump_states.get(pump_bits, "Unknown")
        result["summary"].append(f"Pump: {result['pump_state']}")
        
        # Add other important status information
        if result["bits"][0]["value"] == 1:
            result["summary"].append("Device is busy")
        else:
            result["summary"].append("Device is idle")
            
        if result["bits"][6]["value"] == 1:
            result["summary"].append("Target pressure achieved")
        else:
            result["summary"].append("Target pressure in progress")
            
        if result["bits"][3]["value"] == 1:
            result["summary"].append("Pressure below threshold")
            
        if result["bits"][4]["value"] == 1:
            result["summary"].append("Vacuum below threshold")
            
        if result["bits"][7]["value"] == 1:
            result["summary"].append("Trigger opened")
            
        if result["bits"][10]["value"] == 1:
            result["summary"].append("Outlet valve control enabled")
            
        if result["bits"][11]["value"] == 1:
            result["summary"].append("Exhaust valve open")
            
        if result["bits"][5]["value"] == 1:
            result["summary"].append("EEPROM write pending")
        
        # Add a human-readable overall status
        if len(result["summary"]) == 2:  # Only pump and idle/busy
            if result["bits"][0]["value"] == 0:
                result["summary"] = ["Device is idle and ready"]
            else:
                result["summary"] = ["Device is busy"]
        elif len(result["summary"]) > 2:
            # Keep the detailed status
            pass
        else:
            result["summary"] = ["Device status unknown"]
            
        return result
    
    @staticmethod
    def parse_warning_word(warning_value: int) -> Dict:
        """
        Parse the PGVA warning word (16 bits).
        
        Args:
            warning_value: 16-bit warning word value
            
        Returns:
            Dictionary containing parsed warning information
        """
        result = {
            "raw_value": warning_value,
            "warnings": [],
            "count": 0
        }
        
        # Parse individual bits
        for bit, info in PGVAStatusParser.WARNING_BITS.items():
            if (warning_value >> bit) & 1:
                warning_info = {
                    "bit": bit,
                    "name": info["name"],
                    "description": info["description"],
                    "cause": info["cause"],
                    "remedy": info["remedy"]
                }
                result["warnings"].append(warning_info)
                result["count"] += 1
        
        return result
    
    @staticmethod
    def parse_error_word(error_value: int) -> Dict:
        """
        Parse the PGVA error word (16 bits).
        
        Args:
            error_value: 16-bit error word value
            
        Returns:
            Dictionary containing parsed error information
        """
        result = {
            "raw_value": error_value,
            "errors": [],
            "modbus_errors": [],
            "count": 0,
            "modbus_count": 0
        }
        
        # Parse regular error bits (0-5)
        for bit, info in PGVAStatusParser.ERROR_BITS.items():
            if (error_value >> bit) & 1:
                error_info = {
                    "bit": bit,
                    "name": info["name"],
                    "description": info["description"],
                    "cause": info["cause"],
                    "remedy": info["remedy"]
                }
                result["errors"].append(error_info)
                result["count"] += 1
        
        # Parse Modbus command errors (bits 6-15)
        for bit, info in PGVAStatusParser.MODBUS_ERROR_BITS.items():
            if (error_value >> (bit + 6)) & 1:
                modbus_error_info = {
                    "bit": bit + 6,
                    "name": info["name"],
                    "description": info["description"],
                    "cause": info["cause"],
                    "remedy": info["remedy"]
                }
                result["modbus_errors"].append(modbus_error_info)
                result["modbus_count"] += 1
        
        return result
    
    @staticmethod
    def get_status_summary(status_value: int, warning_value: int = 0, error_value: int = 0) -> str:
        """
        Get a human-readable summary of the device status.
        
        Args:
            status_value: Status word value
            warning_value: Warning word value (optional)
            error_value: Error word value (optional)
            
        Returns:
            Human-readable status summary
        """
        # Ensure all values are integers
        status_value = int(status_value)
        warning_value = int(warning_value)
        error_value = int(error_value)
        
        status = PGVAStatusParser.parse_status_word(status_value)
        summary_parts = status["summary"]
        
        if warning_value > 0:
            warnings = PGVAStatusParser.parse_warning_word(warning_value)
            if warnings["count"] > 0:
                summary_parts.append(f"{warnings['count']} warning(s)")
        
        if error_value > 0:
            errors = PGVAStatusParser.parse_error_word(error_value)
            if errors["count"] > 0:
                summary_parts.append(f"{errors['count']} error(s)")
            if errors["modbus_count"] > 0:
                summary_parts.append(f"{errors['modbus_count']} Modbus error(s)")
        
        return " | ".join(summary_parts)
