import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from microdrop_utils._logger import get_logger
from protocol_grid.services.force_calculation_service import ForceCalculationService

logger = get_logger(__name__)

class ProtocolDataLogger(QObject):
    """Service for logging capacitance data during protocol execution."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data_entries = []
        self._is_logging_active = False
        self._latest_capacitance_per_unit_area = None
        self._current_protocol_context = None
        self._experiment_directory = None
        self._preview_mode = False
        
    def start_logging(self, experiment_directory: Path, preview_mode: bool = False):
        if preview_mode:
            logger.info("Skipping data logging in preview mode")
            self._is_logging_active = False
            return
            
        self._data_entries = []
        self._is_logging_active = True
        self._experiment_directory = experiment_directory
        self._preview_mode = preview_mode
        
        logger.info(f"Started protocol data logging to: {experiment_directory}")
    
    def stop_logging(self):
        self._is_logging_active = False
        logger.info("Stopped protocol data logging")
    
    def set_protocol_context(self, context: Dict):
        self._current_protocol_context = context
    
    def update_capacitance_per_unit_area(self, c_unit_area: float):
        self._latest_capacitance_per_unit_area = c_unit_area
        logger.debug(f"Updated capacitance per unit area: {c_unit_area}")
    
    def log_capacitance_data(self, capacitance_message: str):
        if not self._is_logging_active or self._preview_mode:
            return
            
        try:
            # parse capacitance message
            capacitance_data = json.loads(capacitance_message)
            capacitance_str = capacitance_data.get('capacitance', '-')
            voltage_str = capacitance_data.get('voltage', '-')
            
            if capacitance_str == '-' or voltage_str == '-':
                logger.debug("Invalid capacitance/voltage data, skipping log entry")
                return
            
            # extract numeric values - handle both "pF" and " pF" formats
            try:
                if 'pF' in capacitance_str:
                    capacitance_value = float(capacitance_str.replace('pF', '').strip())
                else:
                    capacitance_value = float(capacitance_str)
            except ValueError:
                logger.debug(f"Could not parse capacitance value: {capacitance_str}")
                return
            
            try:
                if 'V' in voltage_str:
                    voltage_value = float(voltage_str.replace('V', '').strip())
                else:
                    voltage_value = float(voltage_str)
            except ValueError:
                logger.debug(f"Could not parse voltage value: {voltage_str}")
                return
            
            # get current protocol context
            if not self._current_protocol_context:
                logger.debug("No protocol context available, skipping log entry")
                return
            
            step_id = self._current_protocol_context.get('step_id', '')
            actuated_channels = self._current_protocol_context.get('actuated_channels', [])
            actuated_area = self._current_protocol_context.get('actuated_area', 0.0)
            
            # calculate force
            force = self._calculate_force(voltage_value)
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            # eg: "2025-08-26 10:52:11.8"
            
            data_entry = {
                "timestamp": timestamp,
                "capacitance": capacitance_str,
                "voltage": voltage_str,
                "force per unit area": force,
                "step_id": step_id,
                "actuated_channels": actuated_channels,
                "actuated_area in mm^2": actuated_area                
            }
            
            self._data_entries.append(data_entry)
            logger.debug(f"Logged data entry: step={step_id}, channels={len(actuated_channels)}, force={force}")
            
        except Exception as e:
            logger.error(f"Error logging capacitance data: {e}. message: {capacitance_message}")
    
    def _calculate_force(self, voltage: float) -> Optional[float]:
        if self._latest_capacitance_per_unit_area is None or voltage <= 0:
            return None
            
        try:
            # force = 0.5 x capacitance_per_unit_area x voltage^2
            force = 0.5 * self._latest_capacitance_per_unit_area * (voltage ** 2)
            return round(force, 6)
        except Exception as e:
            logger.error(f"Error calculating force: {e}")
            return None
    
    def save_data_file(self):
        """save accumulated data to JSON file."""
        if not self._data_entries or not self._experiment_directory:
            logger.info("No data to save or no experiment directory")
            return None
            
        try:
            data_file_path = self._experiment_directory / "data.json"
            
            with open(data_file_path, "w") as f:
                json.dump(self._data_entries, f, indent=2)
            
            logger.info(f"Saved {len(self._data_entries)} data entries to: {data_file_path}")
            return str(data_file_path)
            
        except Exception as e:
            logger.error(f"Error saving data file: {e}")
            return None
    
    def get_data_entry_count(self) -> int:
        """get number of logged data entries."""
        return len(self._data_entries)