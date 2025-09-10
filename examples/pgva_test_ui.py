#!/usr/bin/env python3
"""
PGVA Controller Test UI

A comprehensive test application for the Festo PGVA controller plugin.
This UI allows testing all PGVA functions including connection, pressure control,
status monitoring, error handling, and health checks.

Usage:
    python pgva_test_ui.py
"""

import sys
import time
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QGroupBox, QLineEdit, QSpinBox,
    QDoubleSpinBox, QTextEdit, QTabWidget, QGridLayout, QSplitter
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import our PGVA controller components
from pgva_controller_plugin.services.pgva_ethernet_communication import PGVAEthernetCommunication
from pgva_controller_plugin.services.pgva_status_parser import PGVAStatusParser

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PGVAStatusMonitor(QThread):
    """Thread for monitoring PGVA status updates."""
    
    status_updated = Signal(dict)
    pressure_updated = Signal(dict)
    vacuum_updated = Signal(dict)
    output_pressure_updated = Signal(dict)
    warnings_updated = Signal(dict)
    errors_updated = Signal(dict)
    health_updated = Signal(dict)
    device_info_updated = Signal(dict)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)
    
    def __init__(self, pgva_comm=None):
        super().__init__()
        self.running = False
        self.pgva_comm = pgva_comm
        self.update_interval = 2.0  # Update every 2 seconds
    
    def set_pgva_comm(self, pgva_comm):
        """Set the PGVA communication object."""
        self.pgva_comm = pgva_comm
    
    def run(self):
        """Run the monitoring thread."""
        self.running = True
        while self.running:
            if self.pgva_comm and self.pgva_comm.connected:
                try:
                    # Read current values
                    pressure = self.pgva_comm.read_pressure_mbar()
                    vacuum = self.pgva_comm.read_vacuum_mbar()
                    output_pressure = self.pgva_comm.read_output_pressure_mbar()
                    
                    # Emit signals with data
                    self.pressure_updated.emit({
                        'pressure': pressure, 
                        'unit': 'mbar',
                        'timestamp': datetime.now().isoformat()
                    })
                    self.vacuum_updated.emit({
                        'vacuum': vacuum, 
                        'unit': 'mbar',
                        'timestamp': datetime.now().isoformat()
                    })
                    self.output_pressure_updated.emit({
                        'output_pressure': output_pressure, 
                        'unit': 'mbar',
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Read status
                    status_raw = self.pgva_comm.get_status()
                    parsed_status = PGVAStatusParser.parse_status_word(status_raw)
                    self.status_updated.emit({
                        'status': parsed_status,
                        'raw_status': status_raw,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Read warnings and errors
                    warnings_raw = self.pgva_comm.get_warnings()
                    errors_raw = self.pgva_comm.get_errors()
                    
                    if warnings_raw > 0:
                        parsed_warnings = PGVAStatusParser.parse_warning_word(warnings_raw)
                        self.warnings_updated.emit({
                            'warnings': parsed_warnings,
                            'raw_warnings': warnings_raw,
                            'timestamp': datetime.now().isoformat()
                        })
                    
                    if errors_raw > 0:
                        parsed_errors = PGVAStatusParser.parse_error_word(errors_raw)
                        self.errors_updated.emit({
                            'errors': parsed_errors,
                            'raw_errors': errors_raw,
                            'timestamp': datetime.now().isoformat()
                        })
                    
                except Exception as e:
                    self.error_occurred.emit(f"Monitoring error: {str(e)}")
            
            time.sleep(self.update_interval)
    
    def stop(self):
        """Stop the monitoring thread."""
        self.running = False


class PGVAConnectionWidget(QGroupBox):
    """Widget for PGVA connection management."""
    
    connection_changed = Signal(bool)
    
    def __init__(self, parent=None):
        super().__init__("Connection", parent)
        self.pgva_comm = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the connection UI."""
        layout = QGridLayout(self)
        
        # Connection parameters
        layout.addWidget(QLabel("IP Address:"), 0, 0)
        self.ip_edit = QLineEdit("192.168.0.1")
        layout.addWidget(self.ip_edit, 0, 1)
        
        layout.addWidget(QLabel("Port:"), 0, 2)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)
        layout.addWidget(self.port_spin, 0, 3)
        
        layout.addWidget(QLabel("Unit ID:"), 1, 0)
        self.unit_id_spin = QSpinBox()
        self.unit_id_spin.setRange(0, 255)
        self.unit_id_spin.setValue(0)
        layout.addWidget(self.unit_id_spin, 1, 1)
        
        # Connection buttons
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_device)
        layout.addWidget(self.connect_btn, 1, 2)
        
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.disconnect_device)
        self.disconnect_btn.setEnabled(False)
        layout.addWidget(self.disconnect_btn, 1, 3)
        
        # Connection status
        self.status_label = QLabel("Status: Disconnected")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.status_label, 2, 0, 1, 4)
    
    def connect_device(self):
        """Connect to PGVA device."""
        ip = self.ip_edit.text()
        port = self.port_spin.value()
        unit_id = self.unit_id_spin.value()
        
        try:
            self.pgva_comm = PGVAEthernetCommunication(
                ip_address=ip,
                port=port,
                unit_id=unit_id,
            )
            
            if self.pgva_comm.connect():
                self.update_connection_status(True)
                self.connection_changed.emit(True)
                logger.info(f"Connected to PGVA at {ip}:{port}")
            else:
                self.update_connection_status(False)
                logger.error("Failed to connect to PGVA device")
                
        except Exception as e:
            self.update_connection_status(False)
            logger.error(f"Connection error: {e}")
    
    def disconnect_device(self):
        """Disconnect from PGVA device."""
        if self.pgva_comm:
            self.pgva_comm.disconnect()
            self.pgva_comm = None
            self.update_connection_status(False)
            self.connection_changed.emit(False)
            logger.info("Disconnected from PGVA device")
    
    def update_connection_status(self, connected):
        """Update connection status display."""
        if connected:
            self.status_label.setText("Status: Connected")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
        else:
            self.status_label.setText("Status: Disconnected")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
    
    def get_pgva_comm(self):
        """Get the PGVA communication object."""
        return self.pgva_comm


class PGVAPressureControlWidget(QGroupBox):
    """Widget for PGVA pressure control with aspirate and dispense functions."""
    
    def __init__(self, parent=None):
        super().__init__("Pressure Control", parent)
        self.pgva_comm = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the pressure control UI with three control sections."""
        layout = QVBoxLayout(self)
        
        # Create horizontal layout for the three control sections
        controls_layout = QHBoxLayout()
        
        # 1. Pressure Output Control
        pressure_group = QGroupBox("Pressure output")
        pressure_layout = QVBoxLayout(pressure_group)
        
        # Setpoint input
        setpoint_layout = QHBoxLayout()
        setpoint_layout.addWidget(QLabel("Setpoint:"))
        self.pressure_setpoint_spin = QDoubleSpinBox()
        self.pressure_setpoint_spin.setRange(-450, 450)
        self.pressure_setpoint_spin.setValue(0)
        self.pressure_setpoint_spin.setSuffix(" mbar")
        setpoint_layout.addWidget(self.pressure_setpoint_spin)
        setpoint_layout.addWidget(QLabel("0 mbar"))  # Current value display
        pressure_layout.addLayout(setpoint_layout)
        
        # Range info
        pressure_layout.addWidget(QLabel("Range [-450, 450]"))
        
        # Set button
        self.set_pressure_btn = QPushButton("Set")
        self.set_pressure_btn.clicked.connect(self.set_pressure_output)
        pressure_layout.addWidget(self.set_pressure_btn)
        
        controls_layout.addWidget(pressure_group)
        
        # 2. Aspirate Control
        aspirate_group = QGroupBox("Aspirate")
        aspirate_layout = QVBoxLayout(aspirate_group)
        
        # Setpoint input
        aspirate_setpoint_layout = QHBoxLayout()
        aspirate_setpoint_layout.addWidget(QLabel("Setpoint:"))
        self.aspirate_setpoint_spin = QDoubleSpinBox()
        self.aspirate_setpoint_spin.setRange(-450, -1)
        self.aspirate_setpoint_spin.setValue(-1)
        self.aspirate_setpoint_spin.setSuffix(" mbar")
        aspirate_setpoint_layout.addWidget(self.aspirate_setpoint_spin)
        aspirate_setpoint_layout.addWidget(QLabel("-1 mbar"))  # Current value display
        aspirate_layout.addLayout(aspirate_setpoint_layout)
        
        # Range info
        aspirate_layout.addWidget(QLabel("Range [-450, -1]"))
        
        # Time input
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Time:"))
        self.aspirate_time_spin = QSpinBox()
        self.aspirate_time_spin.setRange(5, 65534)
        self.aspirate_time_spin.setValue(5)
        self.aspirate_time_spin.setSuffix(" ms")
        time_layout.addWidget(self.aspirate_time_spin)
        time_layout.addWidget(QLabel("5 ms"))  # Current value display
        aspirate_layout.addLayout(time_layout)
        
        # Range info
        aspirate_layout.addWidget(QLabel("Range [5, 65534]"))
        
        # Aspirate button
        self.aspirate_btn = QPushButton("Aspirate")
        self.aspirate_btn.clicked.connect(self.aspirate)
        aspirate_layout.addWidget(self.aspirate_btn)
        
        controls_layout.addWidget(aspirate_group)
        
        # 3. Dispense Control
        dispense_group = QGroupBox("Dispense")
        dispense_layout = QVBoxLayout(dispense_group)
        
        # Setpoint input
        dispense_setpoint_layout = QHBoxLayout()
        dispense_setpoint_layout.addWidget(QLabel("Setpoint:"))
        self.dispense_setpoint_spin = QDoubleSpinBox()
        self.dispense_setpoint_spin.setRange(1, 450)
        self.dispense_setpoint_spin.setValue(1)
        self.dispense_setpoint_spin.setSuffix(" mbar")
        dispense_setpoint_layout.addWidget(self.dispense_setpoint_spin)
        dispense_setpoint_layout.addWidget(QLabel("1 mbar"))  # Current value display
        dispense_layout.addLayout(dispense_setpoint_layout)
        
        # Range info
        dispense_layout.addWidget(QLabel("Range [1, 450]"))
        
        # Time input
        dispense_time_layout = QHBoxLayout()
        dispense_time_layout.addWidget(QLabel("Time:"))
        self.dispense_time_spin = QSpinBox()
        self.dispense_time_spin.setRange(5, 65534)
        self.dispense_time_spin.setValue(5)
        self.dispense_time_spin.setSuffix(" ms")
        dispense_time_layout.addWidget(self.dispense_time_spin)
        dispense_time_layout.addWidget(QLabel("5 ms"))  # Current value display
        dispense_layout.addLayout(dispense_time_layout)
        
        # Range info
        dispense_layout.addWidget(QLabel("Range [5, 65534]"))
        
        # Dispense button
        self.dispense_btn = QPushButton("Dispense")
        self.dispense_btn.clicked.connect(self.dispense)
        dispense_layout.addWidget(self.dispense_btn)
        
        controls_layout.addWidget(dispense_group)
        
        layout.addLayout(controls_layout)
        
        # Status Details Section
        status_group = QGroupBox("Status Details")
        status_layout = QGridLayout(status_group)
        
        # Status labels
        status_layout.addWidget(QLabel("Supply Voltage:"), 0, 0)
        self.supply_voltage_label = QLabel("Nominal")
        status_layout.addWidget(self.supply_voltage_label, 0, 1)
        
        status_layout.addWidget(QLabel("Pump:"), 1, 0)
        self.pump_status_label = QLabel("Off")
        status_layout.addWidget(self.pump_status_label, 1, 1)
        
        status_layout.addWidget(QLabel("Pressure Chamber:"), 2, 0)
        self.pressure_chamber_label = QLabel("Nominal")
        status_layout.addWidget(self.pressure_chamber_label, 2, 1)
        
        status_layout.addWidget(QLabel("Dispense Valve:"), 3, 0)
        self.dispense_valve_label = QLabel("Closed")
        status_layout.addWidget(self.dispense_valve_label, 3, 1)
        
        status_layout.addWidget(QLabel("Vacuum Chamber:"), 4, 0)
        self.vacuum_chamber_label = QLabel("Nominal")
        status_layout.addWidget(self.vacuum_chamber_label, 4, 1)
        
        layout.addWidget(status_group)
    
    def set_pgva_comm(self, pgva_comm):
        """Set the PGVA communication object."""
        self.pgva_comm = pgva_comm
    
    def set_pressure_output(self):
        """Set pressure output."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        pressure = self.pressure_setpoint_spin.value()
        try:
            if self.pgva_comm.set_output_pressure_mbar(pressure):
                logger.info(f"Set pressure output to {pressure} mbar")
            else:
                logger.error("Failed to set pressure output")
        except Exception as e:
            logger.error(f"Error setting pressure output: {e}")
    
    def aspirate(self):
        """Perform aspirate operation - wait for pressure, then trigger valve."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        setpoint = self.aspirate_setpoint_spin.value()
        time_ms = self.aspirate_time_spin.value()
        
        try:
            # Disable button during operation
            self.aspirate_btn.setEnabled(False)
            self.aspirate_btn.setText("Building Pressure...")
            
            # Use the combined aspirate operation method
            if self.pgva_comm.perform_aspirate_operation(setpoint, time_ms):
                logger.info(f"Aspirate operation completed: {setpoint} mbar for {time_ms} ms")
            else:
                logger.error("Failed to perform aspirate operation")
        except Exception as e:
            logger.error(f"Error during aspirate: {e}")
        finally:
            # Re-enable button
            self.aspirate_btn.setEnabled(True)
            self.aspirate_btn.setText("Aspirate")
    
    def dispense(self):
        """Perform dispense operation - wait for pressure, then trigger valve."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        setpoint = self.dispense_setpoint_spin.value()
        time_ms = self.dispense_time_spin.value()
        
        try:
            # Disable button during operation
            self.dispense_btn.setEnabled(False)
            self.dispense_btn.setText("Building Pressure...")
            
            # Use the combined dispense operation method
            if self.pgva_comm.perform_dispense_operation(setpoint, time_ms):
                logger.info(f"Dispense operation completed: {setpoint} mbar for {time_ms} ms")
            else:
                logger.error("Failed to perform dispense operation")
        except Exception as e:
            logger.error(f"Error during dispense: {e}")
        finally:
            # Re-enable button
            self.dispense_btn.setEnabled(True)
            self.dispense_btn.setText("Dispense")
    
    def update_status_details(self, status_data):
        """Update status details display."""
        try:
            # Check if status_data is a dictionary or just the raw status value
            if isinstance(status_data, dict):
                # It's a dictionary with status information
                has_errors = status_data.get('has_errors', False)
                status_info = status_data.get('status', {})
                
                # Update supply voltage status
                if has_errors:
                    self.supply_voltage_label.setText("Error")
                    self.supply_voltage_label.setStyleSheet("color: red;")
                else:
                    self.supply_voltage_label.setText("Nominal")
                    self.supply_voltage_label.setStyleSheet("color: green;")
                
                # Update pump status
                pump_state = status_info.get('pump_state', 'Unknown')
                self.pump_status_label.setText(pump_state)
                
                # Update pressure chamber status
                pressure_bits = status_info.get('bits', {})
                if pressure_bits.get(3, {}).get('value') == 1:
                    self.pressure_chamber_label.setText("Below Threshold")
                    self.pressure_chamber_label.setStyleSheet("color: orange;")
                else:
                    self.pressure_chamber_label.setText("Nominal")
                    self.pressure_chamber_label.setStyleSheet("color: green;")
                
                # Update dispense valve status
                if pressure_bits.get(7, {}).get('value') == 1:
                    self.dispense_valve_label.setText("Open")
                    self.dispense_valve_label.setStyleSheet("color: blue;")
                else:
                    self.dispense_valve_label.setText("Closed")
                    self.dispense_valve_label.setStyleSheet("color: black;")
                
                # Update vacuum chamber status
                if pressure_bits.get(4, {}).get('value') == 1:
                    self.vacuum_chamber_label.setText("Below Threshold")
                    self.vacuum_chamber_label.setStyleSheet("color: orange;")
                else:
                    self.vacuum_chamber_label.setText("Nominal")
                    self.vacuum_chamber_label.setStyleSheet("color: green;")
            else:
                # It's probably just the raw status value, parse it
                from pgva_controller_plugin.services.pgva_status_parser import PGVAStatusParser
                
                # Convert to int if it's not already
                status_value = int(status_data) if status_data else 0
                parsed_status = PGVAStatusParser.parse_status_word(status_value)
                
                # Update supply voltage status (assume nominal if no errors)
                self.supply_voltage_label.setText("Nominal")
                self.supply_voltage_label.setStyleSheet("color: green;")
                
                # Update pump status from parsed bits
                pump_state = parsed_status.get('pump_state', 'Unknown')
                self.pump_status_label.setText(pump_state)
                
                # Update status based on parsed bits
                bits = parsed_status.get('bits', {})
                
                # Update pressure chamber status
                if bits.get(3, {}).get('value') == 1:
                    self.pressure_chamber_label.setText("Below Threshold")
                    self.pressure_chamber_label.setStyleSheet("color: orange;")
                else:
                    self.pressure_chamber_label.setText("Nominal")
                    self.pressure_chamber_label.setStyleSheet("color: green;")
                
                # Update dispense valve status
                if bits.get(7, {}).get('value') == 1:
                    self.dispense_valve_label.setText("Open")
                    self.dispense_valve_label.setStyleSheet("color: blue;")
                else:
                    self.dispense_valve_label.setText("Closed")
                    self.dispense_valve_label.setStyleSheet("color: black;")
                
                # Update vacuum chamber status
                if bits.get(4, {}).get('value') == 1:
                    self.vacuum_chamber_label.setText("Below Threshold")
                    self.vacuum_chamber_label.setStyleSheet("color: orange;")
                else:
                    self.vacuum_chamber_label.setText("Nominal")
                    self.vacuum_chamber_label.setStyleSheet("color: green;")
                
        except Exception as e:
            logger.error(f"Error updating status details: {e}")


class PGVAStatusWidget(QGroupBox):
    """Widget for PGVA status monitoring with device information display."""
    
    def __init__(self, parent=None):
        super().__init__("Status", parent)
        self.pgva_comm = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the status monitoring UI to match the device interface."""
        layout = QVBoxLayout(self)
        
        # Main information grid
        info_layout = QGridLayout()
        
        # Left column - Current values
        actual_pressure_title = QLabel("Actual pressure [mbar]")
        actual_pressure_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(actual_pressure_title, 0, 0, 1, 2)  # Span 2 columns
        
        info_layout.addWidget(QLabel("PGVA Pressure output"), 1, 0)
        self.pressure_output_label = QLabel("-")
        self.pressure_output_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.pressure_output_label, 1, 1)
        
        info_layout.addWidget(QLabel("Pressure chamber"), 2, 0)
        self.pressure_chamber_value_label = QLabel("-")
        self.pressure_chamber_value_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.pressure_chamber_value_label, 2, 1)
        
        info_layout.addWidget(QLabel("Vacuum chamber"), 3, 0)
        self.vacuum_chamber_value_label = QLabel("-")
        self.vacuum_chamber_value_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.vacuum_chamber_value_label, 3, 1)
        
        # Right column - Device info
        info_layout.addWidget(QLabel("Firmware"), 0, 2)
        self.firmware_label = QLabel("-")
        self.firmware_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.firmware_label, 0, 3)
        
        info_layout.addWidget(QLabel("Connectivity"), 1, 2)
        self.connectivity_label = QLabel("Disconnected")
        self.connectivity_label.setStyleSheet("font-weight: bold; font-size: 14px; color: red;")
        info_layout.addWidget(self.connectivity_label, 1, 3)
        
        info_layout.addWidget(QLabel("Status"), 2, 2)
        self.device_status_label = QLabel("-")
        self.device_status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.device_status_label, 2, 3)
        
        layout.addLayout(info_layout)
        
        # Status log (smaller, at bottom)
        status_log_label = QLabel("Status Log:")
        layout.addWidget(status_log_label)
        
        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(150)
        self.status_text.setReadOnly(True)
        self.status_text.setStyleSheet("background-color: #f8f8f8;")
        layout.addWidget(self.status_text)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.get_status_btn = QPushButton("Get Status")
        self.get_status_btn.clicked.connect(self.get_status)
        button_layout.addWidget(self.get_status_btn)
        
        self.get_warnings_btn = QPushButton("Get Warnings")
        self.get_warnings_btn.clicked.connect(self.get_warnings)
        button_layout.addWidget(self.get_warnings_btn)
        
        self.get_errors_btn = QPushButton("Get Errors")
        self.get_errors_btn.clicked.connect(self.get_errors)
        button_layout.addWidget(self.get_errors_btn)
        
        self.get_comprehensive_btn = QPushButton("Comprehensive Status")
        self.get_comprehensive_btn.clicked.connect(self.get_comprehensive_status)
        button_layout.addWidget(self.get_comprehensive_btn)
        
        self.health_check_btn = QPushButton("Health Check")
        self.health_check_btn.clicked.connect(self.get_health_check)
        button_layout.addWidget(self.health_check_btn)
        
        layout.addLayout(button_layout)
    
    def set_pgva_comm(self, pgva_comm):
        """Set the PGVA communication object."""
        self.pgva_comm = pgva_comm
    
    def get_status(self):
        """Get device status."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            status = self.pgva_comm.get_status()
            parsed_status = PGVAStatusParser.parse_status_word(status)
            self.update_status({'status': parsed_status, 'timestamp': datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"Error getting status: {e}")
    
    def get_warnings(self):
        """Get device warnings."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            warnings = self.pgva_comm.get_warnings()
            parsed_warnings = PGVAStatusParser.parse_warning_word(warnings)
            self.update_warnings({'warnings': parsed_warnings, 'timestamp': datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"Error getting warnings: {e}")
    
    def get_errors(self):
        """Get device errors."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            errors = self.pgva_comm.get_errors()
            parsed_errors = PGVAStatusParser.parse_error_word(errors)
            self.update_errors({'errors': parsed_errors, 'timestamp': datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"Error getting errors: {e}")
    
    def get_comprehensive_status(self):
        """Get comprehensive status."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            comprehensive_status = self.pgva_comm.get_comprehensive_status()
            self.update_comprehensive_status({'comprehensive_status': comprehensive_status, 'timestamp': datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"Error getting comprehensive status: {e}")
    
    def get_health_check(self):
        """Get health check."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            health = self.pgva_comm.check_device_health()
            self.update_health_check({'health_check': health, 'timestamp': datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"Error getting health check: {e}")
    
    def update_status(self, data):
        """Update status display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        raw_status = data.get('raw_status', 'Unknown')
        
        # Update device status display
        try:
            if isinstance(data, dict) and 'status' in data:
                status_info = data['status']
                if isinstance(status_info, dict):
                    # Get status summary for display
                    summary_parts = status_info.get('summary', [])
                    if summary_parts:
                        status_message = " | ".join(summary_parts)
                        self.status_text.append(f"[{timestamp}] Status: {status_message}")
                    else:
                        self.status_text.append(f"[{timestamp}] Status: {raw_status}")
                    
                    # Update device status based on parsed status
                    pump_state = status_info.get('pump_state', 'Unknown')
                    if 'idle' in pump_state.lower():
                        self.device_status_label.setText("Idle")
                    elif 'busy' in pump_state.lower():
                        self.device_status_label.setText("Busy")
                    else:
                        self.device_status_label.setText(pump_state)
                        
                    # Also check the idle/busy bit directly
                    bits = status_info.get('bits', {})
                    if bits.get(0, {}).get('value') == 0:
                        self.device_status_label.setText("Idle")
                    elif bits.get(0, {}).get('value') == 1:
                        self.device_status_label.setText("Busy")
                else:
                    self.status_text.append(f"[{timestamp}] Status: {raw_status}")
            else:
                self.status_text.append(f"[{timestamp}] Status: {raw_status}")
        except Exception as e:
            logger.error(f"Error updating status display: {e}")
            self.status_text.append(f"[{timestamp}] Status: {raw_status} (Error parsing)")
    
    def update_pressure_values(self, pressure_data=None, vacuum_data=None, output_data=None):
        """Update pressure values display."""
        try:
            if pressure_data:
                self.pressure_chamber_value_label.setText(str(int(pressure_data.get('pressure', 0))))
            if vacuum_data:
                self.vacuum_chamber_value_label.setText(str(int(vacuum_data.get('vacuum', 0))))
            if output_data:
                # The set output pressure goes under "PGVA Pressure output" title
                self.pressure_output_label.setText(str(int(output_data.get('output_pressure', 0))))
        except Exception as e:
            logger.error(f"Error updating pressure values: {e}")
    
    def update_device_info(self, device_info):
        """Update device information display."""
        try:
            if isinstance(device_info, dict):
                # Update firmware version
                fw_version_major = device_info.get('firmware_version', None)
                if fw_version_major is None:
                    fw_version = 'Unknown'
                else:
                    fw_version_sub = device_info.get('firmware_sub_version', 0)
                    fw_version_build = device_info.get('firmware_build', 0)
                    fw_version = f'{fw_version_major}.{fw_version_sub}.{fw_version_build}'
                self.firmware_label.setText(fw_version)
        except Exception as e:
            logger.error(f"Error updating device info: {e}")
    
    def update_connectivity_status(self, connected):
        """Update connectivity status display."""
        if connected:
            self.connectivity_label.setText("Connected")
            self.connectivity_label.setStyleSheet("font-weight: bold; font-size: 14px; color: green;")
        else:
            self.connectivity_label.setText("Disconnected")
            self.connectivity_label.setStyleSheet("font-weight: bold; font-size: 14px; color: red;")
    
    def update_warnings(self, data):
        """Update warnings display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        warnings = data['warnings']
        if warnings.get('count', 0) > 0:
            self.status_text.append(f"[{timestamp}] Warnings ({warnings['count']}):")
            for warning in warnings.get('warnings', []):
                self.status_text.append(f"  - {warning['description']}: {warning['cause']}")
        else:
            self.status_text.append(f"[{timestamp}] No warnings")
    
    def update_errors(self, data):
        """Update errors display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        errors = data['errors']
        if errors.get('count', 0) > 0 or errors.get('modbus_count', 0) > 0:
            self.status_text.append(f"[{timestamp}] Errors ({errors['count']} + {errors['modbus_count']} Modbus):")
            for error in errors.get('errors', []):
                self.status_text.append(f"  - {error['description']}: {error['cause']}")
            for error in errors.get('modbus_errors', []):
                self.status_text.append(f"  - Modbus: {error['description']}: {error['cause']}")
        else:
            self.status_text.append(f"[{timestamp}] No errors")
    
    def update_comprehensive_status(self, data):
        """Update comprehensive status display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        status = data['comprehensive_status']
        self.status_text.append(f"[{timestamp}] Comprehensive Status:")
        self.status_text.append(f"  Summary: {status['summary']}")
        self.status_text.append(f"  Healthy: {status['is_healthy']}")
        self.status_text.append(f"  Warnings: {status['has_warnings']}")
        self.status_text.append(f"  Errors: {status['has_errors']}")
    
    def update_health_check(self, data):
        """Update health check display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        health = data['health_check']
        self.status_text.append(f"[{timestamp}] Health Check:")
        self.status_text.append(f"  Overall Health: {health['overall_health']}")
        self.status_text.append(f"  Status: {health['status_summary']}")
        if health.get('recommendations'):
            self.status_text.append("  Recommendations:")
            for rec in health['recommendations']:
                self.status_text.append(f"    - {rec}")


class PGVAOperationWidget(QGroupBox):
    """Widget for PGVA operations."""
    
    def __init__(self, parent=None):
        super().__init__("Device Operations", parent)
        self.pgva_comm = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the operations UI."""
        layout = QGridLayout(self)
        
        # Pump control
        layout.addWidget(QLabel("Pump Control:"), 0, 0, 1, 3)
        
        self.enable_btn = QPushButton("Enable Pump")
        self.enable_btn.clicked.connect(self.enable_pump)
        layout.addWidget(self.enable_btn, 1, 0)
        
        self.disable_btn = QPushButton("Disable Pump")
        self.disable_btn.clicked.connect(self.disable_pump)
        layout.addWidget(self.disable_btn, 1, 1)
        
        self.reset_btn = QPushButton("Reset Device")
        self.reset_btn.clicked.connect(self.reset_device)
        layout.addWidget(self.reset_btn, 1, 2)
        
        # Manual operations
        layout.addWidget(QLabel("Manual Operations:"), 2, 0, 1, 3)
        
        self.trigger_btn = QPushButton("Manual Trigger")
        self.trigger_btn.clicked.connect(self.manual_trigger)
        layout.addWidget(self.trigger_btn, 3, 0)
        
        self.close_trigger_btn = QPushButton("Close Trigger")
        self.close_trigger_btn.clicked.connect(self.close_trigger)
        layout.addWidget(self.close_trigger_btn, 3, 1)
        
        self.store_eeprom_btn = QPushButton("Store to EEPROM")
        self.store_eeprom_btn.clicked.connect(self.store_to_eeprom)
        layout.addWidget(self.store_eeprom_btn, 4, 0)
        
        self.get_device_info_btn = QPushButton("Get Device Info")
        self.get_device_info_btn.clicked.connect(self.get_device_info)
        layout.addWidget(self.get_device_info_btn, 4, 1)
    
    def set_pgva_comm(self, pgva_comm):
        """Set the PGVA communication object."""
        self.pgva_comm = pgva_comm
    
    def enable_pump(self):
        """Enable pump."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            if self.pgva_comm.enable_pump():
                logger.info("Pump enabled")
            else:
                logger.error("Failed to enable pump")
        except Exception as e:
            logger.error(f"Error enabling pump: {e}")
    
    def disable_pump(self):
        """Disable pump."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            if self.pgva_comm.disable_pump():
                logger.info("Pump disabled")
            else:
                logger.error("Failed to disable pump")
        except Exception as e:
            logger.error(f"Error disabling pump: {e}")
    
    def reset_device(self):
        """Reset device."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            if self.pgva_comm.reset_device():
                logger.info("Device reset completed successfully")
            else:
                logger.error("Failed to reset device")
        except Exception as e:
            logger.error(f"Error resetting device: {e}")
    
    def manual_trigger(self):
        """Manual trigger."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            if self.pgva_comm.trigger_manual():
                logger.info("Manual trigger activated")
            else:
                logger.error("Failed to activate manual trigger")
        except Exception as e:
            logger.error(f"Error with manual trigger: {e}")
    
    def close_trigger(self):
        """Close the trigger valve."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            if self.pgva_comm.close_trigger():
                logger.info("Trigger valve closed")
            else:
                logger.error("Failed to close trigger valve")
        except Exception as e:
            logger.error(f"Error closing trigger: {e}")
    
    def store_to_eeprom(self):
        """Store parameters to EEPROM."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            if self.pgva_comm.store_to_eeprom():
                logger.info("Parameters stored to EEPROM")
            else:
                logger.error("Failed to store to EEPROM")
        except Exception as e:
            logger.error(f"Error storing to EEPROM: {e}")
    
    def get_device_info(self):
        """Get device information."""
        if not self.pgva_comm or not self.pgva_comm.connected:
            logger.warning("Not connected to PGVA device")
            return
        
        try:
            device_info = self.pgva_comm.get_device_info()
            logger.info(f"Device info: {device_info}")
        except Exception as e:
            logger.error(f"Error getting device info: {e}")


class PGVAInfoWidget(QGroupBox):
    """Widget for PGVA device information."""
    
    def __init__(self, parent=None):
        super().__init__("Device Information", parent)
        self.pgva_comm = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the device info UI."""
        layout = QVBoxLayout(self)
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        layout.addWidget(self.info_text)
    
    def set_pgva_comm(self, pgva_comm):
        """Set the PGVA communication object."""
        self.pgva_comm = pgva_comm
    
    def update_device_info(self, data):
        """Update device information display."""
        device_info = data['device_info']
        self.info_text.clear()
        self.info_text.append("Device Information:")
        self.info_text.append("=" * 50)
        
        for key, value in device_info.items():
            self.info_text.append(f"{key.replace('_', ' ').title()}: {value}")
        
        self.info_text.append("\nLast updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class PGVAErrorWidget(QGroupBox):
    """Widget for PGVA error display."""
    
    def __init__(self, parent=None):
        super().__init__("Error Log", parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the error log UI."""
        layout = QVBoxLayout(self)
        
        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setStyleSheet("background-color: #f8f8f8; color: #d32f2f;")
        layout.addWidget(self.error_text)
        
        # Clear button
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.clear_log)
        layout.addWidget(clear_btn)
    
    def add_error(self, message):
        """Add error message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.error_text.append(f"[{timestamp}] ERROR: {message}")
    
    def clear_log(self):
        """Clear error log."""
        self.error_text.clear()


class PGVATestWindow(QMainWindow):
    """Main test window for PGVA controller."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PGVA Controller Test UI")
        self.setMinimumSize(1200, 800)
        
        # Initialize status monitor
        self.status_monitor = PGVAStatusMonitor()
        self.status_monitor.status_updated.connect(self.on_status_updated)
        self.status_monitor.pressure_updated.connect(self.on_pressure_updated)
        self.status_monitor.vacuum_updated.connect(self.on_vacuum_updated)
        self.status_monitor.output_pressure_updated.connect(self.on_output_pressure_updated)
        self.status_monitor.warnings_updated.connect(self.on_warnings_updated)
        self.status_monitor.errors_updated.connect(self.on_errors_updated)
        self.status_monitor.health_updated.connect(self.on_health_updated)
        self.status_monitor.device_info_updated.connect(self.on_device_info_updated)
        self.status_monitor.connection_changed.connect(self.on_connection_changed)
        self.status_monitor.error_occurred.connect(self.on_error_occurred)
        
        self.setup_ui()
        self.center_window()
        
        # Start status monitor
        self.status_monitor.start()
    
    def setup_ui(self):
        """Setup the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title_label = QLabel("Festo PGVA Controller Test Interface")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setWeight(QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Create splitter for main content
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - Controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Connection widget
        self.connection_widget = PGVAConnectionWidget()
        self.connection_widget.connection_changed.connect(self.on_connection_changed)
        left_layout.addWidget(self.connection_widget)
        
        # Pressure control widget
        self.pressure_widget = PGVAPressureControlWidget()
        left_layout.addWidget(self.pressure_widget)
        
        # Operations widget
        self.operation_widget = PGVAOperationWidget()
        left_layout.addWidget(self.operation_widget)
        
        # Add stretch to push widgets to top
        left_layout.addStretch()
        
        # Right panel - Status and Info
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Create tab widget for right panel
        tab_widget = QTabWidget()
        
        # Status tab
        self.status_widget = PGVAStatusWidget()
        tab_widget.addTab(self.status_widget, "Status")
        
        # Device info tab
        self.info_widget = PGVAInfoWidget()
        tab_widget.addTab(self.info_widget, "Device Info")
        
        # Error log tab
        self.error_widget = PGVAErrorWidget()
        tab_widget.addTab(self.error_widget, "Error Log")
        
        right_layout.addWidget(tab_widget)
        
        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 800])  # Set initial sizes
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.statusBar().showMessage("Ready - Connect to PGVA device to begin testing")
    
    def center_window(self):
        """Center the window on the screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        window_geometry = self.geometry()
        x = (screen.width() - window_geometry.width()) // 2
        y = (screen.height() - window_geometry.height()) // 2
        self.move(x, y)
    
    # Signal handlers
    def on_status_updated(self, data):
        """Handle status update."""
        self.status_widget.update_status(data)
        self.pressure_widget.update_status_details(data)
    
    def on_pressure_updated(self, data):
        """Handle pressure update."""
        self.status_widget.update_pressure_values(pressure_data=data)
    
    def on_vacuum_updated(self, data):
        """Handle vacuum update."""
        self.status_widget.update_pressure_values(vacuum_data=data)
    
    def on_output_pressure_updated(self, data):
        """Handle output pressure update."""
        self.status_widget.update_pressure_values(output_data=data)
    
    def on_warnings_updated(self, data):
        """Handle warnings update."""
        self.status_widget.update_warnings(data)
    
    def on_errors_updated(self, data):
        """Handle errors update."""
        self.status_widget.update_errors(data)
    
    def on_health_updated(self, data):
        """Handle health check update."""
        self.status_widget.update_health_check(data)
    
    def on_device_info_updated(self, data):
        """Handle device info update."""
        self.info_widget.update_device_info(data)
        self.status_widget.update_device_info(data)
    
    def on_connection_changed(self, connected):
        """Handle connection status change."""
        if connected:
            # Get the PGVA communication object from connection widget
            pgva_comm = self.connection_widget.get_pgva_comm()
            
            # Pass it to all widgets that need it
            self.pressure_widget.set_pgva_comm(pgva_comm)
            self.status_widget.set_pgva_comm(pgva_comm)
            self.operation_widget.set_pgva_comm(pgva_comm)
            self.info_widget.set_pgva_comm(pgva_comm)
            
            # Set it in the status monitor
            self.status_monitor.set_pgva_comm(pgva_comm)
            
            # Read firmware version from device
            device_info = pgva_comm.get_device_info()
            self.status_widget.update_device_info(device_info)
            
            self.statusBar().showMessage("Connected to PGVA device")
            self.status_widget.update_connectivity_status(True)
        else:
            # Clear PGVA communication objects
            self.pressure_widget.set_pgva_comm(None)
            self.status_widget.set_pgva_comm(None)
            self.operation_widget.set_pgva_comm(None)
            self.info_widget.set_pgva_comm(None)
            self.status_monitor.set_pgva_comm(None)
            
            # Reset display
            self.status_widget.firmware_label.setText("-")
            self.status_widget.pressure_output_label.setText("-")
            self.status_widget.pressure_chamber_value_label.setText("-")
            self.status_widget.vacuum_chamber_value_label.setText("-")
            self.status_widget.device_status_label.setText("-")
            
            self.statusBar().showMessage("Disconnected from PGVA device")
            self.status_widget.update_connectivity_status(False)
    
    def on_error_occurred(self, message):
        """Handle error occurrence."""
        self.error_widget.add_error(message)
        self.statusBar().showMessage(f"Error: {message}")
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Stop status monitor
        if self.status_monitor.isRunning():
            self.status_monitor.stop()
            self.status_monitor.wait()
        
        # Disconnect from PGVA if connected
        if self.connection_widget.get_pgva_comm():
            self.connection_widget.disconnect_device()
        
        event.accept()


def main():
    """Run the PGVA test UI application."""
    # Create QApplication
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("PGVA Controller Test UI")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Sci-bots")
    
    # Create and show main window
    window = PGVATestWindow()
    window.show()
    
    # Start event loop
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
