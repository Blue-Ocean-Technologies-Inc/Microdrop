import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal

from microdrop_utils._logger import get_logger
from protocol_grid.services.force_calculation_service import ForceCalculationService
from pint import UnitRegistry

logger = get_logger(__name__)

ureg = UnitRegistry()

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
        
        # timing for elapsed time calculation
        self._protocol_start_timestamp = None
        self._protocol_start_time = None
        
        self._columns = [
            "elapsed_time", 
            "capacitance_pF",
            "voltage",
            "force_per_unit_area",
            "step_id",
            "actuated_channels",
            "actuated_area_mm2"
        ]
        
    def start_logging(self, experiment_directory: Path, preview_mode: bool = False):
        if preview_mode:
            logger.info("Skipping data logging in preview mode")
            self._is_logging_active = False
            return
            
        self._data_entries = []
        self._is_logging_active = True
        self._experiment_directory = experiment_directory
        self._preview_mode = preview_mode
        
        # reset timing for new protocol run
        self._protocol_start_timestamp = None
        self._protocol_start_time = None
        
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
            
            # handle timing
            current_time = time.time()
            if self._protocol_start_timestamp is None:
                self._protocol_start_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                self._protocol_start_time = current_time
                elapsed_time = 0.0
            else:
                elapsed_time = current_time - self._protocol_start_time
            
            # Round to millisecond precision (3 decimal places)
            elapsed_time = round(elapsed_time, 3)
            
            data_entry = {
                "elapsed_time": elapsed_time,
                "capacitance_pf": capacitance_value,
                "voltage": voltage_value,
                "force_per_unit_area": force,
                "step_id": step_id,
                "actuated_channels": actuated_channels,
                "actuated_area_mm2": actuated_area                
            }
            
            self._data_entries.append(data_entry)
            logger.debug(f"Logged data entry: step={step_id}, channels={len(actuated_channels)}, force={force}, elapsed={elapsed_time}s")
            
        except Exception as e:
            logger.error(f"Error logging capacitance data: {e}. message: {capacitance_message}")
    
    def _calculate_force(self, voltage: float) -> Optional[float]:
        if self._latest_capacitance_per_unit_area is None or voltage <= 0:
            return None
            
        try:
            # create pint quantities with proper units
            cap_quantity = ureg.Quantity(self._latest_capacitance_per_unit_area, 'pF/mm**2')
            voltage_quantity = ureg.Quantity(voltage, 'V')
            
            # calculate force: F = (C/A × V²) / 2
            force_quantity = cap_quantity * (voltage_quantity ** 2) / 2
            
            # convert to desired unit (mN/m)
            force_in_target_units = force_quantity.to('mN/m')
            
            # return magnitude (numerical value) in mN/m
            return round(force_in_target_units.magnitude, 2)
            
        except Exception as e:
            logger.error(f"Error calculating force: {e}")
            return None
    
    def _convert_to_columnar_format(self) -> Dict:
        """Convert list of entry dictionaries to columnar format with single start timestamp."""
        if not self._data_entries:
            return {
                "start_timestamp": None,
                "columns": self._columns, 
                "data": [[] for _ in self._columns]
            }
        
        columnar_data = {col: [] for col in self._columns}
        
        for entry in self._data_entries:
            for col in self._columns:
                value = entry.get(col)
                if value is None:
                    if col in ["force_per_unit_area", "actuated_area_mm2", "capacitance_pf", "voltage", "elapsed_time"]:
                        value = 0.0
                    elif col == "actuated_channels":
                        value = []
                    else:
                        value = ""
                columnar_data[col].append(value)
        
        result = {
            "start_timestamp": self._protocol_start_timestamp,
            "columns": self._columns,
            "data": [columnar_data[col] for col in self._columns]
        }
        
        return result
    
    def save_data_file(self, save_directory: Path = None):
        """save accumulated data to JSON and CSV files."""
        if not self._data_entries:
            logger.info("No data to save")
            return None, None
            
        # use provided directory or fall back to experiment directory
        target_directory = save_directory or self._experiment_directory
        if not target_directory:
            logger.error("No target directory specified for saving data files")
            return None, None
            
        try:
            # Ensure target directory exists
            target_directory = Path(target_directory)
            target_directory.mkdir(parents=True, exist_ok=True)
            
            # save JSON file
            json_file_path = target_directory / "data.json"
            columnar_data = self._convert_to_columnar_format()
            
            with open(json_file_path, "w") as f:
                json.dump(columnar_data, f, separators=(',', ':'))
            
            logger.info(f"Saved {len(self._data_entries)} data entries to JSON: {json_file_path}")
            
            # save CSV file
            csv_file_path = self._save_as_csv(target_directory, columnar_data)
            
            return str(json_file_path), str(csv_file_path)
            
        except Exception as e:
            logger.error(f"Error saving data files: {e}")
            return None, None
    
    def _save_as_csv(self, target_directory: Path, columnar_data: Dict) -> str:
        try:
            csv_file_path = target_directory / "data.csv"
            
            start_timestamp = columnar_data.get('start_timestamp')
            columns = columnar_data.get('columns', [])
            data_values = columnar_data.get('data', [])
            
            if not columns or not data_values:
                logger.warning("Empty or invalid data format for CSV")
                return None
            
            # ddd start_timestamp column
            csv_columns = ['start_timestamp'] + columns
            
            # prepare data
            num_rows = len(data_values[0]) if data_values else 0
            
            with open(csv_file_path, 'w', newline='') as csvfile:
                import csv
                writer = csv.writer(csvfile)
                
                writer.writerow(csv_columns)
                
                for row_idx in range(num_rows):
                    row_data = []
                    
                    # add start_timestamp only to first row, empty for others
                    if row_idx == 0:
                        row_data.append(start_timestamp or '')
                    else:
                        row_data.append('')
                    
                    for col_idx in range(len(columns)):
                        if col_idx < len(data_values):
                            value = data_values[col_idx][row_idx] if row_idx < len(data_values[col_idx]) else ''
                            row_data.append(value)
                        else:
                            row_data.append('')
                    
                    writer.writerow(row_data)
            
            logger.info(f"Saved CSV file: {csv_file_path}")
            return str(csv_file_path)
            
        except Exception as e:
            logger.error(f"Error saving CSV file: {e}")
            return None
    
    def get_data_entry_count(self) -> int:
        """get number of logged data entries."""
        return len(self._data_entries)
    
    @staticmethod
    def load_data_as_dataframe(file_path: str):
        """
        Load the optimized JSON format and convert to pandas DataFrame.
        
        Args:
            file_path: Path to the JSON data file
            
        Returns:
            pandas.DataFrame: Data with proper column headers
        """
        try:
            import pandas as pd
            
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # extract values
            start_timestamp = data.get('start_timestamp')
            columns = data.get('columns', [])
            data_values = data.get('data', [])
            
            if not columns or not data_values:
                logger.warning("Empty or invalid data format")
                return pd.DataFrame()
            
            # create dataframe
            df_data = {}
            for i, col in enumerate(columns):
                if i < len(data_values):
                    df_data[col] = data_values[i]
                else:
                    df_data[col] = []
            
            df = pd.DataFrame(df_data)
            
            if start_timestamp:
                df['start_timestamp'] = start_timestamp
            
            logger.info(f"Loaded DataFrame with {len(df)} rows and {len(df.columns)} columns")
            logger.info(f"Protocol started at: {start_timestamp}")
            return df
            
        except ImportError:
            logger.error("pandas is required for loading data as DataFrame")
            return None
        except Exception as e:
            logger.error(f"Error loading data as DataFrame: {e}")
            return None