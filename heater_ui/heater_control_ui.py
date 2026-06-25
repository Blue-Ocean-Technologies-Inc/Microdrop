#!/usr/bin/env python3
import os
import re
import sys
import time
import json
import yaml
import shutil
import logging
import platform
import threading
import traceback
import subprocess

import serial as pyserial

from time import sleep
from pathlib import Path
from datetime import datetime
from scipy.signal import find_peaks, butter, filtfilt

import numpy as np
import pandas as pd

# Set matplotlib backend before importing PySide6
os.environ['QT_API'] = 'pyside6'  # Tell matplotlib to use PySide6
os.environ["QT_SCALE_FACTOR"] = "0.8"
import matplotlib
matplotlib.use('QtAgg')  # Use QtAgg backend for Qt6 compatibility
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSpinBox, QDoubleSpinBox, QFileDialog,
    QCheckBox, QTextEdit, QGroupBox, QStatusBar, QComboBox, QScrollArea, QRadioButton,
    QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QTabWidget
)
from PySide6.QtCore import Slot, Signal, QTimer, Qt
from PySide6.QtGui import QPalette, QAction

# Import the existing controller module
from controller import Board


# Constants
MAX_WINDOW_HEIGHT = 1200
PLOT_UPDATE_INTERVAL_MS = 500  # Plot update interval in milliseconds (faster updates)
MAX_PLOT_POINTS = 500  # Maximum number of points to display on plot (optimized for performance)
DEFAULT_SETPOINT = 40.0  # Default temperature setpoint in °C
INVALID_TEMP_THRESHOLD = -40  # Temperature values below this are considered invalid
COMMAND_DELAY_SHORT = 1  # Short delay between commands in seconds
COMMAND_DELAY_LONG = 2  # Long delay between commands in seconds
PID_QUERY_DELAY = 0.5  # Delay before querying PID values in seconds
ZN_SETPOINT_TOLERANCE = 2.0  # Temperature tolerance for ZN calibration in °C
DEFAULT_COMPENSATION_RATE = 1
DEFAULT_COMPENSATION_OFFSET = 0
DEFAULT_BAUDRATE = 115200
DEFAULT_PID = "0005"
DEFAULT_VID = "2E8A"
DEFAULT_ZMQ_PORT = "88080"


class DataLogger:
    """Handles data logging to JSON files"""

    def __init__(self, log_dir="heater_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.current_file = None
        self.file_handle = None

    def start_logging(self):
        """Start a new log file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_file = self.log_dir / f"{timestamp}.json"

        # Create file and open for appending (JSON format - one JSON object per line)
        self.file_handle = open(self.current_file, 'w')
        print(f"Started logging to: {self.current_file}")

    def log_data(self, data):
        """Log data point to JSON Lines format"""
        if self.file_handle:
            # Add timestamp to data
            data_with_timestamp = {
                'timestamp': datetime.now().isoformat(),
                **data
            }
            # Write as single line JSON
            self.file_handle.write(json.dumps(data_with_timestamp) + '\n')
            self.file_handle.flush()

    def stop_logging(self):
        """Stop logging and close file"""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None
            print(f"Stopped logging. Data saved to: {self.current_file}")


class RealTimePlot(FigureCanvas):
    """Real-time plotting widget"""

    def __init__(self, parent=None, width=8, height=6, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)

        # Create subplots
        self.ax1 = self.fig.add_subplot(211)  # Temperature plot
        self.ax2 = self.fig.add_subplot(212)  # PWM plot

        # Data storage
        self.timestamps = []
        self.sensor_data = {}  # Dynamic dictionary for all sensors: {'thermistor1': [], 'top-left': [], ...}
        self.pid_temp_data = []
        self.heater1_pwm_data = []
        self.heater2_pwm_data = []
        self.setpoint_data = []

        # Color palette for dynamic sensors (using matplotlib color names)
        self.color_palette = [
            'tab:blue', 'tab:red', 'tab:green', 'tab:orange',
            'tab:purple', 'tab:brown', 'tab:pink', 'tab:gray',
            'tab:olive', 'tab:cyan'
        ]

        # Widget state
        self._destroyed = False

        # Cache theme colors
        self._cached_theme = None
        self._bg_color = None
        self._text_color = None
        self._grid_color = None

        # Plot setup
        self.setup_plots()

        # Animation - use QTimer instead of FuncAnimation for better stability
        self.animation = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.start_animation()

    def start_animation(self):
        """Start the animation"""
        if not self._destroyed and self.timer:
            self.timer.start(PLOT_UPDATE_INTERVAL_MS)

    def stop_animation(self):
        """Stop the animation"""
        self._destroyed = True
        if self.timer:
            self.timer.stop()
        if self.animation is not None:
            try:
                self.animation.event_source.stop()
                self.animation._stop()
            except Exception:
                pass
            self.animation = None

    def closeEvent(self, event):
        """Handle widget close event"""
        self.stop_animation()
        super().closeEvent(event)

    def __del__(self):
        """Destructor to ensure proper cleanup"""
        try:
            self.stop_animation()
        except Exception:
            pass

    def _update_theme_colors(self):
        """Update cached theme colors based on current palette"""
        palette = QApplication.palette()
        is_dark = palette.color(QPalette.Window).lightness() < 128

        if is_dark:
            self._bg_color = '#2b2b2b'
            self._text_color = '#ffffff'
            self._grid_color = '#555555'
        else:
            self._bg_color = '#ffffff'
            self._text_color = '#000000'
            self._grid_color = '#cccccc'

        self._cached_theme = is_dark

    def setup_plots(self):
        """Setup the plot appearance"""
        # Update theme colors
        self._update_theme_colors()

        # Set figure background
        self.fig.patch.set_facecolor(self._bg_color)

        # Temperature plot
        self.ax1.set_title("Temperature Control", fontsize=12, fontweight='bold', color=self._text_color)
        self.ax1.set_ylabel("Temperature (°C)", fontsize=10, color=self._text_color)
        self.ax1.set_xlim(0, 1)  # Initial x-axis range
        self.ax1.set_ylim(0, 100)  # Initial y-axis range
        self.ax1.grid(True, alpha=0.3, color=self._grid_color)
        self.ax1.set_facecolor(self._bg_color)
        self.ax1.tick_params(colors=self._text_color)

        # PWM plot
        self.ax2.set_title("Heater PWM Control", fontsize=12, fontweight='bold', color=self._text_color)
        self.ax2.set_xlabel("Time (s)", fontsize=10, color=self._text_color)
        self.ax2.set_ylabel("PWM (%)", fontsize=10, color=self._text_color)
        self.ax2.set_xlim(0, 1)  # Initial x-axis range
        self.ax2.set_ylim(-10, 110)  # Initial y-axis range (with margin)
        self.ax2.grid(True, alpha=0.3, color=self._grid_color)
        self.ax2.set_facecolor(self._bg_color)
        self.ax2.tick_params(colors=self._text_color)

        # Apply tight layout with padding to prevent label cutoff
        self.fig.tight_layout(pad=3)

    def add_data_point(self, timestamp, temperatures, pid_temp,
                       heater1_pwm, heater2_pwm, setpoint):
        """Add a new data point with dynamic sensors

        Args:
            timestamp: Time value
            temperatures: Dict of sensor_name: temperature_value
            pid_temp: PID temperature
            heater1_pwm: HEATER1 PWM value
            heater2_pwm: HEATER2 PWM value
            setpoint: Temperature setpoint
        """
        self.timestamps.append(timestamp)

        # First, pad any existing sensors that aren't in this update
        for sensor_name in self.sensor_data:
            if sensor_name not in temperatures:
                self.sensor_data[sensor_name].append(None)

        # Add data for each sensor in this update
        for sensor_name, temp_value in temperatures.items():
            if sensor_name not in self.sensor_data:
                # New sensor - pad with None to match current timestamp length
                self.sensor_data[sensor_name] = [None] * (
                    len(self.timestamps) - 1)
            self.sensor_data[sensor_name].append(temp_value)

        self.pid_temp_data.append(pid_temp)
        self.heater1_pwm_data.append(heater1_pwm)
        self.heater2_pwm_data.append(heater2_pwm)
        self.setpoint_data.append(setpoint)

        # Keep only last MAX_PLOT_POINTS
        if len(self.timestamps) > MAX_PLOT_POINTS:
            self.timestamps = self.timestamps[-MAX_PLOT_POINTS:]
            for sensor_name in self.sensor_data:
                self.sensor_data[sensor_name] = self.sensor_data[sensor_name][-MAX_PLOT_POINTS:]
            self.pid_temp_data = self.pid_temp_data[-MAX_PLOT_POINTS:]
            self.heater1_pwm_data = self.heater1_pwm_data[-MAX_PLOT_POINTS:]
            self.heater2_pwm_data = self.heater2_pwm_data[-MAX_PLOT_POINTS:]
            self.setpoint_data = self.setpoint_data[-MAX_PLOT_POINTS:]

    def update_plot(self, frame=None):
        """Update the plot with new data - optimized for performance"""
        # Fast exit checks
        if self._destroyed or not self.timestamps:
            return

        try:
            # Check if theme changed (only check occasionally for performance)
            if len(self.timestamps) % 10 == 0:  # Check every 10th update
                palette = QApplication.palette()
                is_dark = palette.color(QPalette.Window).lightness() < 128
                if self._cached_theme != is_dark:
                    self._update_theme_colors()

            # Clear and redraw
            self.ax1.clear()
            self.ax2.clear()

            # Temperature plot - plot all dynamic sensors (optimized)
            color_idx = 0
            for sensor_name in sorted(self.sensor_data.keys()):
                sensor_values = self.sensor_data[sensor_name]
                # Skip empty or all-None data
                if not sensor_values:
                    continue

                # Quick check if any valid data exists
                has_data = False
                for val in sensor_values:
                    if val is not None:
                        has_data = True
                        break

                if has_data:
                    color = self.color_palette[color_idx % len(self.color_palette)]
                    self.ax1.plot(
                        self.timestamps, sensor_values, '-',
                        color=color, label=sensor_name,
                        linewidth=2, alpha=0.8)
                    color_idx += 1

            # Plot PID temperature with distinct style
            if self.pid_temp_data and any(
                    t is not None for t in self.pid_temp_data):
                self.ax1.plot(
                    self.timestamps, self.pid_temp_data, '-',
                    color='black', label='PID Temp',
                    linewidth=2.5, alpha=0.7)

            # Plot setpoint
            if self.setpoint_data and any(
                    t is not None for t in self.setpoint_data):
                self.ax1.plot(
                    self.timestamps, self.setpoint_data, '--',
                    color='green', label='Setpoint', linewidth=2)

            # Set axis properties
            self.ax1.set_title("Temperature Control", fontsize=12,
                              fontweight='bold', color=self._text_color)
            self.ax1.set_ylabel("Temperature (°C)", fontsize=10, 
                               color=self._text_color)
            self.ax1.grid(True, alpha=0.3, color=self._grid_color)
            self.ax1.set_facecolor(self._bg_color)
            self.ax1.tick_params(colors=self._text_color)
            
            # Calculate number of legend items (sensors + PID temp + setpoint)
            num_legend_items = color_idx
            if self.pid_temp_data and any(t is not None for t in self.pid_temp_data):
                num_legend_items += 1
            if self.setpoint_data and any(t is not None for t in self.setpoint_data):
                num_legend_items += 1
            
            # Use multiple columns if more than 12 items
            legend_ncol = 1 if num_legend_items <= 12 else num_legend_items // 12 + 1
            fontsize = 8 if num_legend_items <= 12 else 5.5
            
            self.ax1.legend(loc='center left', bbox_to_anchor=(1.005, 0.5),
                           facecolor=self._bg_color, edgecolor=self._text_color,
                           labelcolor=self._text_color, fontsize=fontsize, ncol=legend_ncol)

            # PWM plot
            if self.heater1_pwm_data:
                self.ax2.plot(self.timestamps, self.heater1_pwm_data, '-',
                             color='blue', label='TEC1 PWM', linewidth=2)
            if self.heater2_pwm_data:
                self.ax2.plot(self.timestamps, self.heater2_pwm_data, '-',
                             color='red', label='TEC2 PWM', linewidth=2)

            self.ax2.set_title("Heater PWM Control", fontsize=12,
                              fontweight='bold', color=self._text_color)
            self.ax2.set_xlabel("Time (s)", fontsize=10, color=self._text_color)
            self.ax2.set_ylabel("PWM (%)", fontsize=10, color=self._text_color)
            self.ax2.grid(True, alpha=0.3, color=self._grid_color)
            self.ax2.set_facecolor(self._bg_color)
            self.ax2.tick_params(colors=self._text_color)
            self.ax2.legend(loc='center left', bbox_to_anchor=(1.005, 0.8),
                           facecolor=self._bg_color, edgecolor=self._text_color,
                           labelcolor=self._text_color, fontsize=8)

            self.fig.tight_layout()
            self.draw()

        except (RuntimeError, AttributeError):
            # Widget has been deleted during drawing
            self._destroyed = True
            return


FIRMWARE_CONFIG_PATH = "firmware/config.json"
# Bus-level keys inside `temperature_sensors.1-wire-sensors` that are NOT
# sensor-name -> ROM mappings and must be preserved when we rewrite the
# block.
_OW_RESERVED_KEYS = {"pin", "conv_mode", "resolution"}


class SensorConfigDialog(QDialog):
    """Scan the 1-Wire bus, name discovered sensors, assign them to heaters,
    and save back to firmware/config.json (and optionally push the file to
    the board over mpremote). On open, pulls the live config from the
    board if connected; falls back to the local file otherwise."""

    SCAN_TIMEOUT_MS = 3000
    CONFIG_PULL_TIMEOUT_MS = 4000
    MPREMOTE_TIMEOUT_S = 25

    # Sensor table columns
    COL_CHECK = 0
    COL_ROM = 1
    COL_NAME = 2
    COL_STATUS = 3

    # Heater table columns
    HCOL_NAME = 0
    HCOL_TYPE = 1
    HCOL_SENSORS = 2

    def __init__(self, board, parent=None):
        super().__init__(parent)
        self.board = board
        self._parent_ui = parent
        self.setWindowTitle("Configure Sensors & Heaters")
        self.resize(820, 560)

        self._signal_connected = False
        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.timeout.connect(self._on_scan_timeout)
        self._pull_timer = QTimer(self)
        self._pull_timer.setSingleShot(True)
        self._pull_timer.timeout.connect(self._on_pull_timeout)

        self.config_data = {}
        self.ow_section = {}
        self.thermistors_section = {}
        self.heaters_section = {}
        self.existing_map = {}  # rom (lower) -> name
        # Per-ROM tracking: rom -> {'from_config': bool, 'seen_on_bus': bool}
        self._rom_state = {}
        self._scan_done = False

        # Config-pull state
        self._capturing_config = False
        self._config_buffer = []
        self._config_source = "(none)"

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Scan the 1-Wire bus, name sensors, and assign them to heaters. "
            "On open, the config is pulled live from the board if connected; "
            "otherwise it falls back to the local firmware/config.json."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.source_label = QLabel("")
        self.source_label.setStyleSheet("color: gray;")
        layout.addWidget(self.source_label)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_sensors_tab(), "Sensors")
        self.tabs.addTab(self._build_heaters_tab(), "Heater Assignments")
        layout.addWidget(self.tabs, 1)

        # Bottom button row (shared across tabs)
        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh from Board")
        self.refresh_btn.setToolTip(
            "Re-pull the live config from the board (requires connection).")
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch()
        self.save_btn = QPushButton("Save to config.json")
        self.save_btn.setToolTip(
            "Write changes to local firmware/config.json only. "
            "You'll still need to re-upload firmware for the board to "
            "see them.")
        self.save_btn.clicked.connect(self._on_save_local)
        btn_row.addWidget(self.save_btn)
        self.push_btn = QPushButton("Save && Push to Board")
        self.push_btn.setToolTip(
            "Save to local config.json AND copy it to the board via "
            "mpremote. Briefly disconnects, copies the file, reboots the "
            "board, then reconnects.")
        self.push_btn.clicked.connect(self._on_save_and_push)
        btn_row.addWidget(self.push_btn)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

        # Initial load: pull from board if possible, else local file.
        if self.board is not None and self.board.connected:
            self._start_pull_from_board()
        else:
            self._load_local_config()
            self._config_source = f"local file ({FIRMWARE_CONFIG_PATH})"
            self._update_source_label()
            self._populate_from_config()

    # ------------------------------------------------------------------
    # Tab construction
    # ------------------------------------------------------------------

    def _build_sensors_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        top_bar = QHBoxLayout()
        self.scan_btn = QPushButton("Scan for Sensors")
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        top_bar.addWidget(self.scan_btn)
        self.status_label = QLabel("")
        top_bar.addWidget(self.status_label, 1)
        v.addLayout(top_bar)

        self.table = QTableWidget(0, 4, w)
        self.table.setHorizontalHeaderLabels(
            ["Save", "ROM (hex)", "Name", "Status"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_ROM, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        h.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, 1)
        return w

    def _build_heaters_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Edit the comma-separated sensor list for each heater. Use "
            "1-Wire sensor names from the Sensors tab and thermistor names "
            "from the config (e.g. thermistor1, thermistor2)."))
        self.heaters_table = QTableWidget(0, 3, w)
        self.heaters_table.setHorizontalHeaderLabels(
            ["Heater", "Type", "Sensors (comma-separated)"])
        h = self.heaters_table.horizontalHeader()
        h.setSectionResizeMode(self.HCOL_NAME, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.HCOL_TYPE, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.HCOL_SENSORS, QHeaderView.Stretch)
        self.heaters_table.verticalHeader().setVisible(False)
        v.addWidget(self.heaters_table, 1)

        v.addWidget(QLabel("Available sensor names (for reference):"))
        self.available_sensors_label = QLabel("(loading…)")
        self.available_sensors_label.setWordWrap(True)
        self.available_sensors_label.setStyleSheet("color: gray;")
        v.addWidget(self.available_sensors_label)
        return w

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_local_config(self):
        try:
            with open(FIRMWARE_CONFIG_PATH, "r") as f:
                self.config_data = json.load(f)
        except Exception as e:
            self.config_data = {}
            QMessageBox.warning(
                self, "Config load error",
                f"Could not read {FIRMWARE_CONFIG_PATH}:\n{e}\n\n"
                "Scan will still work but existing names won't be "
                "pre-populated.")
        self._derive_sections()

    def _derive_sections(self):
        cfg = self.config_data if isinstance(self.config_data, dict) else {}
        ts = cfg.get("temperature_sensors", {}) if isinstance(
            cfg, dict) else {}
        self.ow_section = ts.get("1-wire-sensors", {}) if isinstance(
            ts, dict) else {}
        self.thermistors_section = ts.get("thermistors", {}) if isinstance(
            ts, dict) else {}
        self.heaters_section = cfg.get("heaters", {}) if isinstance(
            cfg, dict) else {}
        self.existing_map = {
            str(rom).lower(): name
            for name, rom in self.ow_section.items()
            if name not in _OW_RESERVED_KEYS and isinstance(rom, str)
        }

    def _update_source_label(self):
        self.source_label.setText(f"Config source: {self._config_source}")

    # ------------------------------------------------------------------
    # Pull config from board
    # ------------------------------------------------------------------

    def _on_refresh_clicked(self):
        if self.board is None or not self.board.connected:
            QMessageBox.warning(
                self, "Not connected",
                "Connect to the board first, then try again.")
            return
        self._start_pull_from_board()

    def _start_pull_from_board(self):
        self.refresh_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.push_btn.setEnabled(False)
        self.status_label.setText("Pulling config from board…")
        self._capturing_config = True
        self._config_buffer = []
        if not self._signal_connected:
            self.board.message_received.connect(self._on_board_message)
            self._signal_connected = True
        try:
            self.board.send_cmd("dump_config")
        except Exception as e:
            self._capturing_config = False
            self.status_label.setText(f"Failed to send dump_config: {e}")
            self._on_pull_finished(success=False)
            return
        self._pull_timer.start(self.CONFIG_PULL_TIMEOUT_MS)

    def _on_pull_timeout(self):
        if not self._capturing_config:
            return  # already finished cleanly
        self._capturing_config = False
        self.status_label.setText("Config pull timed out — using local file.")
        self._load_local_config()
        self._config_source = (
            f"local file (pull from board timed out: {FIRMWARE_CONFIG_PATH})")
        self._update_source_label()
        self._populate_from_config()
        self._on_pull_finished(success=False)

    def _on_pull_finished(self, success):
        self.refresh_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.push_btn.setEnabled(True)
        if self._signal_connected and not self._scan_timer.isActive():
            try:
                self.board.message_received.disconnect(self._on_board_message)
            except Exception:
                pass
            self._signal_connected = False

    # ------------------------------------------------------------------
    # Board message routing (handles both scan responses and config pull)
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_board_message(self, line):
        stripped = line.strip()

        # Config-pull state machine
        if self._capturing_config:
            if stripped == "<<<CONFIG_BEGIN>>>":
                self._config_buffer = []
                return
            if stripped == "<<<CONFIG_END>>>":
                self._pull_timer.stop()
                self._finish_config_capture()
                return
            if stripped.startswith("<<<CONFIG_ERROR"):
                self._pull_timer.stop()
                self._capturing_config = False
                self.status_label.setText(
                    f"Board reported error pulling config: {stripped}")
                self._load_local_config()
                self._config_source = (
                    f"local file (board errored: {stripped})")
                self._update_source_label()
                self._populate_from_config()
                self._on_pull_finished(success=False)
                return
            # Otherwise, accumulate as config content
            self._config_buffer.append(line)
            return

        # Scan response: "Sensor N: <hex>"
        m = re.match(r"Sensor\s+\d+\s*:\s*([0-9a-fA-F]{16})", stripped)
        if not m:
            return
        rom = m.group(1).lower()
        st = self._rom_state.setdefault(
            rom, {'from_config': False, 'seen_on_bus': False})
        st['seen_on_bus'] = True
        name = self.existing_map.get(rom, "")
        self._add_or_update_row(rom, name)
        self._refresh_statuses()

    def _finish_config_capture(self):
        self._capturing_config = False
        raw = "\n".join(self._config_buffer)
        try:
            self.config_data = json.loads(raw)
            self._derive_sections()
            self._config_source = "live from board (dump_config)"
            self._update_source_label()
            self.status_label.setText(
                "Config pulled from board successfully.")
            self._populate_from_config()
            self._on_pull_finished(success=True)
        except Exception as e:
            self.status_label.setText(
                f"Failed to parse config from board ({e}); using local file.")
            self._load_local_config()
            self._config_source = (
                f"local file (board response unparseable: {e})")
            self._update_source_label()
            self._populate_from_config()
            self._on_pull_finished(success=False)

    # ------------------------------------------------------------------
    # Table population (from current config_data)
    # ------------------------------------------------------------------

    def _populate_from_config(self):
        # Wipe + rebuild sensors table
        self.table.setRowCount(0)
        self._rom_state = {}
        self._scan_done = False
        for rom, name in self.existing_map.items():
            self._rom_state[rom] = {'from_config': True, 'seen_on_bus': False}
            self._add_or_update_row(rom, name)
        self._refresh_statuses()

        # Wipe + rebuild heater assignments table
        self._populate_heaters()
        # Update the "available sensor names" hint
        names = sorted(set(list(self.existing_map.values()) +
                           list(self.thermistors_section.keys())))
        names = [n for n in names if n]  # drop empties
        self.available_sensors_label.setText(
            ", ".join(names) if names else "(none defined yet)")

    def _populate_heaters(self):
        self.heaters_table.setRowCount(0)
        if not isinstance(self.heaters_section, dict):
            return
        for heater_name, heater_cfg in self.heaters_section.items():
            row = self.heaters_table.rowCount()
            self.heaters_table.insertRow(row)
            name_item = QTableWidgetItem(heater_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.heaters_table.setItem(row, self.HCOL_NAME, name_item)
            htype = heater_cfg.get("type", "?") if isinstance(
                heater_cfg, dict) else "?"
            type_item = QTableWidgetItem(str(htype))
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.heaters_table.setItem(row, self.HCOL_TYPE, type_item)
            sensors = heater_cfg.get("sensors", []) if isinstance(
                heater_cfg, dict) else []
            if not isinstance(sensors, list):
                sensors = []
            sensors_item = QTableWidgetItem(", ".join(str(s) for s in sensors))
            self.heaters_table.setItem(row, self.HCOL_SENSORS, sensors_item)

    # ------------------------------------------------------------------
    # Sensors table helpers
    # ------------------------------------------------------------------

    def _add_or_update_row(self, rom, name):
        rom = rom.lower()
        for r in range(self.table.rowCount()):
            existing = self.table.item(r, self.COL_ROM).text().lower()
            if existing == rom:
                name_item = self.table.item(r, self.COL_NAME)
                if name and name_item and not name_item.text():
                    name_item.setText(name)
                return r
        row = self.table.rowCount()
        self.table.insertRow(row)
        check_item = QTableWidgetItem()
        check_item.setFlags(
            (check_item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
        check_item.setCheckState(Qt.Checked)
        check_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, self.COL_CHECK, check_item)
        rom_item = QTableWidgetItem(rom)
        rom_item.setFlags(rom_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_ROM, rom_item)
        self.table.setItem(row, self.COL_NAME, QTableWidgetItem(name or ""))
        status_item = QTableWidgetItem("")
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_STATUS, status_item)
        return row

    def _status_text(self, st):
        fc, sb = st['from_config'], st['seen_on_bus']
        if fc and sb:
            return "On bus + in config"
        if fc and not sb:
            return "Missing from bus" if self._scan_done else "In config"
        if not fc and sb:
            return "New (on bus)"
        return ""

    def _refresh_statuses(self):
        for r in range(self.table.rowCount()):
            rom = self.table.item(r, self.COL_ROM).text().lower()
            st = self._rom_state.get(
                rom, {'from_config': False, 'seen_on_bus': False})
            self.table.item(r, self.COL_STATUS).setText(self._status_text(st))

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def _on_scan_clicked(self):
        if self.board is None or not self.board.connected:
            QMessageBox.warning(
                self, "Not connected",
                "Connect to the board before scanning.")
            return
        self.status_label.setText("Scanning...")
        self.scan_btn.setEnabled(False)
        for st in self._rom_state.values():
            st['seen_on_bus'] = False
        if not self._signal_connected:
            self.board.message_received.connect(self._on_board_message)
            self._signal_connected = True
        try:
            self.board.send_cmd("scan")
        except Exception as e:
            self._end_scan(f"Failed to send scan: {e}")
            return
        self._scan_timer.start(self.SCAN_TIMEOUT_MS)

    def _on_scan_timeout(self):
        self._scan_done = True
        matched = sum(1 for s in self._rom_state.values()
                      if s['from_config'] and s['seen_on_bus'])
        new_count = sum(1 for s in self._rom_state.values()
                        if not s['from_config'] and s['seen_on_bus'])
        missing = sum(1 for s in self._rom_state.values()
                      if s['from_config'] and not s['seen_on_bus'])
        on_bus_total = matched + new_count
        self._refresh_statuses()
        parts = [f"Scan complete: {on_bus_total} on bus "
                 f"({matched} matched, {new_count} new)"]
        if missing:
            parts.append(
                f"{missing} config "
                f"{'entries' if missing != 1 else 'entry'} not found on bus")
        self._end_scan(". ".join(parts) + ".")

    def _end_scan(self, msg):
        self.scan_btn.setEnabled(True)
        self.status_label.setText(msg)
        if self._signal_connected and not self._capturing_config:
            try:
                self.board.message_received.disconnect(self._on_board_message)
            except Exception:
                pass
            self._signal_connected = False

    # ------------------------------------------------------------------
    # Build new config from current table state
    # ------------------------------------------------------------------

    def _collect_new_config(self):
        """Validate UI state and return the new full config dict, or None
        on validation failure (a QMessageBox is shown to the user)."""
        new_map = {}  # name -> rom
        unnamed_checked = 0
        for r in range(self.table.rowCount()):
            check_item = self.table.item(r, self.COL_CHECK)
            if check_item is None or check_item.checkState() != Qt.Checked:
                continue
            rom = self.table.item(r, self.COL_ROM).text().strip().lower()
            name_item = self.table.item(r, self.COL_NAME)
            name = name_item.text().strip() if name_item else ""
            if not rom:
                continue
            if not name:
                unnamed_checked += 1
                continue
            if name in _OW_RESERVED_KEYS:
                QMessageBox.warning(
                    self, "Reserved name",
                    f"'{name}' is a reserved key in the 1-wire-sensors "
                    "block. Choose a different name.")
                return None
            if name in new_map:
                QMessageBox.warning(
                    self, "Duplicate name",
                    f"Name '{name}' is assigned to more than one sensor.")
                return None
            new_map[name] = rom

        if unnamed_checked:
            reply = QMessageBox.question(
                self, "Unnamed sensors",
                f"{unnamed_checked} checked row(s) have no name and will be "
                "skipped. Continue?",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return None

        # Allowed sensor names = new 1-Wire names + existing thermistor names
        allowed_sensor_names = set(new_map.keys()) | set(
            self.thermistors_section.keys()
            if isinstance(self.thermistors_section, dict) else [])

        # Collect heater assignments
        new_heaters = {}
        if isinstance(self.heaters_section, dict):
            new_heaters = {
                k: (dict(v) if isinstance(v, dict) else v)
                for k, v in self.heaters_section.items()
            }
        unknown_sensors = set()
        for r in range(self.heaters_table.rowCount()):
            heater_name = self.heaters_table.item(r, self.HCOL_NAME).text()
            sensors_text = self.heaters_table.item(
                r, self.HCOL_SENSORS).text()
            sensor_list = [s.strip() for s in sensors_text.split(",")
                           if s.strip()]
            for s in sensor_list:
                if s not in allowed_sensor_names:
                    unknown_sensors.add(s)
            if heater_name in new_heaters and isinstance(
                    new_heaters[heater_name], dict):
                new_heaters[heater_name]["sensors"] = sensor_list

        if unknown_sensors:
            reply = QMessageBox.question(
                self, "Unknown sensor names",
                "The following sensor names are referenced by heaters but "
                "not defined as 1-Wire sensors or thermistors:\n\n"
                + ", ".join(sorted(unknown_sensors))
                + "\n\nContinue anyway? (The firmware will likely log a "
                "warning at boot.)",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return None

        # Rebuild the 1-wire-sensors block: preserve bus-level keys
        new_ow = {k: v for k, v in self.ow_section.items()
                  if k in _OW_RESERVED_KEYS}
        new_ow.setdefault("pin", 13)
        new_ow.setdefault("conv_mode", 4)
        new_ow.setdefault("resolution", 16)
        for name, rom in new_map.items():
            new_ow[name] = rom

        new_cfg = (dict(self.config_data)
                   if isinstance(self.config_data, dict) else {})
        new_cfg.setdefault("temperature_sensors", {})
        if isinstance(new_cfg["temperature_sensors"], dict):
            new_cfg["temperature_sensors"]["1-wire-sensors"] = new_ow
        else:
            new_cfg["temperature_sensors"] = {"1-wire-sensors": new_ow}
        new_cfg["heaters"] = new_heaters
        return new_cfg

    # ------------------------------------------------------------------
    # Save flows
    # ------------------------------------------------------------------

    def _write_local(self, new_cfg):
        try:
            with open(FIRMWARE_CONFIG_PATH, "w") as f:
                json.dump(new_cfg, f, indent=2)
                f.write("\n")
            return True
        except Exception as e:
            QMessageBox.critical(
                self, "Save failed",
                f"Could not write {FIRMWARE_CONFIG_PATH}:\n{e}")
            return False

    def _on_save_local(self):
        new_cfg = self._collect_new_config()
        if new_cfg is None:
            return
        if not self._write_local(new_cfg):
            return
        QMessageBox.information(
            self, "Saved",
            f"Wrote {FIRMWARE_CONFIG_PATH}.\n\n"
            "Re-upload the firmware (or use the Push to Board button) "
            "for the board to pick up the changes.")
        self.accept()

    def _on_save_and_push(self):
        new_cfg = self._collect_new_config()
        if new_cfg is None:
            return
        if self.board is None or not self.board.connected:
            QMessageBox.warning(
                self, "Not connected",
                "Push requires an active USB connection to the board.")
            return
        # Only support serial-mode push (mpremote talks serial). BLE
        # connections can't be reused by mpremote.
        if getattr(self.board, "connection_mode", None) != self.board.MODE_SERIAL:
            QMessageBox.warning(
                self, "USB connection required",
                "Push to board is only supported over USB serial. "
                "Switch to USB and try again.")
            return
        port = getattr(self.board, "port", None)
        if not port:
            QMessageBox.warning(
                self, "No serial port",
                "Could not determine the board's serial port. Reconnect "
                "and try again.")
            return
        if not self._write_local(new_cfg):
            return
        ok, msg = self._push_to_board(port)
        if ok:
            QMessageBox.information(self, "Pushed", msg)
            self.accept()
        else:
            QMessageBox.critical(self, "Push failed", msg)

    def _push_to_board(self, port):
        """Disconnect the UI from the board, copy config.json over via
        mpremote, reset the board, then reconnect. Returns (ok, message)."""
        mpremote = shutil.which("mpremote") or shutil.which("mpremote.exe")
        if not mpremote:
            return False, (
                "mpremote not found in PATH. Install it with "
                "`pip install mpremote` and try again.")

        # Disconnect parent UI from the board so mpremote can take the port.
        try:
            if self._parent_ui is not None and hasattr(
                    self._parent_ui, "disconnect"):
                self._parent_ui.disconnect()
            else:
                self.board.close()
        except Exception as e:
            return False, f"Failed to disconnect before push: {e}"

        # Give the OS a moment to release the port.
        QApplication.processEvents()
        time.sleep(1.0)

        cp_result = None
        reset_result = None
        try:
            cp_result = subprocess.run(
                [mpremote, "connect", port, "cp",
                 FIRMWARE_CONFIG_PATH, ":config.json"],
                capture_output=True, text=True,
                timeout=self.MPREMOTE_TIMEOUT_S,
            )
            if cp_result.returncode != 0:
                return False, (
                    f"mpremote cp failed (exit {cp_result.returncode}):\n"
                    f"{cp_result.stderr or cp_result.stdout}")
            reset_result = subprocess.run(
                [mpremote, "connect", port, "reset"],
                capture_output=True, text=True,
                timeout=self.MPREMOTE_TIMEOUT_S,
            )
            # reset always returns immediately even if board reboots;
            # ignore non-zero exit here.
        except subprocess.TimeoutExpired:
            return False, (
                f"mpremote timed out after {self.MPREMOTE_TIMEOUT_S}s. "
                "Board may need a manual reset.")
        except Exception as e:
            return False, f"mpremote invocation failed: {e}"
        finally:
            # Reconnect the parent UI regardless of push outcome so the
            # user isn't left disconnected.
            time.sleep(2.0)  # let the board reboot
            try:
                if self._parent_ui is not None and hasattr(
                        self._parent_ui, "connect_usb"):
                    self._parent_ui.connect_usb()
            except Exception:
                pass

        return True, (
            f"Pushed {FIRMWARE_CONFIG_PATH} to the board and reset it. "
            "UI is reconnecting.")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, ev):
        if self._signal_connected:
            try:
                self.board.message_received.disconnect(self._on_board_message)
            except Exception:
                pass
            self._signal_connected = False
        super().closeEvent(ev)


class HeaterControlUI(QMainWindow):
    """Main Heater Control UI Application"""

    # Emitted from a background worker thread once it has finished probing
    # each connected board for its whoami response. Routed back to the main
    # thread by Qt's signal/slot wiring.
    identify_results_signal = Signal(dict)

    def __init__(self):
        super().__init__()

        # Connection and logging
        self.board = None
        self.data_logger = DataLogger()
        self.is_logging = False
        self.config = self.load_config()

        # Most-recent §WHOAMI{} payload from the connected board. Used by
        # the connection-status label and by the "Identify" feature so the
        # currently-connected port doesn't get re-probed.
        self.board_info = {}

        # Heater selection
        self.available_heaters = {}  # {'tec': ['tec1'], 'resistive': ['heater1']}
        self.current_heater = None  # Currently selected heater name
        self.current_heater_type = None  # 'tec' or 'resistive'

        # Control state
        self.current_setpoint = DEFAULT_SETPOINT
        self.pid_enabled = False
        self.pid_active = False
        self.stream_active = False
        self.pwm_value = 0
        self.current_temperature = None
        self.compensation_rate = 1.0
        self.compensation_offset = 0.0

        # Current PID parameters
        self.current_kp = 1.0
        self.current_ki = 0.1
        self.current_kd = 0.0

        # Temperature profile variables
        self.profile_active = False
        self.current_profile_step = 0
        self.current_execution_index = 0
        self.execution_sequence = []
        self.profile_steps = []
        self.last_timestamp = 0
        self.pre_profile_stream_state = False

        # Calibration data structures
        self.calibration_data = {
            'timestamps': [],
            'temperatures': [],
            'pwm_values': [],
            'setpoints': []
        }
        self.calibration_active = False
        self.calibration_method = None
        self.calibration_results = None
        self.oscillation_stats = None
        self.pre_calibration_stream_state = False

        # Calibration monitoring
        self.kp_test_data = {}  # Store data for each Kp test
        self.oscillation_detected = False
        self.critical_gain = None
        self.critical_period = None
        self.test_phase = None  # 'testing', 'cooling', 'analyzing'
        self.zn_calibration_params = {}

        self.init_ui()
        self.setup_connection()

        # Initialize PID parameter display
        self.update_pid_display()

    def load_config(self):
        """Load the configuration from the config.yml file"""
        try:
            with open("config.yml", "r") as ymlfile:
                cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)
        except OSError:
            cfg = {
                    "heater_control": {
                        "compensation_rate": DEFAULT_COMPENSATION_RATE,
                        "compensation_offset": DEFAULT_COMPENSATION_OFFSET
                        },
                    "serial": {
                        "baudrate": DEFAULT_BAUDRATE,
                        "pid": DEFAULT_PID,
                        "vid": DEFAULT_VID
                        },
                    "zmq": {
                        "port": DEFAULT_ZMQ_PORT
                        }
                    }
        return cfg

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Heater Control System v1.0")
        self.setGeometry(100, 100, MAX_WINDOW_HEIGHT, 800)

        self._build_menu_bar()

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(0)  # Small spacing between panels
        main_layout.setContentsMargins(0, 0, 0, 0)  # Small margins around edges

        # Left panel - Controls and Calibration
        left_panel = self.create_control_panel()
        left_panel.setMaximumWidth(350)
        left_panel.setMaximumHeight(MAX_WINDOW_HEIGHT)
        main_layout.addWidget(left_panel, 0, Qt.AlignTop)

        # Central panel - Plot and status
        central_panel = self.create_plot_panel()
        central_panel.setMinimumWidth(580)
        central_panel.setMaximumHeight(MAX_WINDOW_HEIGHT)
        main_layout.addWidget(central_panel, 0, Qt.AlignTop)

        # Right panel - Calibration
        right_panel = self.create_calibration_panel()
        right_panel.setMaximumWidth(400)
        right_panel.setMaximumHeight(MAX_WINDOW_HEIGHT)
        main_layout.addWidget(right_panel, 0, Qt.AlignTop)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Disconnected")

        # Populate ports on startup
        self.refresh_serial_ports()
        
        # Apply compensation settings
        self.on_compensation_changed()
        
        # Apply system-aware styling
        self.apply_system_theme()

    def apply_system_theme(self):
        """Apply system-aware theme that adapts to light/dark mode"""
        # Get system palette
        palette = QApplication.palette()
        # Check if system is in dark mode
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128

        if is_dark_mode:
            # Dark theme
            self.setStyleSheet("""
                    QMainWindow {
                        background-color: #2b2b2b;
                        color: #ffffff;
                    }
                    QGroupBox {
                        font-weight: bold;
                        border: 2px solid #555555;
                        border-radius: 5px;
                        margin-top: 1ex;
                        padding-top: 10px;
                        color: #ffffff;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px 0 5px;
                        color: #ffffff;
                    }
                    QPushButton {
                        background-color: #404040;
                        border: 1px solid #555555;
                        border-radius: 3px;
                        padding: 5px;
                        min-width: 80px;
                        color: #ffffff;
                    }
                    QPushButton:hover {
                        background-color: #505050;
                    }
                    QPushButton:pressed {
                        background-color: #606060;
                    }
                    QPushButton:disabled {
                        background-color: #2b2b2b;
                        color: #666666;
                    }
                    QSpinBox, QDoubleSpinBox {
                        background-color: #404040;
                        border: 1px solid #555555;
                        border-radius: 3px;
                        padding: 3px;
                        color: #ffffff;
                    }
                    QCheckBox {
                        spacing: 5px;
                        color: #ffffff;
                    }
                    QCheckBox::indicator {
                        width: 18px;
                        height: 18px;
                    }
                    QCheckBox::indicator:unchecked {
                        border: 2px solid #555555;
                        background-color: #404040;
                        border-radius: 3px;
                    }
                    QCheckBox::indicator:checked {
                        border: 2px solid #4CAF50;
                        background-color: #4CAF50;
                        border-radius: 3px;
                    }
                    QTextEdit {
                        background-color: #1e1e1e;
                        border: 1px solid #555555;
                        border-radius: 3px;
                        color: #ffffff;
                    }
                    QStatusBar {
                        background-color: #404040;
                        border-top: 1px solid #555555;
                        color: #ffffff;
                    }
                QLabel {
                    color: #ffffff;
                }
            """)
        else:
            # Light theme
            self.setStyleSheet("""
                    QMainWindow {
                        background-color: #ffffff;
                        color: #000000;
                    }
                    QGroupBox {
                        font-weight: bold;
                        border: 2px solid #cccccc;
                        border-radius: 5px;
                        margin-top: 1ex;
                        padding-top: 10px;
                        color: #000000;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px 0 5px;
                        color: #000000;
                    }
                    QPushButton {
                        background-color: #f0f0f0;
                        border: 1px solid #cccccc;
                        border-radius: 3px;
                        padding: 5px;
                        min-width: 80px;
                        color: #000000;
                    }
                    QPushButton:hover {
                        background-color: #e0e0e0;
                    }
                    QPushButton:pressed {
                        background-color: #d0d0d0;
                    }
                    QPushButton:disabled {
                        background-color: #f5f5f5;
                        color: #999999;
                    }
                    QSpinBox, QDoubleSpinBox {
                        background-color: #ffffff;
                        border: 1px solid #cccccc;
                        border-radius: 3px;
                        padding: 3px;
                        color: #000000;
                    }
                    QCheckBox {
                        spacing: 5px;
                        color: #000000;
                    }
                    QCheckBox::indicator {
                        width: 18px;
                        height: 18px;
                    }
                    QCheckBox::indicator:unchecked {
                        border: 2px solid #cccccc;
                        background-color: #ffffff;
                        border-radius: 3px;
                    }
                    QCheckBox::indicator:checked {
                        border: 2px solid #4CAF50;
                        background-color: #4CAF50;
                        border-radius: 3px;
                    }
                    QTextEdit {
                        background-color: #ffffff;
                        border: 1px solid #cccccc;
                        border-radius: 3px;
                        color: #000000;
                    }
                    QStatusBar {
                        background-color: #f0f0f0;
                        border-top: 1px solid #cccccc;
                        color: #000000;
                    }
                QLabel {
                    color: #000000;
                }
            """)

    def create_control_panel(self):
        """Create the control panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Connection group
        conn_group = QGroupBox("Connection")
        conn_layout = QVBoxLayout(conn_group)

        self.connect_btn = QPushButton("Connect USB")
        self.connect_btn.clicked.connect(self.connect_usb)
        self.connect_btn.setToolTip("Connect to heater controller via USB (Ctrl+C)")
        self.connect_btn.setShortcut("Ctrl+C")
        conn_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.disconnect)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setToolTip("Disconnect from heater controller (Ctrl+D)")
        self.disconnect_btn.setShortcut("Ctrl+D")
        conn_layout.addWidget(self.disconnect_btn)

        # Serial port selection
        port_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setToolTip("Select serial port to connect to")
        port_layout.addWidget(self.port_combo)

        self.refresh_ports_btn = QPushButton("Refresh")
        self.refresh_ports_btn.clicked.connect(self.refresh_serial_ports)
        self.refresh_ports_btn.setToolTip("Refresh available serial ports")
        port_layout.addWidget(self.refresh_ports_btn)

        self.identify_ports_btn = QPushButton("Identify")
        self.identify_ports_btn.clicked.connect(self.identify_boards)
        self.identify_ports_btn.setToolTip(
            "Probe every matching port for its whoami response and label\n"
            "the dropdown with device_id / UID so multiple Picos can be told\n"
            "apart.")
        port_layout.addWidget(self.identify_ports_btn)

        conn_layout.addLayout(port_layout)

        self.connection_status = QLabel("Disconnected")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        self.connection_status.setToolTip("Connection status indicator")
        conn_layout.addWidget(self.connection_status)

        self.board_id_label = QLabel("Board: -")
        self.board_id_label.setToolTip(
            "Identity of the connected board (device_id + hardware UID).\n"
            "Set device_id under the top-level key in firmware/config.json.")
        conn_layout.addWidget(self.board_id_label)

        layout.addWidget(conn_group)

        # Heater Control group
        heater_group = QGroupBox("Heater Control")
        heater_layout = QGridLayout(heater_group)

        # Heater selection
        heater_layout.addWidget(QLabel("Heater:"), 0, 0)
        self.heater_combo_selection = QComboBox()
        self.heater_combo_selection.currentTextChanged.connect(self.on_heater_changed)
        self.heater_combo_selection.setEnabled(False)
        self.heater_combo_selection.setToolTip("Select which heater to control")
        heater_layout.addWidget(self.heater_combo_selection, 0, 1)

        # Sensor group selection
        heater_layout.addWidget(QLabel("Sensor Group:"), 1, 0)
        self.sensor_group_combo = QComboBox()
        self.sensor_group_combo.addItems(["thermistors", "onewire", "all", "None"])
        self.sensor_group_combo.setCurrentText("thermistors")
        self.sensor_group_combo.currentTextChanged.connect(self.on_sensor_group_changed)
        self.sensor_group_combo.setToolTip("Select which sensor group to monitor/use for PID control")
        heater_layout.addWidget(self.sensor_group_combo, 1, 1)

        # Setpoint control
        heater_layout.addWidget(QLabel("Setpoint (°C):"), 2, 0)
        self.setpoint_spin = QDoubleSpinBox()
        self.setpoint_spin.setRange(-10, 140)
        self.setpoint_spin.setValue(DEFAULT_SETPOINT)
        self.setpoint_spin.setDecimals(1)
        self.setpoint_spin.setKeyboardTracking(False)
        self.setpoint_spin.valueChanged.connect(self.on_setpoint_changed)
        self.setpoint_spin.setToolTip("Target temperature for PID control")
        heater_layout.addWidget(self.setpoint_spin, 2, 1)

        # Compensation control
        heater_layout.addWidget(QLabel("Compensation Rate:"), 3, 0)
        self.compensation_rate_spin = QDoubleSpinBox()
        self.compensation_rate_spin.setRange(-10, 10)
        self.compensation_rate_spin.setValue(self.config['heater_control']['compensation_rate'])
        self.compensation_rate_spin.setDecimals(2)
        self.compensation_rate_spin.setSingleStep(0.01)
        self.compensation_rate_spin.valueChanged.connect(self.on_compensation_changed)
        heater_layout.addWidget(self.compensation_rate_spin, 3, 1)
        
        heater_layout.addWidget(QLabel("Compensation Offset (°C):"), 4, 0)
        self.compensation_offset_spin = QDoubleSpinBox()
        self.compensation_offset_spin.setRange(-100, 100)
        self.compensation_offset_spin.setValue(self.config['heater_control']['compensation_offset'])
        self.compensation_offset_spin.setDecimals(2)
        self.compensation_offset_spin.setSingleStep(0.01)
        self.compensation_offset_spin.valueChanged.connect(self.on_compensation_changed)
        heater_layout.addWidget(self.compensation_offset_spin, 4, 1)
        
        # Stream control toggle button
        self.stream_toggle_btn = QPushButton("Start Stream")
        self.stream_toggle_btn.setCheckable(True)
        self.stream_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.stream_toggle_btn.clicked.connect(self.toggle_stream)
        self.stream_toggle_btn.setToolTip("Start/stop temperature streaming and control (Ctrl+S)")
        self.stream_toggle_btn.setShortcut("Ctrl+S")
        heater_layout.addWidget(self.stream_toggle_btn, 5, 0)

        # PID control
        self.pid_toggle_btn = QCheckBox("PID Control")
        self.pid_toggle_btn.setChecked(False)
        self.pid_toggle_btn.clicked.connect(self.on_pid_toggled)
        self.pid_toggle_btn.setToolTip("Enable PID temperature control mode (unchecked = stream only)")
        heater_layout.addWidget(self.pid_toggle_btn, 5, 1)

        # Manual PWM control (TEC1 & TEC2 are dependent)
        heater_layout.addWidget(QLabel("Manual PWM (%):"), 6, 0)
        self.pwm_spin = QSpinBox()
        self.pwm_spin.setRange(-100, 100)
        self.pwm_spin.setValue(0)
        heater_layout.addWidget(self.pwm_spin, 6, 1)

        self.pwm_apply_btn = QPushButton("Apply PWM")
        self.pwm_apply_btn.clicked.connect(self.apply_manual_pwm)
        self.pwm_apply_btn.setToolTip("Apply manual PWM value to heater (bypass PID control)")
        heater_layout.addWidget(self.pwm_apply_btn, 7, 0, 1, 2)

        layout.addWidget(heater_group)

        # Fan Control group
        fan_group = QGroupBox("Fan Control")
        fan_layout = QVBoxLayout(fan_group)

        self.fan_on_btn = QPushButton("Fan ON")
        self.fan_on_btn.clicked.connect(self.fan_on)
        self.fan_on_btn.setStyleSheet("QPushButton { background-color: #2196F3; }")
        self.fan_on_btn.setToolTip("Turn cooling fan on")
        fan_layout.addWidget(self.fan_on_btn)

        self.fan_off_btn = QPushButton("Fan OFF")
        self.fan_off_btn.clicked.connect(self.fan_off)
        self.fan_off_btn.setStyleSheet("QPushButton { background-color: #FF9800; }")
        self.fan_off_btn.setToolTip("Turn cooling fan off")
        fan_layout.addWidget(self.fan_off_btn)

        layout.addWidget(fan_group)

        # Data Logging group
        log_group = QGroupBox("Data Logging")
        log_layout = QVBoxLayout(log_group)

        self.logging_checkbox = QCheckBox("Enable Logging")
        self.logging_checkbox.toggled.connect(self.on_logging_toggled)
        self.logging_checkbox.setToolTip("Log all temperature and control data to JSON file")
        log_layout.addWidget(self.logging_checkbox)

        self.log_folder_btn = QPushButton("Open Log Folder")
        self.log_folder_btn.clicked.connect(self.open_log_folder)
        self.log_folder_btn.setToolTip("Open folder containing log files")
        log_layout.addWidget(self.log_folder_btn)

        layout.addWidget(log_group)

        # Status display
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)

        # Scrollable area for dynamic sensor labels
        self.sensor_labels_widget = QWidget()
        self.sensor_labels_layout = QVBoxLayout(self.sensor_labels_widget)
        self.sensor_labels_layout.setContentsMargins(0, 0, 0, 0)

        sensor_scroll_area = QScrollArea()
        sensor_scroll_area.setWidget(self.sensor_labels_widget)
        sensor_scroll_area.setWidgetResizable(True)
        sensor_scroll_area.setMinimumHeight(160)
        sensor_scroll_area.setMaximumHeight(250)
        sensor_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sensor_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        status_layout.addWidget(QLabel("Temperature Sensors:"))
        status_layout.addWidget(sensor_scroll_area)

        # Dictionary to store dynamic sensor labels
        self.sensor_labels = {}

        # Fixed status labels
        self.pid_temp_status_label = QLabel("PID Temp: --°C")
        self.heater1_pwm_label = QLabel("Heater PWM: --%")
        self.heater2_pwm_label = QLabel("Heater2 PWM: --%")
        self.current_label = QLabel("Current: --A")
        self.fan_status_label = QLabel("Fan: OFF")

        status_layout.addWidget(self.pid_temp_status_label)
        status_layout.addWidget(self.heater1_pwm_label)
        status_layout.addWidget(self.heater2_pwm_label)
        status_layout.addWidget(self.current_label)
        status_layout.addWidget(self.fan_status_label)

        layout.addWidget(status_group)

        # Add stretch to fill remaining vertical space
        layout.addStretch()

        return panel

    def create_plot_panel(self):
        """Create the plotting panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Plots group - contains plot and controls
        plot_group = QGroupBox("Stream")
        plot_layout = QVBoxLayout(plot_group)

        # Plot widget
        self.plot_widget = RealTimePlot(plot_group, width=8, height=6)
        plot_layout.addWidget(self.plot_widget)

        # Plot control buttons
        plot_control_layout = QHBoxLayout()

        self.clear_plot_btn = QPushButton("Clear Plot")
        self.clear_plot_btn.clicked.connect(self.clear_plot)
        self.clear_plot_btn.setStyleSheet("QPushButton { background-color: #FF9800; }")
        self.clear_plot_btn.setToolTip("Clear all plot data (Ctrl+L)")
        self.clear_plot_btn.setShortcut("Ctrl+L")
        plot_control_layout.addWidget(self.clear_plot_btn)

        plot_control_layout.addStretch()  # Push button to the left
        plot_layout.addLayout(plot_control_layout)

        # Add plot group to main layout
        plot_group.setMaximumHeight(500)
        layout.addWidget(plot_group, 3)  # Stretch factor 3 for more space

        # Temperature Profile group
        profile_group = QGroupBox("Temperature Profile")
        profile_layout = QVBoxLayout(profile_group)

        # Profile steps container with scrollable area
        self.profile_steps_container = QWidget()
        self.profile_steps_layout = QVBoxLayout(self.profile_steps_container)

        # Create scrollable area for steps
        self.profile_scroll_area = QScrollArea()
        self.profile_scroll_area.setWidget(self.profile_steps_container)
        self.profile_scroll_area.setWidgetResizable(True)
        self.profile_scroll_area.setMinimumHeight(150)
        self.profile_scroll_area.setMaximumHeight(200)  # Show ~3 steps initially
        self.profile_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.profile_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        # Add header labels with proper alignment
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Fixed width labels to align with spinboxes
        step_header = QLabel("Step")
        step_header.setFixedWidth(60)
        step_header.setStyleSheet("font-weight: bold;")
        temp_header = QLabel("Temp")
        temp_header.setFixedWidth(85)
        temp_header.setStyleSheet("font-weight: bold;")
        hold_header = QLabel("Hold")
        hold_header.setFixedWidth(80)
        hold_header.setStyleSheet("font-weight: bold;")
        tol_header = QLabel("Tolerance")
        tol_header.setFixedWidth(85)
        tol_header.setStyleSheet("font-weight: bold;")
        bundle_header = QLabel("Bundle")
        bundle_header.setFixedWidth(60)
        bundle_header.setStyleSheet("font-weight: bold;")
        repeats_header = QLabel("Repeats")
        repeats_header.setFixedWidth(65)
        repeats_header.setStyleSheet("font-weight: bold;")

        header_layout.addWidget(step_header)
        header_layout.addWidget(temp_header)
        header_layout.addWidget(hold_header)
        header_layout.addWidget(tol_header)
        header_layout.addWidget(bundle_header)
        header_layout.addWidget(repeats_header)
        header_layout.addStretch()

        # self.profile_steps_layout.addWidget(header_widget)
        profile_layout.addWidget(header_widget)

        profile_layout.addWidget(self.profile_scroll_area)

        # Add initial step
        self.add_profile_step()

        # Add/Remove step buttons
        step_buttons_layout = QHBoxLayout()

        self.add_step_btn = QPushButton("Add Step")
        self.add_step_btn.clicked.connect(self.add_profile_step)
        self.add_step_btn.setStyleSheet("QPushButton { background-color: #4CAF50; }")
        step_buttons_layout.addWidget(self.add_step_btn)

        self.remove_step_btn = QPushButton("Remove Step")
        self.remove_step_btn.clicked.connect(self.remove_profile_step)
        self.remove_step_btn.setStyleSheet("QPushButton { background-color: #f44336; }")
        step_buttons_layout.addWidget(self.remove_step_btn)

        # Save/Load profile buttons
        profile_io_layout = QHBoxLayout()

        self.save_profile_btn = QPushButton("Save Profile")
        self.save_profile_btn.clicked.connect(self.save_profile)
        self.save_profile_btn.setStyleSheet("QPushButton { background-color: #9C27B0; }")
        self.save_profile_btn.setToolTip("Save current profile to JSON file")
        profile_io_layout.addWidget(self.save_profile_btn)

        self.load_profile_btn = QPushButton("Load Profile")
        self.load_profile_btn.clicked.connect(self.load_profile)
        self.load_profile_btn.setStyleSheet("QPushButton { background-color: #607D8B; }")
        self.load_profile_btn.setToolTip("Load profile from JSON file")
        profile_io_layout.addWidget(self.load_profile_btn)

        profile_layout.addLayout(profile_io_layout)

        # profile_layout.addLayout(step_buttons_layout)

        # Profile control buttons
        # profile_control_layout = QHBoxLayout()

        self.start_profile_btn = QPushButton("Start Profile")
        self.start_profile_btn.clicked.connect(self.start_temperature_profile)
        self.start_profile_btn.setStyleSheet("QPushButton { background-color: #2196F3; }")
        # profile_control_layout.addWidget(self.start_profile_btn)
        step_buttons_layout.addWidget(self.start_profile_btn)


        self.stop_profile_btn = QPushButton("Stop Profile")
        self.stop_profile_btn.clicked.connect(self.stop_temperature_profile)
        self.stop_profile_btn.setStyleSheet("QPushButton { background-color: #FF9800; }")
        self.stop_profile_btn.setEnabled(False)
        # profile_control_layout.addWidget(self.stop_profile_btn)
        step_buttons_layout.addWidget(self.stop_profile_btn)

        # Skip current step while the profile is running. Useful if a step's
        # tolerance/hold criterion ends up unreachable so the profile would
        # otherwise stall.
        self.skip_step_btn = QPushButton("Skip Step")
        self.skip_step_btn.clicked.connect(self.skip_current_profile_step)
        self.skip_step_btn.setStyleSheet("QPushButton { background-color: #9C27B0; }")
        self.skip_step_btn.setEnabled(False)
        self.skip_step_btn.setToolTip(
            "Skip the current profile step while running, without stopping\n"
            "the profile. The next execution item starts immediately.")
        step_buttons_layout.addWidget(self.skip_step_btn)

        # profile_layout.addLayout(profile_control_layout)
        profile_layout.addLayout(step_buttons_layout)

        # Profile status
        self.profile_status_label = QLabel("Profile: Ready")
        self.profile_status_label.setStyleSheet("color: green; font-weight: bold;")
        profile_layout.addWidget(self.profile_status_label)

        # Current step display
        self.current_step_label = QLabel("Current Step: --")
        self.current_step_label.setStyleSheet("color: blue; font-weight: bold;")
        profile_layout.addWidget(self.current_step_label)

        # Add profile group to main layout
        layout.addWidget(profile_group)

        # Log display
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout(log_group)

        self.log_display = QTextEdit()
        self.log_display.setMaximumHeight(150)
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)

        # Add log group to main layout
        layout.addWidget(log_group)

        return panel

    def create_calibration_panel(self):
        """Create the calibration panel"""
        # Right side - Calibration panel
        calib_widget = QWidget()
        calib_layout = QVBoxLayout(calib_widget)

        # PID Calibration group
        calib_group = QGroupBox("PID Calibration")
        calib_group_layout = QVBoxLayout(calib_group)

        # Ziegler-Nichols calibration
        zn_group = QGroupBox("Ziegler-Nichols Method")
        zn_layout = QGridLayout(zn_group)

        zn_layout.addWidget(QLabel("Target Temp (°C):"), 0, 0)
        self.zn_temp_spin = QDoubleSpinBox()
        self.zn_temp_spin.setRange(20, 120)
        self.zn_temp_spin.setValue(40.0)
        self.zn_temp_spin.setDecimals(1)
        zn_layout.addWidget(self.zn_temp_spin, 0, 1)

        zn_layout.addWidget(QLabel("Min Kp:"), 1, 0)
        self.zn_min_kp_spin = QSpinBox()
        self.zn_min_kp_spin.setRange(0, 200)
        self.zn_min_kp_spin.setValue(5)
        zn_layout.addWidget(self.zn_min_kp_spin, 1, 1)

        zn_layout.addWidget(QLabel("Max Kp:"), 2, 0)
        self.zn_max_kp_spin = QSpinBox()
        self.zn_max_kp_spin.setRange(10, 200)
        self.zn_max_kp_spin.setValue(100)
        zn_layout.addWidget(self.zn_max_kp_spin, 2, 1)

        zn_layout.addWidget(QLabel("Kp Step:"), 3, 0)
        self.zn_kp_step_spin = QSpinBox()
        self.zn_kp_step_spin.setRange(1, 20)
        self.zn_kp_step_spin.setValue(5)
        zn_layout.addWidget(self.zn_kp_step_spin, 3, 1) 

        zn_layout.addWidget(QLabel("Duration (s):"), 4, 0)
        self.zn_kp_duration_spin = QSpinBox()
        self.zn_kp_duration_spin.setRange(1, 600)
        self.zn_kp_duration_spin.setValue(60)
        zn_layout.addWidget(self.zn_kp_duration_spin, 4, 1)

        zn_layout.addWidget(QLabel("Cool Down Duration (s):"), 5, 0)
        self.zn_cool_down_duration_spin = QSpinBox()
        self.zn_cool_down_duration_spin.setRange(1, 600)
        self.zn_cool_down_duration_spin.setValue(30)
        zn_layout.addWidget(self.zn_cool_down_duration_spin, 5, 1)

        self.zn_start_btn = QPushButton("Start ZN Calibration")
        self.zn_start_btn.clicked.connect(self.start_ziegler_nichols_calibration)
        self.zn_start_btn.setStyleSheet("QPushButton { background-color: #4CAF50; }")
        zn_layout.addWidget(self.zn_start_btn, 6, 0, 1, 2)

        calib_group_layout.addWidget(zn_group)

        # Open-loop calibration
        ol_group = QGroupBox("Open-Loop Method")
        ol_layout = QGridLayout(ol_group)

        ol_layout.addWidget(QLabel("PWM Step (%):"), 0, 0)
        self.ol_pwm_spin = QSpinBox()
        self.ol_pwm_spin.setRange(10, 80)
        self.ol_pwm_spin.setValue(30)
        ol_layout.addWidget(self.ol_pwm_spin, 0, 1)

        ol_layout.addWidget(QLabel("Duration (s):"), 1, 0)
        self.ol_duration_spin = QSpinBox()
        self.ol_duration_spin.setRange(30, 300)
        self.ol_duration_spin.setValue(60)
        ol_layout.addWidget(self.ol_duration_spin, 1, 1)

        ol_layout.addWidget(QLabel("Repetitions:"), 2, 0)
        self.ol_repetitions_spin = QSpinBox()
        self.ol_repetitions_spin.setRange(1, 5)
        self.ol_repetitions_spin.setValue(3)
        ol_layout.addWidget(self.ol_repetitions_spin, 2, 1)

        self.ol_start_btn = QPushButton("Start Open-Loop Calibration")
        self.ol_start_btn.clicked.connect(self.start_open_loop_calibration)
        self.ol_start_btn.setStyleSheet("QPushButton { background-color: #2196F3; }")
        ol_layout.addWidget(self.ol_start_btn, 3, 0, 1, 2)

        calib_group_layout.addWidget(ol_group)

        # Calibration control
        calib_control_layout = QHBoxLayout()

        self.calib_stop_btn = QPushButton("Stop Calibration")
        self.calib_stop_btn.clicked.connect(self.stop_calibration)
        self.calib_stop_btn.setStyleSheet("QPushButton { background-color: #f44336; }")
        self.calib_stop_btn.setEnabled(False)
        calib_control_layout.addWidget(self.calib_stop_btn)

        self.calib_apply_btn = QPushButton("Apply Results")
        self.calib_apply_btn.clicked.connect(self.apply_calibration_results)
        self.calib_apply_btn.setStyleSheet("QPushButton { background-color: #FF9800; }")
        self.calib_apply_btn.setEnabled(False)
        calib_control_layout.addWidget(self.calib_apply_btn)

        calib_group_layout.addLayout(calib_control_layout)

        # Calibration status
        self.calib_status_label = QLabel("Calibration: Ready")
        self.calib_status_label.setStyleSheet("color: green; font-weight: bold;")
        calib_group_layout.addWidget(self.calib_status_label)

        # Current Kp display
        self.current_kp_label = QLabel("Current Kp: --")
        self.current_kp_label.setStyleSheet("color: blue; font-weight: bold;")
        calib_group_layout.addWidget(self.current_kp_label)

        # Calibration results display
        self.calib_results_text = QTextEdit()
        self.calib_results_text.setMaximumHeight(85)
        self.calib_results_text.setReadOnly(True)
        self.calib_results_text.setPlaceholderText("Calibration results will appear here...")
        calib_group_layout.addWidget(self.calib_results_text)

        # PID Parameters group (moved from main control panel)
        pid_group = QGroupBox("PID Parameters")
        pid_layout = QGridLayout(pid_group)

        # Kp parameter
        pid_layout.addWidget(QLabel("Kp (Proportional):"), 0, 0)
        self.kp_spin = QDoubleSpinBox()
        self.kp_spin.setRange(0, 1000)
        self.kp_spin.setValue(1.0)
        self.kp_spin.setDecimals(4)
        self.kp_spin.setSingleStep(0.1)
        pid_layout.addWidget(self.kp_spin, 0, 1)

        # Ki parameter
        pid_layout.addWidget(QLabel("Ki (Integral):"), 1, 0)
        self.ki_spin = QDoubleSpinBox()
        self.ki_spin.setRange(0, 1000)
        self.ki_spin.setValue(0.1)
        self.ki_spin.setDecimals(4)
        self.ki_spin.setSingleStep(0.01)
        pid_layout.addWidget(self.ki_spin, 1, 1)

        # Kd parameter
        pid_layout.addWidget(QLabel("Kd (Derivative):"), 2, 0)
        self.kd_spin = QDoubleSpinBox()
        self.kd_spin.setRange(0, 1000)
        self.kd_spin.setValue(0.0)
        self.kd_spin.setDecimals(4)
        self.kd_spin.setSingleStep(0.01)
        pid_layout.addWidget(self.kd_spin, 2, 1)

        # Apply PID parameters button
        self.apply_pid_btn = QPushButton("Apply PID Parameters")
        self.apply_pid_btn.clicked.connect(self.apply_pid_parameters)
        self.apply_pid_btn.setStyleSheet("QPushButton { background-color: #9C27B0; }")
        self.apply_pid_btn.setToolTip(
            "Send the kp/ki/kd values above to the board (in-memory only).")
        pid_layout.addWidget(self.apply_pid_btn, 3, 0, 1, 2)

        # Persist current PID tunings to the board's flash so they survive
        # a power cycle. Calls the firmware's save_pid_<heater> command.
        self.save_pid_btn = QPushButton("Save PID to Board")
        self.save_pid_btn.clicked.connect(self.save_pid_to_board)
        self.save_pid_btn.setStyleSheet("QPushButton { background-color: #00897B; }")
        self.save_pid_btn.setToolTip(
            "Write the current PID tunings on the board back to config.json\n"
            "on the Pico's filesystem so they persist across reboots.")
        pid_layout.addWidget(self.save_pid_btn, 4, 0, 1, 2)

        # Refresh PID values button
        self.refresh_pid_btn = QPushButton("Refresh from Board")
        self.refresh_pid_btn.clicked.connect(self.query_pid_values)
        self.refresh_pid_btn.setStyleSheet("QPushButton { background-color: #607D8B; }")
        pid_layout.addWidget(self.refresh_pid_btn, 5, 0, 1, 2)

        # PID Enable/Disable buttons
        pid_enable_layout = QHBoxLayout()

        self.pid_enable_btn = QPushButton("Enable PID")
        self.pid_enable_btn.clicked.connect(self.enable_pid)
        self.pid_enable_btn.setStyleSheet("QPushButton { background-color: #4CAF50; }")
        pid_enable_layout.addWidget(self.pid_enable_btn)

        self.pid_disable_btn = QPushButton("Disable PID")
        self.pid_disable_btn.clicked.connect(self.disable_pid)
        self.pid_disable_btn.setStyleSheet("QPushButton { background-color: #f44336; }")
        pid_enable_layout.addWidget(self.pid_disable_btn)

        pid_layout.addLayout(pid_enable_layout, 6, 0, 1, 2)

        # Current PID display
        self.current_pid_label = QLabel("Current PID: Kp=--, Ki=--, Kd=--")
        self.current_pid_label.setStyleSheet("color: blue; font-weight: bold;")
        pid_layout.addWidget(self.current_pid_label, 7, 0, 1, 2)

        calib_group_layout.addWidget(pid_group)

        calib_layout.addWidget(calib_group)

        # Add stretch to fill remaining vertical space
        calib_layout.addStretch()

        return calib_widget

    def setup_connection(self):
        """Setup the board connection"""
        try:
            # Set up logger for command logging
            board_logger = logging.getLogger(__name__)
            board_logger.setLevel(logging.DEBUG)

            self.board = Board(
                addr="auto",
                baudrate=115200,
                connection_mode=Board.MODE_SERIAL,
                logger=board_logger
            )

            # Connect signals
            self.board.connection_changed.connect(self.on_connection_changed)
            self.board.telemetry.connect(self.on_telemetry_received)
            self.board.status_message.connect(self.on_status_message)
            self.board.message_received.connect(self.on_message_received)

            # Identify-boards background worker reports back through this
            # signal so the UI update happens on the main thread.
            self.identify_results_signal.connect(self._on_identify_results)

        except Exception as e:
            self.log_message(f"Error setting up connection: {e}")

    ############################
    # Calibrations
    ############################
    def monitor_calibration_messages(self, message):
        """Monitor serial messages during Ziegler-Nichols calibration"""
        try:
            if message.lower().startswith("testing kp = "):
                self.current_kp = float(message.split("=")[-1].strip())
                self.test_phase = "testing"
                self.log_message(f"Testing Kp = {self.current_kp}")
                if self.current_kp is not None:
                    self.current_kp_label.setText(f"Testing Kp: {self.current_kp:.1f}")
                    self.current_kp_label.setStyleSheet(
                        "color: orange; font-weight: bold;"
                    )
                if self.current_kp not in self.kp_test_data:
                    self.kp_test_data[self.current_kp] = {
                        'timestamps': [],
                        'temperatures': [],
                        'pwm_values': []
                    }

            elif message.lower().startswith("temperature reached target"):
                self.test_phase = "collecting"
                self.log_message("Temperature reached target - starting data collection")

            elif message.lower().startswith("cooling down for "):
                self.test_phase = "cooling"
                self.log_message("Cooling down - stopping data collection")
                self.analyze_kp_test_data(self.current_kp)

        except Exception as e:
            self.log_message(f"Error monitoring calibration messages: {e}")

    @Slot()
    def start_ziegler_nichols_calibration(self):
        self.oscillation_stats = None
        self.calibration_results = None
        """Start Ziegler-Nichols calibration"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        # Stop thermistor streaming
        self.send_cmd_with_log("stream_stop")
        sleep(COMMAND_DELAY_LONG)
        self.clear_plot()

        # Store previous stream state to resume after calibration
        self.pre_calibration_stream_state = self.stream_active

        if self.calibration_active:
            self.log_message("Calibration already in progress!")
            return

        try:
            target_temp = self.zn_temp_spin.value()
            min_kp = self.zn_min_kp_spin.value()
            max_kp = self.zn_max_kp_spin.value()
            kp_step = self.zn_kp_step_spin.value()
            duration = self.zn_kp_duration_spin.value()
            cool_down_duration = self.zn_cool_down_duration_spin.value()

            # Clear previous calibration data
            self.calibration_data = {
                'timestamps': [],
                'temperatures': [],
                'pwm_values': [],
                'setpoints': []
            }

            # Reset monitoring variables
            self.current_kp = min_kp  # Start with the first Kp value
            self.kp_test_data = {}
            self.oscillation_detected = False
            self.critical_gain = None
            self.critical_period = None
            self.test_phase = None

            # Start calibration
            self.calibration_active = True
            self.calibration_method = "ziegler_nichols"

            # Update UI
            self.calib_status_label.setText("Calibration: Running ZN Method")
            self.calib_status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.current_kp_label.setText("Current Kp: --")
            self.current_kp_label.setStyleSheet("color: blue; font-weight: bold;")
            self.calib_stop_btn.setEnabled(True)
            self.zn_start_btn.setEnabled(False)
            self.ol_start_btn.setEnabled(False)

            # Start ZN calibration with available commands
            self.log_message("Starting Ziegler-Nichols calibration...")
            self.log_message(f"Target: {target_temp}°C, Min Kp: {min_kp}, Max Kp: {max_kp}, Step: {kp_step}")
            self.log_message(f"Duration: {duration}s, Cool Down: {cool_down_duration}s")

            # Set temperature update frequency to 0.2 seconds
            self.send_cmd_with_log("update_freq_temp_0.2")

            # Start PID control with initial Kp
            sensor_group = self.sensor_group_combo.currentText()
            if sensor_group == "None":
                cmd = self.get_heater_cmd(f"pid_{{heater}}_{target_temp}")
            else:
                cmd = self.get_heater_cmd(f"pid_{{heater}}_{target_temp}_{sensor_group}")
            self.send_cmd_with_log(cmd)

            # Start calibration cycle
            self.start_zn_calibration_cycle(min_kp, max_kp, kp_step, duration, cool_down_duration, target_temp)

        except Exception as e:
            self.log_message(f"Error starting ZN calibration: {e}")
            self.calibration_active = False

    def start_zn_calibration_cycle(self, min_kp, max_kp, kp_step, duration, cool_down_duration, target_temp):
        """Start the ZN calibration cycle with PID enable/disable"""
        self.zn_calibration_params = {
            'min_kp': min_kp,
            'max_kp': max_kp,
            'kp_step': kp_step,
            'duration': duration,
            'cool_down_duration': cool_down_duration,
            'target_temp': target_temp,
            'current_kp': min_kp,
            'phase': 'testing',  # 'testing' or 'cooldown'
            'phase_start_time': time.time(),
            'test_data': []
        }

        # Start with first Kp value
        self.update_kp_and_start_test(self.zn_calibration_params['current_kp'])

        # No timer needed - monitoring will be done via telemetry data
        self.log_message("ZN calibration started")

    def update_kp_and_start_test(self, kp_value):
        """Update Kp value and start testing phase"""
        # Update PID tunings with current Kp (Ki=0, Kd=0 for ZN method)
        cmd = self.get_heater_cmd(f"pid_{{heater}}>{kp_value}_0_0")
        self.send_cmd_with_log(cmd)

        # Enable PID for testing
        cmd = self.get_heater_cmd("pid_{heater}_enable")
        self.send_cmd_with_log(cmd)

        # Update UI
        self.current_kp = kp_value
        self.current_kp_label.setText(f"Current Kp: {kp_value}")
        self.zn_calibration_params['phase'] = 'warming_up'
        self.zn_calibration_params['phase_start_time'] = time.time()
        self.zn_calibration_params['test_data'] = []
        self.zn_calibration_params['setpoint_reached'] = False
        self.zn_calibration_params['setpoint_reach_time'] = None
        setpoint = self.setpoint_spin.value()
        self.log_message(f"Starting test with Kp = {kp_value} - waiting for setpoint {setpoint}°C...")

    def monitor_zn_calibration(self):
        """Monitor ZN calibration phases and switch between testing and cooldown"""
        if not self.calibration_active or not hasattr(self, 'zn_calibration_params'):
            return

        # Ensure stop button stays enabled during calibration
        if not self.calib_stop_btn.isEnabled():
            self.calib_stop_btn.setEnabled(True)

        params = self.zn_calibration_params
        current_time = time.time()
        phase_elapsed = current_time - params['phase_start_time']

        if params['phase'] == 'warming_up':
            # Waiting for setpoint to be reached - check temperature
            if self.current_temperature is not None:
                setpoint = self.zn_temp_spin.value()
                temp_diff = abs(self.current_temperature - setpoint)

                if temp_diff <= ZN_SETPOINT_TOLERANCE and not params['setpoint_reached']:
                    # Setpoint reached for the first time
                    params['setpoint_reached'] = True
                    params['setpoint_reach_time'] = current_time
                    params['phase'] = 'testing'
                    params['phase_start_time'] = current_time  # Reset timer for testing phase
                    self.log_message(f"Setpoint reached! Starting data collection for Kp={params['current_kp']}")

        elif params['phase'] == 'testing':
            # Testing phase - collect data (only after setpoint reached)
            if params['setpoint_reached']:
                test_elapsed = current_time - params['setpoint_reach_time']
                if test_elapsed >= params['duration']:
                    # Testing phase complete, switch to cooldown
                    self.log_message(f"Testing phase complete for Kp={params['current_kp']}")
                    self.start_cooldown_phase()

        elif params['phase'] == 'cooldown':
            # Cooldown phase - PID disabled, analyze data for oscillations
            if not params.get('cooldown_analysis_done', False):
                # Perform oscillation analysis during cooldown
                self.log_message(f"Analyzing data for Kp={params['current_kp']} during cooldown...")
                oscillation_detected = self.analyze_kp_test_data(params['current_kp'])

                if oscillation_detected:
                    # Oscillation found! Store critical parameters and finish calibration
                    critical_gain = self.oscillation_stats['critical_gain']
                    critical_period = self.oscillation_stats['oscillation_period']
                    amplitude = self.oscillation_stats['oscillation_amplitude']

                    # Update display to show critical gain found
                    self.current_kp_label.setText(f"Critical Kp: {critical_gain:.1f} ✓")
                    self.current_kp_label.setStyleSheet("color: green; font-weight: bold;")

                    self.log_message(f"Critical gain found! Kp={critical_gain:.1f}, "
                                     f"Period={critical_period:.1f}s, Amplitude={amplitude:.2f}°C")
                    self.log_message("Finishing calibration early due to oscillation detection...")

                    # Finish calibration immediately
                    self.finish_zn_calibration()
                    return
                else:
                    # No oscillation detected, mark analysis as done
                    params['cooldown_analysis_done'] = True

            # Continue with normal cooldown timing
            if phase_elapsed >= params['cool_down_duration']:
                # Cooldown complete, move to next Kp or finish
                self.log_message(f"Cooldown phase complete for Kp={params['current_kp']}")
                self.move_to_next_kp()

    def start_cooldown_phase(self):
        """Start cooldown phase - disable PID"""
        cmd = self.get_heater_cmd("pid_{heater}_disable")
        self.send_cmd_with_log(cmd)

        self.zn_calibration_params['phase'] = 'cooldown'
        self.zn_calibration_params['phase_start_time'] = time.time()
        self.zn_calibration_params['cooldown_analysis_done'] = False  # Reset analysis flag

    def move_to_next_kp(self):
        """Move to next Kp value or finish calibration"""
        params = self.zn_calibration_params
        params['current_kp'] += params['kp_step']

        if params['current_kp'] > params['max_kp']:
            # Calibration complete
            self.log_message("ZN calibration complete!")
            self.finish_zn_calibration()
        else:
            # Reset test data for next Kp value
            params['test_data'] = []
            params['setpoint_reached'] = False
            params['setpoint_reach_time'] = None
            params['cooldown_analysis_done'] = False

            # Start next test
            self.log_message(f"Starting test for Kp={params['current_kp']}")
            self.update_kp_and_start_test(params['current_kp'])

    def finish_zn_calibration(self):
        """Finish ZN calibration and calculate results"""
        # No timer to stop - monitoring was done via telemetry

        # Stop PID controller
        cmd = self.get_heater_cmd("pid_{heater}_stop")
        self.send_cmd_with_log(cmd)

        # Reset temperature frequency
        self.send_cmd_with_log("update_freq_temp_1")

        self.display_calibration_results()
        self.calibration_active = False
        self.calib_status_label.setText("Calibration: Complete")
        self.calib_status_label.setStyleSheet("color: green; font-weight: bold;")
        self.calib_stop_btn.setEnabled(False)
        self.zn_start_btn.setEnabled(True)
        self.ol_start_btn.setEnabled(True)

        # Resume previous stream state
        if self.pre_calibration_stream_state:
            self.log_message("Resuming previous stream state...")
            self.restore_stream_state()

    # ------------------------------------------------------------------
    # Open-loop FOPDT calibration
    # ------------------------------------------------------------------
    # The board doesn't need any new firmware command for this: we just
    # drive the heater open-loop with the existing pwm_<heater>_<pct>
    # command, capture §TEMP frames, fit a first-order-plus-dead-time
    # model on the host, and propose PID gains from that model.

    OL_MAX_TEMP       = 90.0   # safety cutoff during the step (°C)
    OL_COOL_TIMEOUT_S = 600    # max wait for between-rep cooldown (s)
    OL_COOL_TOL_C     = 1.0    # how close to baseline counts as cooled

    @Slot()
    def start_open_loop_calibration(self):
        """Apply a PWM step open-loop, repeat for the configured number
        of reps, and identify a FOPDT process model from the response."""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return
        if not self.current_heater:
            self.log_message("No heater selected!")
            return
        if self.calibration_active:
            self.log_message("Calibration already in progress!")
            return

        self.ol_pwm_step = self.ol_pwm_spin.value()
        self.ol_duration_s = self.ol_duration_spin.value()
        self.ol_reps_total = self.ol_repetitions_spin.value()

        self.calibration_active = True
        self.calibration_method = "open_loop"
        self.ol_phase = 'step'
        self.ol_rep = 1
        self.ol_phase_start = time.time()
        self.ol_step_time = time.time()
        self.ol_reps_data = []        # one dict per rep: {baseline, samples}
        self.ol_samples = []          # samples for the current rep
        self.ol_baseline = None       # baseline of the current rep
        self.pre_calibration_stream_state = self.stream_active
        self.calibration_results = None

        # Stop whatever is currently driving the heater and start a
        # fast thermistor stream so the host gets a clean step response.
        if self.pid_active:
            self.send_cmd_with_log(self.get_heater_cmd("pid_{heater}_stop"))
        if self.stream_active:
            self.send_cmd_with_log("stream_stop")
        sleep(COMMAND_DELAY_SHORT)
        self.send_cmd_with_log("update_freq_temp_0.2")
        self.send_cmd_with_log("stream_thermistors")

        # Apply the step. Mirror the commanded value into self.pwm_value
        # so the PWM plot/label reflects what we're driving (the §TEMP
        # frame doesn't carry pwm_tec*).
        self.pwm_value = self.ol_pwm_step
        self.send_cmd_with_log(
            self.get_heater_cmd(f"pwm_{{heater}}_{self.ol_pwm_step}"))

        self.calib_status_label.setText(
            f"Calibration: Open-Loop rep 1/{self.ol_reps_total} "
            f"@ {self.ol_pwm_step}% PWM")
        self.calib_status_label.setStyleSheet("color: orange; font-weight: bold;")
        self.calib_stop_btn.setEnabled(True)
        self.zn_start_btn.setEnabled(False)
        self.ol_start_btn.setEnabled(False)
        self.calib_apply_btn.setEnabled(False)
        self.calib_results_text.clear()
        self.log_message(
            f"Open-loop calibration started — {self.ol_reps_total} rep(s) "
            f"of {self.ol_pwm_step}% PWM for {self.ol_duration_s}s each.")

    def _on_openloop_telemetry(self, data, frame):
        """State machine: step -> cooldown -> next step -> ... -> done."""
        if not self.calibration_active or self.calibration_method != 'open_loop':
            return

        T = None
        if frame == 'TEMP':
            temps = data.get('temperatures') or {}
            vals = [v for k, v in temps.items()
                    if k.startswith('thermistor')
                    and v is not None and v > INVALID_TEMP_THRESHOLD]
            if vals:
                T = sum(vals) / len(vals)
        if T is None:
            return

        now = time.time()
        phase_elapsed = now - self.ol_phase_start

        if self.ol_phase == 'step':
            # First sample of the rep is the baseline (we just commanded
            # the PWM step; the system has barely begun to respond).
            if self.ol_baseline is None:
                self.ol_baseline = T
            t_rel = now - self.ol_step_time
            self.ol_samples.append((t_rel, T))

            if T >= self.OL_MAX_TEMP:
                self.log_message(
                    f"Safety cutoff hit: T={T:.2f}°C ≥ "
                    f"{self.OL_MAX_TEMP:.1f}°C. Stopping.")
                self.pwm_value = 0
                self.send_cmd_with_log(self.get_heater_cmd("pwm_{heater}_0"))
                self.ol_reps_data.append({'baseline': self.ol_baseline,
                                          'samples': list(self.ol_samples)})
                self._finalise_openloop()
                return

            if phase_elapsed >= self.ol_duration_s:
                self.ol_reps_data.append({'baseline': self.ol_baseline,
                                          'samples': list(self.ol_samples)})
                self.pwm_value = 0
                self.send_cmd_with_log(self.get_heater_cmd("pwm_{heater}_0"))
                self.log_message(
                    f"Rep {self.ol_rep}/{self.ol_reps_total} done "
                    f"({len(self.ol_samples)} samples, "
                    f"ΔT={T - self.ol_baseline:+.2f}°C).")
                if self.ol_rep >= self.ol_reps_total:
                    self._finalise_openloop()
                    return
                self.ol_phase = 'cooldown'
                self.ol_phase_start = time.time()
                self.calib_status_label.setText(
                    f"Calibration: Open-Loop cooldown after rep "
                    f"{self.ol_rep}/{self.ol_reps_total}")
            return

        if self.ol_phase == 'cooldown':
            target_T = self.ol_reps_data[-1]['baseline'] + self.OL_COOL_TOL_C
            cooled = T <= target_T
            timed_out = phase_elapsed >= self.OL_COOL_TIMEOUT_S
            if cooled or timed_out:
                if timed_out and not cooled:
                    self.log_message(
                        f"Cooldown timed out at {T:.2f}°C "
                        f"(target {target_T:.2f}°C); starting next rep "
                        f"anyway.")
                else:
                    self.log_message(
                        f"Cooled to {T:.2f}°C — starting rep "
                        f"{self.ol_rep + 1}.")
                self.ol_rep += 1
                self.ol_samples = []
                self.ol_baseline = None
                self.pwm_value = self.ol_pwm_step
                self.send_cmd_with_log(
                    self.get_heater_cmd(f"pwm_{{heater}}_{self.ol_pwm_step}"))
                self.ol_phase = 'step'
                self.ol_phase_start = time.time()
                self.ol_step_time = time.time()
                self.calib_status_label.setText(
                    f"Calibration: Open-Loop rep "
                    f"{self.ol_rep}/{self.ol_reps_total} "
                    f"@ {self.ol_pwm_step}% PWM")
            return

    def _stop_openloop(self):
        """User pressed Stop, or we aborted: shut everything down cleanly."""
        self.pwm_value = 0
        self.send_cmd_with_log(self.get_heater_cmd("pwm_{heater}_0"))
        self.send_cmd_with_log("stream_stop")
        self.send_cmd_with_log("update_freq_temp_1")
        self.calibration_active = False
        self.ol_phase = None
        self.calib_status_label.setText("Calibration: Stopped")
        self.calib_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.calib_apply_btn.setEnabled(False)
        self.zn_start_btn.setEnabled(True)
        self.ol_start_btn.setEnabled(True)
        self.calib_stop_btn.setEnabled(False)
        if self.pre_calibration_stream_state:
            self.restore_stream_state()

    def _finalise_openloop(self):
        """Stop the heater, fit the FOPDT model, compute candidate gains."""
        # PWM is already at 0 from the state machine; redundantly enforce
        # it here in case we got here via the safety cutoff path.
        self.pwm_value = 0
        self.send_cmd_with_log(self.get_heater_cmd("pwm_{heater}_0"))
        self.send_cmd_with_log("stream_stop")
        self.send_cmd_with_log("update_freq_temp_1")

        # Save raw response (all reps) — useful if the fit looks off and
        # we want to re-analyse later.
        try:
            log_dir = Path("heater_logs")
            log_dir.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            outpath = log_dir / f"openloop_{stamp}.json"
            with open(outpath, 'w') as f:
                json.dump({
                    'pwm_step': self.ol_pwm_step,
                    'duration_requested': self.ol_duration_s,
                    'reps': self.ol_reps_data,
                }, f)
            self.log_message(f"Raw step response saved to {outpath}")
        except Exception as e:
            self.log_message(f"Could not save raw response: {e}")

        if not self.ol_reps_data:
            self.log_message("No reps captured; nothing to fit.")
            self._stop_openloop()
            return

        try:
            from scipy.optimize import curve_fit
        except Exception as e:
            self.log_message(f"scipy.optimize.curve_fit not available: {e}")
            self._stop_openloop()
            return

        # Build a single rise-over-baseline curve averaged across reps
        # on a common 0.5 s time grid. Each rep contributes
        # (T(t) - rep.baseline) so different ambient starts don't bias
        # the fit.
        common_dt = 0.5
        t_grid = np.arange(0, self.ol_duration_s + common_dt, common_dt)
        rises = []
        baselines = []
        for rep in self.ol_reps_data:
            samples = rep.get('samples') or []
            if len(samples) < 5:
                continue
            t_rep = np.array([s[0] for s in samples])
            T_rep = np.array([s[1] for s in samples])
            t_max = float(t_rep.max())
            grid_in_range = t_grid <= t_max
            if not grid_in_range.any():
                continue
            rises.append(np.interp(t_grid[grid_in_range], t_rep, T_rep)
                         - rep['baseline'])
            baselines.append(rep['baseline'])

        if not rises:
            self.log_message(
                f"Reps contained too few samples to fit ({len(self.ol_reps_data)} "
                f"rep(s)). Aborting.")
            self._stop_openloop()
            return

        # Truncate every rep to the shortest length so np.mean is well
        # defined (handles the safety-cutoff case where the last rep is
        # shorter than the others).
        min_len = min(len(r) for r in rises)
        rise_avg = np.mean(np.vstack([r[:min_len] for r in rises]), axis=0)
        t_arr = t_grid[:min_len]
        T0 = float(np.mean(baselines))
        T_arr = rise_avg + T0

        # First-order-plus-dead-time on the rise:
        #   y(t) = 0                              for t < L
        #   y(t) = dT * (1 - exp(-(t - L)/tau))   for t >= L
        def fopdt_rise(t, dT, tau, L):
            t = np.asarray(t)
            return np.where(t < L, 0.0,
                            dT * (1 - np.exp(-(t - L) / tau)))

        try:
            popt, _ = curve_fit(
                fopdt_rise, t_arr, rise_avg,
                p0=[max(rise_avg.max(), 1.0), 100.0, 2.0],
                bounds=([1.0, 5.0, 0.0], [400.0, 800.0, 60.0]))
        except Exception as e:
            self.log_message(f"FOPDT fit failed: {e}")
            self._stop_openloop()
            return

        dT, tau, L = popt
        K = dT / self.ol_pwm_step                 # °C per %PWM
        T_inf = T0 + dT
        y_fit = fopdt_rise(t_arr, *popt)
        rmse = float(np.sqrt(np.mean((rise_avg - y_fit) ** 2)))

        def simc(tau_c):
            # Skogestad SIMC PI tuning for first-order-plus-dead-time.
            Kp = tau / (K * (tau_c + L)) if K > 0 else 0.0
            Ti = min(tau, 4 * (tau_c + L))
            return Kp, (Kp / Ti if Ti > 0 else 0.0), 0.0

        def cohen_coon():
            r = L / tau if tau > 0 else 0.01
            if r <= 0 or K == 0:
                return 0.0, 0.0, 0.0
            Kp = (1.35 + 0.25 * r) / (K * r)
            Ti = L * (1.35 + 0.25 * r) / (0.54 + 0.33 * r)
            Td = 0.5 * L / (1.35 + 0.25 * r)
            return Kp, Kp / Ti, Kp * Td

        def zn_pid():
            if L <= 0 or K == 0:
                return 0.0, 0.0, 0.0
            Kp = 1.2 * tau / (K * L)
            Ti = 2.0 * L
            Td = 0.5 * L
            return Kp, Kp / Ti, Kp * Td

        simc_aggressive   = simc(L)
        simc_moderate     = simc(2 * L)
        simc_conservative = simc(3 * L)
        cc                = cohen_coon()
        zn                = zn_pid()

        # SIMC moderate (tau_c = 2L) is the default — well-behaved for
        # thermal loops without being too sluggish.
        recommended_kp, recommended_ki, recommended_kd = simc_moderate

        self.calibration_results = {
            'method': 'Open-Loop FOPDT',
            'kp': recommended_kp,
            'ki': recommended_ki,
            'kd': recommended_kd,
            'simc_aggressive': simc_aggressive,
            'simc_moderate': simc_moderate,
            'simc_conservative': simc_conservative,
            'cohen_coon': cc,
            'zn_pid': zn,
            'process': {'T0': T0, 'T_inf': T_inf, 'dT': dT,
                        'tau': tau, 'L': L, 'K': K, 'rmse': rmse,
                        'pwm_step': self.ol_pwm_step,
                        'n_samples': int(len(t_arr)),
                        'n_reps': int(len(rises))},
        }

        self.display_calibration_results()
        self.calibration_active = False
        self.ol_phase = None
        self.calib_status_label.setText("Calibration: Complete")
        self.calib_status_label.setStyleSheet("color: green; font-weight: bold;")
        self.calib_apply_btn.setEnabled(True)
        self.zn_start_btn.setEnabled(True)
        self.ol_start_btn.setEnabled(True)
        self.calib_stop_btn.setEnabled(False)
        if self.pre_calibration_stream_state:
            self.restore_stream_state()

    @Slot()
    def stop_calibration(self):
        """Stop current calibration (dispatch to the right cleanup path)."""
        if not self.calibration_active:
            return

        if self.calibration_method == "open_loop":
            self._stop_openloop()
            return

        self.pid_enabled = False
        try:
            self.send_cmd_with_log("pid_stop")
            self.send_cmd_with_log("update_freq_temp_1")

            self.calibration_active = False
            self.calib_status_label.setText("Calibration: Stopped")
            self.calib_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.current_kp_label.setText("Current Kp: --")
            self.current_kp_label.setStyleSheet("color: blue; font-weight: bold;")
            self.calib_stop_btn.setEnabled(False)
            self.zn_start_btn.setEnabled(True)
            self.ol_start_btn.setEnabled(True)

            if self.pre_calibration_stream_state:
                self.log_message("Resuming previous stream state...")
                self.restore_stream_state()

        except Exception as e:
            self.log_message(f"Error stopping calibration: {e}")

    def display_calibration_results(self):
        """Display calibration results in the UI"""
        if not self.calibration_results:
            return

        results_text = f"Calibration Results ({self.calibration_results['method']}):\n"
        results_text += "=" * 50 + "\n"

        if self.calibration_results['method'] == 'Ziegler-Nichols':
            # Enhanced Ziegler-Nichols display
            results_text += f"Critical Gain (Ku): {self.oscillation_stats['critical_gain']:.3f}\n"
            results_text += f"Critical Period (Pu): {self.oscillation_stats['oscillation_period']:.2f}s\n"
            results_text += f"Oscillation Amplitude: {self.oscillation_stats['oscillation_amplitude']:.3f}°C\n"
            results_text += f"Peaks/Valleys: {self.oscillation_stats['num_peaks']}/{self.oscillation_stats['num_valleys']}\n"
            results_text += f"Temperature Range: {self.oscillation_stats['temperature_range']:.2f}°C\n"
            results_text += f"Stability (±1σ): {self.oscillation_stats['stability_std']:.3f}°C\n"
            results_text += f"Detection: {'Auto-detected' if self.oscillation_stats['oscillation_detected'] else 'Manual analysis'}\n"
            results_text += "\n"

            # Show all controller types
            if self.calibration_results.get('method', False):
                results_text += "RECOMMENDED PID PARAMETERS:\n"
                results_text += "-" * 30 + "\n"
                results_text += "Standard PID Parameters:\n"
                results_text += f"Kp: {self.calibration_results['kp']:.3f}\n"
                results_text += f"Ki: {self.calibration_results['ki']:.3f}\n"
                results_text += f"Kd: {self.calibration_results['kd']:.3f}\n"
                if self.calibration_results["method"] == "Ziegler-Nichols":
                    results_text += "\n"
                    results_text += "No Overshoot PID Parameters:\n"
                    results_text += f"Kp: {self.calibration_results['kp_no_overshoot']:.3f}\n"
                    results_text += f"Ki: {self.calibration_results['ki_no_overshoot']:.3f}\n"
                    results_text += f"Kd: {self.calibration_results['kd_no_overshoot']:.3f}\n"
                    results_text += "\n"
                    results_text += "Aggressive PID Parameters:\n"
                    results_text += f"Kp: {self.calibration_results['kp_aggressive']:.3f}\n"
                    results_text += f"Ki: {self.calibration_results['ki_aggressive']:.3f}\n"
                    results_text += f"Kd: {self.calibration_results['kd_aggressive']:.3f}\n"

        elif self.calibration_results['method'] == 'Open-Loop FOPDT':
            r = self.calibration_results
            p = r['process']
            results_text += "Process Model (FOPDT):\n"
            results_text += f"  Baseline T0   = {p['T0']:.2f} °C\n"
            results_text += f"  Asymptote T∞  = {p['T_inf']:.2f} °C  (Δ = {p['dT']:.2f} °C @ {p['pwm_step']}% PWM)\n"
            results_text += f"  Time const τ  = {p['tau']:.2f} s\n"
            results_text += f"  Dead time L   = {p['L']:.2f} s\n"
            results_text += f"  Process gain  = {p['K']:.4f} °C / %PWM\n"
            results_text += (
                f"  Fit RMSE      = {p['rmse']:.3f} °C  "
                f"({p['n_samples']} samples avg of "
                f"{p.get('n_reps', 1)} rep)\n\n")
            results_text += "Recommended PID gains   (kp,    ki,     kd):\n"
            results_text += "-" * 50 + "\n"
            def fmt(t):
                return f"({t[0]:7.3f}, {t[1]:7.4f}, {t[2]:7.3f})"
            results_text += f"  SIMC aggressive    {fmt(r['simc_aggressive'])}\n"
            results_text += f"  SIMC moderate ★    {fmt(r['simc_moderate'])}\n"
            results_text += f"  SIMC conservative  {fmt(r['simc_conservative'])}\n"
            results_text += f"  Cohen-Coon         {fmt(r['cohen_coon'])}\n"
            results_text += f"  Ziegler-Nichols    {fmt(r['zn_pid'])}\n\n"
            results_text += "★ 'Apply Results' applies SIMC moderate.\n"
            results_text += "  To try a different recipe, copy those\n"
            results_text += "  values into the kp/ki/kd boxes and click\n"
            results_text += "  'Apply PID Parameters'.\n"
        else:
            # Unknown method
            pass

        self.calib_results_text.setText(results_text)
        self.log_message("Calibration results calculated and displayed")

    @Slot()
    def apply_calibration_results(self):
        """Apply calculated PID parameters to the system"""
        if not self.calibration_results:
            self.log_message("No calibration results to apply!")
            return

        try:
            kp = self.calibration_results['kp']
            ki = self.calibration_results['ki']
            kd = self.calibration_results['kd']

            # Update the PID parameter spin boxes
            self.kp_spin.setValue(kp)
            self.ki_spin.setValue(ki)
            self.kd_spin.setValue(kd)

            # Update current PID values
            self.current_kp = kp
            self.current_ki = ki
            self.current_kd = kd

            # Update display
            self.current_pid_label.setText(f"Current PID: Kp={kp:.2f}, Ki={ki:.2f}, Kd={kd:.2f}")

            # Send PID parameters to firmware
            # Format: pid_<heater_name>><kp>_<ki>_<kd>
            cmd = self.get_heater_cmd(f"pid_{{heater}}>{kp}_{ki}_{kd}")
            self.send_cmd_with_log(cmd)

            self.log_message(f"Applied PID parameters: Kp={kp:.2f}, Ki={ki:.2f}, Kd={kd:.2f}")
            self.calib_apply_btn.setEnabled(False)

            # Update the PID button to reflect that PID is now configured
            self.pid_toggle_btn.setChecked(True)
            self.pid_toggle_btn.setText("Stop PID Control")
            self.pid_toggle_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #f44336; 
                    color: white;
                    font-weight: bold;
                }
                QPushButton:hover { 
                    background-color: #d32f2f; 
                }
                QPushButton:pressed { 
                    background-color: #b71c1c; 
                }
            """)

        except Exception as e:
            self.log_message(f"Error applying PID parameters: {e}")

    def analyze_kp_test_data(self, kp_value):
        """Analyze data from a specific Kp test to detect oscillations"""
        try:
            if not self.zn_calibration_params['test_data']:
                return False, 0, 0

            test_data = self.zn_calibration_params['test_data']
            if len(test_data) < 20:  # Need sufficient data
                self.log_message(f"Insufficient data for Kp={kp_value} analysis")
                return False, 0, 0

            # Extract temperature data
            temps = np.array([d['temperature'] for d in test_data if d['temperature'] is not None])
            timestamps = np.array([d['timestamp'] for d in test_data if d['temperature'] is not None])

            if len(temps) < 20:
                self.log_message(f"Insufficient valid temperature data for Kp={kp_value} analysis")
                return False, 0, 0

            # Detect oscillations using scipy
            oscillation_detected = self.detect_oscillations(temps,
                                                            timestamps)

            if oscillation_detected:
                if self.oscillation_stats is not None:
                    self.oscillation_stats['critical_gain'] = kp_value
                    amplitude = self.oscillation_stats['oscillation_amplitude']
                    period = self.oscillation_stats['oscillation_period']
                    self.log_message(f"Oscillation detected at Kp={kp_value}, "
                                     f"Amplitude={amplitude:.2f}°C, Period={period:.1f}s")

                    kp = kp_value * 0.6
                    ki = 1.2 *  kp_value / period
                    kd = 0.075 * kp_value * period

                    kp_no_overshoot = 0.2 * kp_value
                    ki_no_overshoot = 0.4 * kp_value / period
                    kd_no_overshoot = 0.066 * kp_value * period

                    kp_aggressive = 0.7 * kp_value
                    ki_aggressive = 1.75 * kp_value / period
                    kd_aggressive = 0.105 * kp_value * period

                    self.calibration_results = {'method': 'Ziegler-Nichols',
                                                'kp': kp,
                                                'ki': ki,
                                                'kd': kd,
                                                'kp_no_overshoot': kp_no_overshoot,
                                                'ki_no_overshoot': ki_no_overshoot,
                                                'kd_no_overshoot': kd_no_overshoot,
                                                'kp_aggressive': kp_aggressive,
                                                'ki_aggressive': ki_aggressive,
                                                'kd_aggressive': kd_aggressive}
                    return True
            else:
                self.log_message(f"No oscillation detected at Kp={kp_value}")
                return False

        except Exception as e:
            self.log_message(f"Error analyzing Kp test data: {e}")
            return False

    def _find_peaks_valleys(self, data, **kwargs):
        """Find peaks and valleys in temperature data"""        # Find peaks (local maxima)
        peaks, _ = find_peaks(data, **kwargs)

        # Find valleys (local minima)
        valleys, _ = find_peaks(-data, **kwargs)

        return peaks, valleys

    def low_pass_filter(self, data, cutoff_freq, sampling_rate, order=4):
        """Apply Butterworth low-pass filter."""
        nyquist = 0.5 * sampling_rate
        normal_cutoff = cutoff_freq / nyquist
        b, a = butter(order, normal_cutoff, btype='low', analog=False)
        return filtfilt(b, a, data)

    def detect_oscillations(self, temperatures, timestamps,
                            min_amplitude=1, min_period=10):
        """Detect oscillations in temperature data using scipy"""
        temps = np.array(temperatures)
        # Calculate sampling rate
        sampling_rate = len(timestamps) / (timestamps[-1] - timestamps[0])
        # Apply Butterworth 0.5Hz filter to smooth the data
        temps_filtered = self.low_pass_filter(temps, cutoff_freq=0.5,
                                              sampling_rate=sampling_rate,
                                              order=4)

        # save data to a csv for validation
        df = pd.DataFrame({'timestamps': timestamps, 'temperatures': temps})
        dir_path = Path('calib_temp_data')
        dir_path.mkdir(parents=True, exist_ok=True)
        filename = f'temperatures{self.zn_temp_spin.value()}_{self.current_kp}.csv'
        df.to_csv(dir_path / filename, index=False)

        try:
            peaks, valleys = self._find_peaks_valleys(temps_filtered,
                                                      distance=5,  # Minimum distance between peaks
                                                      prominence=0.1)  # Minimum prominence

            if len(peaks) < 3 or len(valleys) < 3:
                return False, 0, 0

            # Calculate oscillation amplitude using filtered data
            peak_temps = temps_filtered[peaks]
            valley_temps = temps_filtered[valleys]
            amplitude = (np.mean(peak_temps) - np.mean(valley_temps)) / 2

            if amplitude < min_amplitude:
                return False

            # Calculate oscillation period
            peak_times = timestamps[peaks]
            if len(peak_times) > 1:
                periods = np.diff(peak_times)
                period = np.median(periods)  # Use median to avoid outliers
            else:
                period = 0

            if period < min_period:
                return False

            # Additional check: look for sustained oscillations
            # Check if the last few peaks/valleys show consistent amplitude
            if len(peaks) >= 4 and len(valleys) >= 4:
                recent_peaks = peak_temps[-4:]
                recent_valleys = valley_temps[-4:]
                recent_amplitude = (np.mean(recent_peaks) - np.mean(recent_valleys)) / 2

                # Oscillation is sustained if recent amplitude is similar to overall amplitude
                if recent_amplitude < amplitude * 0.7:
                    return False

            self.oscillation_stats = {
                'oscillation_detected': True,
                'oscillation_amplitude': amplitude,
                'oscillation_period': period,
                'num_peaks': len(peaks),
                'num_valleys': len(valleys),
                'temperature_range': np.max(temps) - np.min(temps),
                'stability_std': np.std(temps)
            }

            return True

        except ImportError:
            # Fallback if scipy is not available
            self.log_message("scipy not available, using simple oscillation detection")
            return self.simple_oscillation_detection(temperatures, timestamps, min_amplitude, min_period)
        except Exception as e:
            self.log_message(f"Error in oscillation detection: {e}")
            return False, 0, 0

    @Slot()
    def refresh_serial_ports(self):
        """Refresh the list of available serial ports"""
        try:
            # Save currently selected port
            current_port = self.port_combo.currentText()

            # Clear and repopulate the combo box
            self.port_combo.clear()
            ports = Board.list_serial_ports_filtered()

            if ports:
                for port in ports:
                    # Display port name with description
                    port_display = f"{port.device}"
                    if port.description and port.description != 'n/a':
                        port_display += f" - {port.description}"
                    self.port_combo.addItem(port_display, port.device)

                # Try to restore previous selection
                if current_port:
                    index = self.port_combo.findText(
                        current_port, Qt.MatchStartsWith)
                    if index >= 0:
                        self.port_combo.setCurrentIndex(index)

                self.log_message(f"Found {len(ports)} serial port(s)")
            else:
                self.port_combo.addItem("No ports found", None)
                self.log_message("No serial ports found")

        except Exception as e:
            self.log_message(f"Error refreshing serial ports: {e}")
            self.port_combo.addItem("Error loading ports", None)

    @Slot()
    def connect_usb(self):
        """Connect to USB device"""
        try:
            # Get selected port
            selected_port = self.port_combo.currentData()

            if not selected_port:
                self.log_message("Please select a valid serial port")
                return

            self.log_message(f"Connecting to {selected_port}...")
            self.connect_btn.setEnabled(False)
            self.port_combo.setEnabled(False)
            self.refresh_ports_btn.setEnabled(False)

            # Update board port before connecting
            self.board.port = selected_port

            # Try to connect
            success = self.board.setup()
            if success:
                self.log_message("Connected successfully!")
                self.connection_status.setText("Connected")
                self.connection_status.setStyleSheet(
                    "color: green; font-weight: bold;")
                self.connect_btn.setEnabled(False)
                self.disconnect_btn.setEnabled(True)
                self.status_bar.showMessage(
                    f"Connected via USB to {selected_port}")
            else:
                self.log_message("Connection failed!")
                self.connect_btn.setEnabled(True)
                self.port_combo.setEnabled(True)
                self.refresh_ports_btn.setEnabled(True)

        except Exception as e:
            self.log_message(f"Connection error: {e}")
            self.connect_btn.setEnabled(True)
            self.port_combo.setEnabled(True)
            self.refresh_ports_btn.setEnabled(True)

    @Slot()
    def disconnect(self):
        """Disconnect from device"""
        try:
            if self.board:
                self.board.close()
            self.connection_status.setText("Disconnected")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.port_combo.setEnabled(True)
            self.refresh_ports_btn.setEnabled(True)
            self.status_bar.showMessage("Disconnected")
            self.log_message("Disconnected from device")
        except Exception as e:
            self.log_message(f"Disconnect error: {e}")

    @Slot(bool)
    def on_connection_changed(self, connected):
        """Handle connection status changes"""
        if connected:
            self.connection_status.setText("Connected")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.port_combo.setEnabled(False)
            self.refresh_ports_btn.setEnabled(False)
            self.status_bar.showMessage("Connected via USB")

            # Query the board identity first so the board ID label is
            # populated before the heater list arrives.
            QTimer.singleShot(200, self.query_whoami)
            # Query available heaters after connection
            QTimer.singleShot(600, self.query_available_heaters)
        else:
            self.connection_status.setText("Disconnected")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.port_combo.setEnabled(True)
            self.refresh_ports_btn.setEnabled(True)
            self.status_bar.showMessage("Disconnected")
            self.board_id_label.setText("Board: -")
            self.board_info = {}
            # Clear heater selection
            self.heater_combo_selection.clear()
            self.heater_combo_selection.setEnabled(False)
            self.current_heater = None
            self.current_heater_type = None

    @Slot(str)
    def on_message_received(self, message):
        """Handle raw text messages from board.

        Structured state-change events (pid_started/pid_stopped/pid_saved/
        overtemp etc.) now arrive via §INFO and §ERR frames and are handled
        in _on_info_frame / _on_err_frame. This handler only deals with the
        legacy plain-text responses (heater list, pid tunings, ZN
        calibration messages)."""
        if self.parse_available_heaters(message):
            return
        if self.parse_pid_values(message):
            return
        if self.calibration_active and self.calibration_method == "ziegler_nichols":
            self.monitor_calibration_messages(message)

    @Slot(str)
    def on_status_message(self, message):
        """Handle status messages from board."""
        self.log_message(f"Board: {message}")
        if self.calibration_active and self.calibration_method == "ziegler_nichols":
            self.monitor_calibration_messages(message)

    @Slot(dict)
    def on_telemetry_received(self, data):
        """Route telemetry by frame header. controller.py tags each frame
        with `_frame` set to the prefix that followed the '§' marker
        (TEMP, PID_<HEATER>, INFO, ERR, WHOAMI, etc.)."""
        frame = data.get('_frame', '') if isinstance(data, dict) else ''
        if frame == 'WHOAMI':
            self._on_whoami_frame(data)
            return
        if frame == 'INFO':
            self._on_info_frame(data)
            return
        if frame == 'ERR':
            self._on_err_frame(data)
            return

        # If an open-loop calibration is in flight, feed its state
        # machine before (or instead of) the normal plotting path. The
        # plot is still updated below so the user sees the live curve.
        if self.calibration_active and self.calibration_method == 'open_loop':
            self._on_openloop_telemetry(data, frame)

        # Otherwise treat as TEMP / PID_<HEATER> telemetry.
        self._on_pid_telemetry(data)

    def _on_whoami_frame(self, data):
        """Display board identity in the connection group + window title."""
        self.board_info = {
            'uid': data.get('uid'),
            'device_id': data.get('device_id'),
            'bluetooth_name': data.get('bluetooth_name'),
        }
        label = self._format_board_identity(self.board_info)
        self.board_id_label.setText(f"Board: {label}")
        self.setWindowTitle(f"Heater Control System v1.0 — {label}")
        self.log_message(f"Board identified: {label}")

    def _on_info_frame(self, data):
        """Surface structured §INFO events into the log + reactive UI bits."""
        event = data.get('event', '?')
        if event == 'pid_saved':
            kp, ki, kd = data.get('kp'), data.get('ki'), data.get('kd')
            self.log_message(
                f"PID saved to board flash: Kp={kp}, Ki={ki}, Kd={kd}")
            self.status_bar.showMessage("PID tunings saved to board.", 5000)
            return
        if event == 'pid_started':
            self.pid_active = True
            self.pid_enabled = True
            if not self.stream_active:
                self.set_stream_active(True)
            if not self.pid_toggle_btn.isChecked():
                self.pid_toggle_btn.setChecked(True)
            return
        if event == 'pid_stopped':
            self.pid_active = False
            self.pid_enabled = False
            # Don't touch stream_active here. pid_stopped means the
            # PID-coupled stream task ended on the board, but the user
            # may have unchecked the PID toggle (which immediately kicks
            # off a plain stream_<group> task) — in that case a stream
            # is still running and the UI button should keep saying
            # "Stop Stream". The synchronous paths that *do* want
            # streaming to stop (stop_stream, stream_stop send, err
            # frames) already update stream_active themselves.
            if self.pid_toggle_btn.isChecked():
                self.pid_toggle_btn.setChecked(False)
            return
        # Anything else: log compactly.
        compact = {k: v for k, v in data.items() if not k.startswith('_')}
        self.log_message(f"§INFO {event}: {compact}")

    def _on_err_frame(self, data):
        kind = data.get('kind', '?')
        heater = data.get('heater', '?')
        msg = data.get('message', '')
        self.log_message(f"§ERR [{kind}] on {heater}: {msg}")
        self.status_bar.showMessage(
            f"Board error ({heater}, {kind}): {msg}", 10000)
        # An overtemp/task_crash for the active heater stops PID streaming
        # on the board side; reflect that in the UI.
        if kind in ('overtemp', 'task_crash', 'sensor_fail'):
            self.pid_active = False
            if self.stream_active:
                self.set_stream_active(False)
            if self.pid_toggle_btn.isChecked():
                self.pid_toggle_btn.setChecked(False)

    @staticmethod
    def _format_board_identity(info):
        parts = []
        if info.get('device_id'):
            parts.append(str(info['device_id']))
        uid = info.get('uid')
        if uid:
            short = uid if len(uid) <= 10 else f"{uid[:8]}…"
            parts.append(f"uid:{short}")
        return " / ".join(parts) if parts else "(unknown)"

    def _on_pid_telemetry(self, data):
        """Handle telemetry data from board"""
        try:
            # Extract temperature data
            current = data.get('current', 0)
            temperatures_dict = data.get('temperatures', {})
            pid_temp = data.get('pid_temperature', -50)

            if self.pid_enabled:
                # PID stream provides pwm_percentage for TEC1 (TEC1 and TEC2 are dependent)
                heater1_pwm = data.get('pwm_percentage', 0)
                heater2_pwm = heater1_pwm  # TEC1 and TEC2 are dependent
            else:
                heater1_pwm = data.get('pwm_tec1', self.pwm_value)
                heater2_pwm = data.get('pwm_tec2', self.pwm_value)
            timestamp = data.get('timestamp', 0)
            if timestamp < self.last_timestamp:
                timestamp += self.last_timestamp
            self.last_timestamp = timestamp

            if pid_temp > INVALID_TEMP_THRESHOLD:
                self.current_temperature = pid_temp
                self.pid_temp_status_label.setText(f"PID Temp: {pid_temp:.1f}°C")
            else:
                self.current_temperature = None
                pid_temp = None
                self.pid_temp_status_label.setText("PID Temp: --°C")

            # Update dynamic sensor labels
            valid_temperatures = {}
            for sensor_name, temp_value in temperatures_dict.items():
                if temp_value > INVALID_TEMP_THRESHOLD:
                    valid_temperatures[sensor_name] = temp_value
                    # Create label if it doesn't exist
                    if sensor_name not in self.sensor_labels:
                        label = QLabel(f"{sensor_name}: {temp_value:.1f}°C")
                        self.sensor_labels[sensor_name] = label
                        self.sensor_labels_layout.addWidget(label)
                    else:
                        # Update existing label
                        self.sensor_labels[sensor_name].setText(f"{sensor_name}: {temp_value:.1f}°C")
                else:
                    # Mark sensor as invalid
                    if sensor_name in self.sensor_labels:
                        self.sensor_labels[sensor_name].setText(f"{sensor_name}: --°C")

            # Update current and PWM labels
            if current is not None:
                self.current_label.setText(f"Current: {current:.1f}A")
            else:
                self.current_label.setText("Current: --A")
            self.heater1_pwm_label.setText(f"Heater PWM: {heater1_pwm:.1f}%")
            self.heater2_pwm_label.setText(f"Heater2 PWM: {heater2_pwm:.1f}%")

            # Monitor ZN calibration if active
            if self.calibration_active and self.calibration_method == "ziegler_nichols":
                self.monitor_zn_calibration()
                self.pid_enabled = True

            if self.calibration_active and self.calibration_method == "ziegler_nichols":
                setpoint = self.zn_temp_spin.value()
            else:
                if self.pid_enabled:
                    setpoint = self.current_setpoint
                else:
                    setpoint = None


            # Add data to plot (pass all sensors as dict)
            self.plot_widget.add_data_point(
                timestamp, valid_temperatures, pid_temp,
                heater1_pwm, heater2_pwm, setpoint
            )

            # Capture calibration data if calibration is active
            if self.calibration_active:
                self.calibration_data['timestamps'].append(timestamp)
                self.calibration_data['temperatures'].append(pid_temp)  # Use PID temp for calibration
                self.calibration_data['pwm_values'].append(heater1_pwm)
                self.calibration_data['setpoints'].append(self.current_setpoint)

                # Store data for current Kp test (Ziegler-Nichols only)
                # Only collect data during testing phase (after setpoint reached)
                if (self.calibration_method == "ziegler_nichols" and
                    self.zn_calibration_params.get('phase', None) == 'testing' and
                    self.zn_calibration_params.get('setpoint_reached', False)):

                    # Add data to current test
                    self.zn_calibration_params['test_data'].append({
                        'timestamp': timestamp,
                        'temperature': pid_temp if pid_temp else None,
                        'pwm': heater1_pwm,
                        'setpoint': self.current_setpoint
                    })

            # Log data if logging is enabled
            if self.is_logging:
                log_data = {
                    'temperatures': valid_temperatures,
                    'dt': timestamp,
                    'current': current,
                    'pid_temp': pid_temp,
                    'heater1_pwm': heater1_pwm,
                    'heater2_pwm': heater2_pwm,
                    'pid_enabled': self.pid_enabled,
                    'setpoint': setpoint
                }
                self.data_logger.log_data(log_data)

            if self.profile_active:
                self.check_profile_step(pid_temp)

        except Exception as e:
            self.log_message(f"Error processing telemetry: {e}")
            print(traceback.format_exc())

    @Slot()
    def toggle_stream(self):
        """Toggle stream on/off"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        if self.stream_active:
            self.stop_stream()
        else:
            self.start_stream()

    @Slot()
    def on_compensation_changed(self):
        """Handle compensation changes"""
        self.compensation_rate = self.compensation_rate_spin.value()
        self.compensation_offset = self.compensation_offset_spin.value()
        self.config['heater_control']['compensation_rate'] = self.compensation_rate
        self.config['heater_control']['compensation_offset'] = self.compensation_offset

        # Write to file
        with open("config.yml", "w") as outfile:
            yaml.dump(self.config, outfile, default_flow_style=False)

        self.log_message(f"Temperature compensation changed to {self.compensation_rate:.2f}x temperature and {self.compensation_offset:.2f}°C offset")

    def start_stream(self):
        """Start temperature streaming with current settings"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        try:
            # Stop any existing stream first
            if self.pid_active:
                self.send_cmd_with_log("pid_stop")
            else:
                self.send_cmd_with_log("stream_stop")
            sleep(COMMAND_DELAY_SHORT)

            # Get sensor group
            sensor_group = self.sensor_group_combo.currentText()

            # Check PID checkbox state to determine which command to send
            if self.pid_toggle_btn.isChecked():
                # Start PID control with selected sensor group
                setpoint = round((self.setpoint_spin.value() * self.compensation_rate) + self.compensation_offset, 2)
                self.current_setpoint = setpoint

                if sensor_group == "None":
                    cmd = self.get_heater_cmd(f"pid_{{heater}}_{setpoint}")
                else:
                    cmd = self.get_heater_cmd(f"pid_{{heater}}_{setpoint}_{sensor_group}")

                self.send_cmd_with_log(cmd)
                self.pid_active = True
                self.pid_enabled = True
                self.log_message(f"Started PID control at {setpoint}°C with sensor group '{sensor_group}'")
            else:
                # Start temperature streaming only
                if sensor_group == "None":
                    cmd = "stream_all"
                else:
                    cmd = f"stream_{sensor_group}"

                self.send_cmd_with_log(cmd)
                self.pid_active = False
                self.pid_enabled = False
                self.log_message(f"Started temperature streaming for sensor group '{sensor_group}'")

            # Update button state
            self.set_stream_active(True)

        except Exception as e:
            self.log_message(f"Error starting stream: {e}")

    def stop_stream(self):
        """Stop all streaming and control"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        try:
            # Stop whatever is currently running
            if self.pid_active:
                self.send_cmd_with_log("pid_stop")
                self.log_message("Stopped PID control")
            else:
                self.send_cmd_with_log("stream_stop")
                self.log_message("Stopped temperature streaming")

            # Reset state
            self.pid_active = False
            # Note: Don't reset pid_enabled here - the checkbox state determines that

            # Update button state
            self.set_stream_active(False)

        except Exception as e:
            self.log_message(f"Error stopping stream: {e}")

    def set_stream_active(self, active):
        """Update stream state and button appearance"""
        self.stream_active = active
        if active:
            self.stream_toggle_btn.setText("Stop Stream")
            self.stream_toggle_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #f44336; 
                    color: white;
                    font-weight: bold;
                }
                QPushButton:hover { 
                    background-color: #d32f2f; 
                }
                QPushButton:pressed { 
                    background-color: #b71c1c; 
                }
            """)
        else:
            self.stream_toggle_btn.setText("Start Stream")
            self.stream_toggle_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #4CAF50; 
                    color: white;
                    font-weight: bold;
                }
                QPushButton:hover { 
                    background-color: #45a049; 
                }
                QPushButton:pressed { 
                    background-color: #3d8b40; 
            }
            """)

    @Slot()
    def apply_manual_pwm(self):
        """Apply manual PWM control"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        try:
            self.pwm_value = self.pwm_spin.value()
            cmd = self.get_heater_cmd(f"pwm_{{heater}}_{self.pwm_value}")
            self.send_cmd_with_log(cmd)
            self.log_message(f"Sent command: {cmd}")
            self.log_message(f"Applied manual PWM to heater: {self.pwm_value}%")
            if self.pwm_value < 0:
                self.send_cmd_with_log("fan_on")

        except Exception as e:
            self.log_message(f"Error applying PWM: {e}")

    @Slot()
    def apply_pid_parameters(self):
        """Apply PID parameters to the system"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        try:
            # Get values from spin boxes
            kp = self.kp_spin.value()
            ki = self.ki_spin.value()
            kd = self.kd_spin.value()

            # Update current PID values
            self.current_kp = kp
            self.current_ki = ki
            self.current_kd = kd

            # Update display
            self.current_pid_label.setText(f"Current PID: Kp={kp:.2f}, Ki={ki:.2f}, Kd={kd:.2f}")

            # Send PID parameters to firmware
            # Format: pid_<heater_name>><kp>_<ki>_<kd>
            cmd = self.get_heater_cmd(f"pid_{{heater}}>{kp}_{ki}_{kd}")
            self.send_cmd_with_log(cmd)

            self.log_message(f"Applied PID parameters: Kp={kp:.2f}, Ki={ki:.2f}, Kd={kd:.2f}")
            self.log_message(f"Sent command: {cmd}")

            # Query the values back to confirm they were set correctly
            sleep(PID_QUERY_DELAY)  # Give the board time to process
            self.query_pid_values()

            # The pid_<heater_name>><kp>_<ki>_<kd> command automatically starts PID control
            # No need to restart PID separately

        except Exception as e:
            self.log_message(f"Error applying PID parameters: {e}")

    def update_pid_display(self):
        """Update the current PID display"""
        self.current_pid_label.setText(f"Current PID: Kp={self.current_kp:.2f}, Ki={self.current_ki:.2f}, Kd={self.current_kd:.2f}")

    def query_available_heaters(self):
        """Query available heaters from the board"""
        if not self.board or not self.board.connected:
            return

        try:
            self.send_cmd_with_log("available_heaters")
            self.log_message("Querying available heaters...")
        except Exception as e:
            self.log_message(f"Error querying available heaters: {e}")

    def query_whoami(self):
        """Ask the board to report its identity via §WHOAMI{}."""
        if not self.board or not self.board.connected:
            return
        try:
            self.board.send_cmd("whoami")
        except Exception as e:
            self.log_message(f"Error querying whoami: {e}")

    @Slot()
    def save_pid_to_board(self):
        """Persist the current PID tunings on the board to its config.json."""
        if not (self.board and self.board.connected):
            self.log_message("Not connected to device!")
            return
        if not self.current_heater:
            self.log_message("No heater selected; cannot save PID.")
            return
        cmd = f"save_pid_{self.current_heater}"
        self.send_cmd_with_log(cmd)
        self.log_message(
            f"Requested save of PID tunings for {self.current_heater} to "
            f"board flash...")

    @Slot()
    def identify_boards(self):
        """Probe every matching USB-serial port for its whoami response.
        Runs in a worker thread so the UI stays responsive."""
        self.identify_ports_btn.setEnabled(False)
        self.log_message("Identifying boards on serial ports...")
        connected_port = (
            getattr(self.board, 'port', None) if (self.board and self.board.connected)
            else None)
        cached_info = dict(self.board_info) if self.board_info else None

        def worker():
            results = {}
            for port_info in Board.list_serial_ports_filtered():
                port = port_info.device
                desc = getattr(port_info, 'description', '') or ''
                if port == connected_port and cached_info:
                    # Reuse the identity we already have for the connected
                    # board rather than fighting with the open serial port.
                    results[port] = {'info': cached_info,
                                     'description': desc}
                    continue
                results[port] = {
                    'info': self._probe_whoami_on_port(port),
                    'description': desc,
                }
            self.identify_results_signal.emit(results)

        threading.Thread(target=worker, daemon=True).start()

    def _probe_whoami_on_port(self, port):
        """Open `port` briefly, send 'whoami\\n', and parse §WHOAMI{}.
        Returns an empty dict if anything fails."""
        try:
            ser = pyserial.Serial(port, 115200, timeout=2,
                                  writeTimeout=2)
        except Exception as e:
            self.logger.debug(f"Identify: cannot open {port}: {e}")
            return {}
        try:
            ser.reset_input_buffer()
            ser.write(b"whoami\n")
            ser.flush()
            # Give the firmware time to run the command and reply.
            time.sleep(0.7)
            data = ser.read_all().decode(errors='replace')
        except Exception as e:
            self.logger.debug(f"Identify: read failed on {port}: {e}")
            data = ""
        finally:
            try:
                ser.close()
            except Exception:
                pass

        for line in data.splitlines():
            line = line.strip()
            if line.startswith('§WHOAMI'):
                j = line.find('{')
                if j >= 0:
                    try:
                        return json.loads(line[j:])
                    except Exception:
                        return {}
        return {}

    @Slot(dict)
    def _on_identify_results(self, results):
        """Re-populate the port dropdown with friendly identity labels."""
        # Remember the user's current selection so we can restore it.
        prev_port = self.port_combo.currentData()

        self.port_combo.clear()
        for port, info_dict in results.items():
            info = info_dict.get('info') or {}
            desc = info_dict.get('description') or ''
            identity = self._format_board_identity(info)
            if identity != "(unknown)":
                label = f"{identity} — {port}"
            elif desc:
                label = f"{port} — {desc}"
            else:
                label = port
            self.port_combo.addItem(label, port)

        # Restore selection by port path.
        if prev_port:
            idx = self.port_combo.findData(prev_port)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)

        self.identify_ports_btn.setEnabled(True)
        identified = sum(1 for r in results.values() if r.get('info'))
        self.log_message(
            f"Identified {identified}/{len(results)} board(s) on serial ports.")

    def parse_available_heaters(self, message):
        """Parse available heaters response from board"""
        try:
            # Expected format: "{'tec': ['tec1'], 'resistive': ['heater1']}"
            # or JSON format from telemetry
            if 'available heaters' in message.lower():
                heaters_dict = json.loads(message[message.find("{"):])
            else:
                return False

            self.available_heaters = heaters_dict
            self.log_message(f"Available heaters: {heaters_dict}")

            # Populate heater combo box
            self.heater_combo_selection.clear()
            for heater_type, heater_list in heaters_dict.items():
                for heater_name in heater_list:
                    display_name = f"{heater_name} ({heater_type})"
                    self.heater_combo_selection.addItem(display_name, (heater_name, heater_type))

            # Select first heater by default
            if self.heater_combo_selection.count() > 0:
                self.heater_combo_selection.setEnabled(True)
                first_data = self.heater_combo_selection.itemData(0)
                self.current_heater = first_data[0]
                self.current_heater_type = first_data[1]
                self.log_message(f"Selected heater: {self.current_heater}")

            return True
        except Exception as e:
            self.log_message(f"Error parsing available heaters: {e}")
            return False

    @Slot()
    def on_heater_changed(self):
        """Handle heater selection change"""
        if self.heater_combo_selection.currentIndex() >= 0:
            heater_data = self.heater_combo_selection.currentData()
            if heater_data:
                self.current_heater = heater_data[0]
                self.current_heater_type = heater_data[1]
                self.log_message(f"Heater changed to: {self.current_heater} ({self.current_heater_type})")

                # Update heater PWM label
                self.heater1_pwm_label.setText(f"{self.current_heater} PWM: --%")

                # Query PID values for new heater
                if self.board and self.board.connected:
                    QTimer.singleShot(100, self.query_pid_values)

    def query_pid_values(self):
        """Query current PID values from the board for selected heater"""
        if not self.board or not self.board.connected:
            return
        if not self.current_heater:
            return

        try:
            # Query PID tunings from firmware for current heater
            cmd = f"pid_{self.current_heater}_tunings"
            self.send_cmd_with_log(cmd)
            self.log_message(f"Querying current PID values for {self.current_heater}...")
        except Exception as e:
            self.log_message(f"Error querying PID values: {e}")

    @Slot()
    def enable_pid(self):
        """Enable PID control for the heater"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        try:
            cmd = self.get_heater_cmd("pid_{heater}_enable")
            self.send_cmd_with_log(cmd)
            self.log_message(f"PID enabled for {self.current_heater}")
        except Exception as e:
            self.log_message(f"Error enabling PID: {e}")

    @Slot()
    def disable_pid(self):
        """Disable PID control for the heater"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        try:
            cmd = self.get_heater_cmd("pid_{heater}_disable")
            self.send_cmd_with_log(cmd)
            self.pid_enabled = False
            self.log_message(f"PID disabled for {self.current_heater}")
        except Exception as e:
            self.log_message(f"Error disabling PID: {e}")

    @Slot()
    def on_sensor_group_changed(self):
        """Handle sensor group selection change"""
        sensor_group = self.sensor_group_combo.currentText()
        self.log_message(f"Sensor group changed to: {sensor_group}")

        # If stream is active, restart with the new sensor group
        if self.stream_active:
            self.log_message("Restarting stream with new sensor group...")
            self.start_stream()

    def start_pid_with_sensor_group(self, sensor_group):
        """Start PID control with specified sensor group"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        try:
            setpoint = round((self.setpoint_spin.value()  * self.compensation_rate) + self.compensation_offset, 2)

            # Handle "None" sensor group
            if sensor_group == "None":
                cmd = self.get_heater_cmd(f"pid_{{heater}}_{setpoint}")
            else:
                cmd = self.get_heater_cmd(f"pid_{{heater}}_{setpoint}_{sensor_group}")

            self.send_cmd_with_log(cmd)
            self.log_message(f"Started PID with sensor group '{sensor_group}': {cmd}")
            self.pid_active = True
        except Exception as e:
            self.log_message(f"Error starting PID with sensor group: {e}")

    def parse_pid_values(self, message):
        """Parse PID values from board response"""
        try:
            # Expected format: "PID tunings for TEC1 are Kp: 15, Ki: 2, Kd: 5"
            if "PID tunings for" in message and "are Kp:" in message:
                # Extract the values using regex or string parsing
                pattern = r"Kp:\s*([\d.]+),\s*Ki:\s*([\d.]+),\s*Kd:\s*([\d.]+)"
                match = re.search(pattern, message)

                if match:
                    kp = float(match.group(1))
                    ki = float(match.group(2))
                    kd = float(match.group(3))

                    # Update internal values
                    self.current_kp = kp
                    self.current_ki = ki
                    self.current_kd = kd

                    # Update spin boxes
                    self.kp_spin.setValue(kp)
                    self.ki_spin.setValue(ki)
                    self.kd_spin.setValue(kd)

                    # Update display
                    self.update_pid_display()

                    self.log_message(f"Retrieved PID values: Kp={kp:.4f}, Ki={ki:.4f}, Kd={kd:.4f}")
                    return True

        except (ValueError, IndexError) as e:
            self.log_message(f"Error parsing PID values: {e}")

        return False

    def add_profile_step(self, step_number=None, insert_at=None):
        """
        Build a new profile step row. If `insert_at` is given, the new step
        is placed at that index in `self.profile_steps`; otherwise it's
        appended to the end.
        """
        if not hasattr(self, 'profile_steps_layout'):
            return

        if step_number is None:
            step_number = len(self.profile_steps)

        # Create step widget
        step_widget = QWidget()
        step_layout = QHBoxLayout(step_widget)
        step_layout.setContentsMargins(0, 0, 0, 0)

        # Step number label with fixed width for alignment
        step_label = QLabel(f"Step {step_number + 1}:")
        step_label.setFixedWidth(50)
        step_layout.addWidget(step_label)

        # Temperature input with fixed width
        temp_spin = QDoubleSpinBox()
        temp_spin.setRange(0, 140)
        temp_spin.setValue(40.0)
        temp_spin.setDecimals(1)
        temp_spin.setSuffix("°C")
        temp_spin.setFixedWidth(80)
        step_layout.addWidget(temp_spin)

        # Hold time input with fixed width
        hold_spin = QSpinBox()
        hold_spin.setRange(1, 3600)
        hold_spin.setValue(60)
        hold_spin.setSuffix("s")
        hold_spin.setFixedWidth(80)
        step_layout.addWidget(hold_spin)

        # Tolerance input with fixed width
        tol_spin = QDoubleSpinBox()
        tol_spin.setRange(0.1, 5.0)
        tol_spin.setValue(1.0)
        tol_spin.setDecimals(1)
        tol_spin.setSuffix("°C")
        tol_spin.setFixedWidth(80)
        step_layout.addWidget(tol_spin)

        # Bundle radio button with fixed width
        bundle_radio = QRadioButton()
        bundle_radio.setFixedWidth(60)
        bundle_radio.setChecked(False)
        step_layout.addWidget(bundle_radio)

        # Repeats spinbox with fixed width (disabled by default, only for bundles)
        repeats_spin = QSpinBox()
        repeats_spin.setRange(1, 100)
        repeats_spin.setValue(1)
        repeats_spin.setFixedWidth(60)
        repeats_spin.setEnabled(False)  # Disabled by default
        step_layout.addWidget(repeats_spin)

        # Connect bundle radio to enable/disable repeats
        def toggle_repeats(checked):
            repeats_spin.setEnabled(checked)
            if not checked:
                repeats_spin.setValue(1)  # Reset to 1 when unchecked

        bundle_radio.toggled.connect(toggle_repeats)

        # Per-row insert / delete buttons. They look up the row by the
        # step_data reference rather than an index, so reordering doesn't
        # break their wiring.
        insert_btn = QPushButton("+")
        insert_btn.setFixedWidth(28)
        insert_btn.setToolTip("Insert a new step above this one")
        step_layout.addWidget(insert_btn)

        delete_btn = QPushButton("✕")
        delete_btn.setFixedWidth(28)
        delete_btn.setToolTip("Delete this step")
        step_layout.addWidget(delete_btn)

        step_layout.addStretch()

        # Store step data
        step_data = {
            'widget': step_widget,
            'layout': step_layout,
            'temp_spin': temp_spin,
            'hold_spin': hold_spin,
            'tol_spin': tol_spin,
            'bundle_radio': bundle_radio,
            'repeats_spin': repeats_spin,
            'insert_btn': insert_btn,
            'delete_btn': delete_btn,
            'step_number': step_number,
        }

        # Connect per-row buttons now that step_data exists.
        insert_btn.clicked.connect(
            lambda _checked=False, sd=step_data: self.insert_profile_step_above(sd))
        delete_btn.clicked.connect(
            lambda _checked=False, sd=step_data: self.delete_profile_step(sd))

        if insert_at is None or insert_at >= len(self.profile_steps):
            self.profile_steps.append(step_data)
            self.profile_steps_layout.addWidget(step_widget)
        else:
            self.profile_steps.insert(insert_at, step_data)
            self.profile_steps_layout.insertWidget(insert_at, step_widget)

        # Update scroll area height based on number of steps
        self.update_profile_scroll_height()

        # Update step numbers
        self.update_profile_step_numbers()

        return step_data

    def update_profile_scroll_height(self):
        """Update scroll area height based on number of steps"""
        num_steps = len(self.profile_steps)
        if num_steps <= 3:
            # Show all steps without scrollbar
            self.profile_scroll_area.setMaximumHeight(200)
        else:
            # Show scrollbar for more than 3 steps
            self.profile_scroll_area.setMaximumHeight(200)
            self.profile_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def remove_profile_step(self):
        """Remove the last temperature profile step (legacy 'Remove Step' button)."""
        if len(self.profile_steps) <= 1:
            return  # Keep at least one step

        step_data = self.profile_steps.pop()
        step_data['widget'].setParent(None)
        step_data['widget'].deleteLater()

        # Update scroll area height
        self.update_profile_scroll_height()

        # Update step numbers
        self.update_profile_step_numbers()

    def insert_profile_step_above(self, ref_step):
        """Insert a new step before `ref_step` in the profile list."""
        if ref_step not in self.profile_steps:
            return
        idx = self.profile_steps.index(ref_step)
        # If running, refuse to insert before/at the currently executing step
        # — otherwise the execution sequence's indices get out from under us.
        if self.profile_active and idx <= self.current_profile_step:
            self.log_message(
                "Cannot insert above the current or past steps while the "
                "profile is running.")
            return
        new_step = self.add_profile_step(insert_at=idx)
        if new_step is not None:
            self.log_message(f"Inserted new step at position {idx + 1}")

    def delete_profile_step(self, ref_step):
        """Delete the row that owns `ref_step` from the profile list."""
        if ref_step not in self.profile_steps:
            return
        if len(self.profile_steps) <= 1:
            self.log_message("Cannot delete the last remaining step.")
            return
        idx = self.profile_steps.index(ref_step)
        if self.profile_active and idx <= self.current_profile_step:
            self.log_message(
                "Cannot delete the current or past steps while the profile "
                "is running. Use 'Skip Step' to advance instead.")
            return
        self.profile_steps.pop(idx)
        ref_step['widget'].setParent(None)
        ref_step['widget'].deleteLater()
        self.update_profile_scroll_height()
        self.update_profile_step_numbers()
        self.log_message(f"Deleted step {idx + 1}")

    @Slot()
    def skip_current_profile_step(self):
        """Skip the currently executing profile step, immediately advancing
        to the next item in the execution sequence."""
        if not self.profile_active:
            return
        self.log_message(
            f"User skipped step {self.current_profile_step + 1}; advancing.")
        # Reset the hold-time accounting on the current step so the next
        # entry into it (if any, via a bundle repeat) starts cleanly.
        try:
            step_data = self.profile_steps[self.current_profile_step]
            step_data['hold_start_time'] = None
            step_data['step_start_time'] = None
        except (IndexError, KeyError):
            pass
        self.move_to_next_execution_step()

    def update_profile_step_numbers(self):
        """Update step number labels"""
        for i, step_data in enumerate(self.profile_steps):
            step_data['step_number'] = i
            # Find the step label (first widget in the layout)
            if step_data['layout'].count() > 0:
                step_label = step_data['layout'].itemAt(0).widget()
                if isinstance(step_label, QLabel):
                    step_label.setText(f"Step {i + 1}:")

    @Slot()
    def start_temperature_profile(self):
        """Start the temperature profile"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        if len(self.profile_steps) == 0:
            self.log_message("No profile steps defined!")
            return

        if self.profile_active:
            self.log_message("Profile already running!")
            return

        try:
            self.clear_plot()
            # Validate profile steps
            for step_data in self.profile_steps:
                temp = step_data['temp_spin'].value()
                hold = step_data['hold_spin'].value()
                tol = step_data['tol_spin'].value()

                if temp < 0 or temp > 140:
                    self.log_message(f"Invalid temperature {temp} ±{tol}°C in step {step_data['step_number'] + 1}")
                    return

                if hold < 1:
                    self.log_message(f"Invalid hold time {hold}s in step {step_data['step_number'] + 1}")
                    return

            # Process profile steps into execution sequence
            self.execution_sequence = self.process_profile_bundles()

            # Start profile
            self.profile_active = True
            self.current_execution_index = 0
            self.current_profile_step = 0

            # Update UI
            self.start_profile_btn.setEnabled(False)
            self.stop_profile_btn.setEnabled(True)
            self.skip_step_btn.setEnabled(True)
            self.profile_status_label.setText("Profile: Running")
            self.profile_status_label.setStyleSheet("color: orange; font-weight: bold;")

            self.log_message(f"Starting profile with {len(self.profile_steps)} steps")
            # Store previous stream state to resume after profile
            self.pre_profile_stream_state = self.stream_active
            self.send_cmd_with_log("stream_stop")
            sleep(COMMAND_DELAY_SHORT)
            self.execute_profile_step()

            self.log_message("Temperature profile started")

        except Exception as e:
            self.log_message(f"Error starting profile: {e}")

    def process_profile_bundles(self):
        """Process profile steps into execution sequence - bundles can repeat, single steps execute once"""
        execution_sequence = []

        i = 0
        while i < len(self.profile_steps):
            step_data = self.profile_steps[i]

            if step_data['bundle_radio'].isChecked():
                # This step starts a bundle - find consecutive checked steps
                bundle_start = i
                bundle_steps = []

                # Find the end of the bundle (consecutive checked steps)
                while (i < len(self.profile_steps) and 
                       self.profile_steps[i]['bundle_radio'].isChecked()):
                    bundle_steps.append(i)
                    i += 1

                # Get the repeat count from the first step in the bundle
                bundle_repeats = self.profile_steps[bundle_start]['repeats_spin'].value()

                # Add bundle to execution sequence
                execution_sequence.append({
                    'type': 'bundle',
                    'steps': bundle_steps,
                    'repeats': bundle_repeats,
                    'current_repeat': 0,
                    'current_step_in_bundle': 0
                })
            else:
                # Single step - execute once (no repeats)
                execution_sequence.append({
                    'type': 'single',
                    'step': i,
                    'repeats': 1,  # Single steps always execute once
                    'current_repeat': 0
                })
                i += 1

        return execution_sequence

    @Slot()
    def stop_temperature_profile(self):
        """Stop the temperature profile"""
        if not self.profile_active:
            return

        try:
            self.profile_active = False
            self.current_profile_step = 0

            # Stop PID control
            if self.board and self.board.connected:
                cmd = self.get_heater_cmd("pid_{heater}_stop")
                self.send_cmd_with_log(cmd)

            self.pid_enabled = False

            # Update UI
            self.start_profile_btn.setEnabled(True)
            self.stop_profile_btn.setEnabled(False)
            self.skip_step_btn.setEnabled(False)
            self.profile_status_label.setText("Profile: Stopped")
            self.profile_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.current_step_label.setText("Current Step: --")

            # Resume previous stream state
            if self.pre_profile_stream_state:
                self.log_message("Resuming previous stream state after profile...")
                self.restore_stream_state()

            self.log_message("Temperature profile stopped")

        except Exception as e:
            self.log_message(f"Error stopping profile: {e}")

    def restore_stream_state(self):
        """Restore stream state without sending commands (used after profile stops)"""
        # Just update the button state to reflect that stream should be active
        self.set_stream_active(True)
        self.log_message("Stream state restored (no commands sent)")

    def execute_profile_step(self):
        """Execute the current profile step (now handles execution sequence)"""
        if not self.profile_active or self.current_execution_index >= len(self.execution_sequence):
            self.log_message(f"Profile execution stopped: active={self.profile_active}, index={self.current_execution_index}, total_items={len(self.execution_sequence)}")
            self.stop_temperature_profile()
            return

        try:
            current_item = self.execution_sequence[self.current_execution_index]

            if current_item['type'] == 'bundle':
                # Execute current step in bundle
                step_idx = current_item['steps'][current_item['current_step_in_bundle']]

                self.log_message(f"Executing bundle {self.current_execution_index + 1}, step {step_idx + 1}, repeat {current_item['current_repeat'] + 1}/{current_item['repeats']}")

                # Update display
                self.current_step_label.setText(f"Bundle {self.current_execution_index + 1}: Step {step_idx + 1}, Repeat {current_item['current_repeat'] + 1}/{current_item['repeats']}")
            else:
                step_idx = current_item['step']

                self.log_message(f"Executing single step {step_idx + 1}")

                # Update display
                self.current_step_label.setText(f"Step {step_idx + 1}")

            step_data = self.profile_steps[step_idx]
            target_temp = step_data['temp_spin'].value()
            hold_time = step_data['hold_spin'].value()
            tolerance = step_data['tol_spin'].value()
            step_data['hold_start_time'] = None
            step_data['step_start_time'] = datetime.now()

            # Set temperature
            self.setpoint_spin.setValue(target_temp)
            target_temp = round((target_temp * self.compensation_rate) + self.compensation_offset, 2)
            self.current_setpoint = target_temp

            # Change setpoint (PID should already be running)
            sensor_group = self.sensor_group_combo.currentText()
            if sensor_group == "None":
                cmd = self.get_heater_cmd(f"pid_{{heater}}_{target_temp}")
            else:
                cmd = self.get_heater_cmd(f"pid_{{heater}}_{target_temp}_{sensor_group}")
            self.send_cmd_with_log(cmd)
            self.pid_enabled = True
            self.current_profile_step = step_idx

            if current_item['type'] == 'bundle':
                self.log_message(f"Bundle Step {step_idx + 1}: Target {target_temp}°C, Hold {hold_time}s, Tolerance ±{tolerance}°C")

            else:
                self.log_message(f"Single Step {step_idx + 1}: Target {target_temp}°C, Hold {hold_time}s, Tolerance ±{tolerance}°C")

        except Exception as e:
            self.log_message(f"Error executing profile step: {e}")

    def check_profile_step(self, temp_data=0):
        """Check if current profile step is complete (now handles execution sequence)"""
        if not self.profile_active:
            return

        try:
            step_data = self.profile_steps[self.current_profile_step]
            target_temp = round((step_data['temp_spin'].value() * self.compensation_rate) + self.compensation_offset, 2)
            tolerance = step_data['tol_spin'].value()

            # Check if temperature is within tolerance
            temp_diff = abs(temp_data - target_temp)
            if temp_diff <= tolerance:
                # Temperature reached, start hold timer
                if step_data.get('hold_start_time', None) is None:
                    step_data['hold_start_time'] = datetime.now()
                    self.log_message(f"Temperature reached! Holding for {step_data['hold_spin'].value()}s...")

            # Calculate elapsed times
            step_start_time = step_data.get('step_start_time', None)
            hold_start_time = step_data.get('hold_start_time', None)

            if step_start_time:
                total_elapsed = (
                    datetime.now() - step_start_time).total_seconds()
            else:
                total_elapsed = 0

            if hold_start_time:
                hold_elapsed = (
                    datetime.now() - hold_start_time).total_seconds()
            else:
                hold_elapsed = 0

            # Update step label with elapsed times
            current_item = self.execution_sequence[
                self.current_execution_index]
            if current_item['type'] == 'bundle':
                step_idx = self.current_profile_step
                repeat_info = (f"{current_item['current_repeat'] + 1}/"
                               f"{current_item['repeats']}")
                label_text = (f"Bundle {self.current_execution_index + 1}: "
                              f"Step {step_idx + 1}, Repeat {repeat_info} | "
                              f"Total: {int(total_elapsed)}s")
                if hold_start_time:
                    label_text += f" | Hold: {int(hold_elapsed)}s"
                label_text += f" | Target: {target_temp}°C, Tolerance ±{tolerance}°C"
            else:
                step_idx = self.current_profile_step
                label_text = (f"Step {step_idx + 1} | "
                              f"Total: {int(total_elapsed)}s")
                if hold_start_time:
                    label_text += f" | Hold: {int(hold_elapsed)}s"

            self.current_step_label.setText(label_text)

            # Check if hold time is complete
            if hold_elapsed >= step_data['hold_spin'].value():
                # Step complete, move to next step in execution sequence
                self.log_message(f"Step {self.current_profile_step + 1} complete!")
                self.move_to_next_execution_step()

        except Exception as e:
            self.log_message(f"Error checking profile step: {e}")

    def move_to_next_execution_step(self):
        """Move to next step in execution sequence"""
        if not self.profile_active:
            return

        current_item = self.execution_sequence[self.current_execution_index]

        if current_item['type'] == 'bundle':
            # Check if we've completed all steps in the bundle
            if current_item['current_step_in_bundle'] < len(current_item['steps']) - 1:
                # Move to next step in bundle
                current_item['current_step_in_bundle'] += 1
                self.execute_profile_step()
            else:
                # All steps in bundle complete, check repeats
                current_item['current_repeat'] += 1

                if current_item['current_repeat'] < current_item['repeats']:
                    # Repeat bundle from beginning
                    self.log_message(f"Bundle repeat {current_item['current_repeat'] + 1}/{current_item['repeats']} complete, repeating...")
                    current_item['current_step_in_bundle'] = 0  # Start from first step
                    self.execute_profile_step()
                else:
                    # Bundle complete, move to next execution item
                    self.log_message(f"Bundle {self.current_execution_index + 1} complete!")
                    self.current_execution_index += 1
                    self.execute_profile_step()
        else:
            # Single step complete, move to next execution item (no repeats for single steps)
            self.log_message(f"Single step {current_item['step'] + 1} complete!")
            self.current_execution_index += 1
            self.execute_profile_step()

    def serialize_profile(self):
        """Serialize current profile steps to JSON-compatible dictionary"""
        profile_data = {
            'profile_name': 'Temperature Profile',
            'version': '1.0',
            'steps': []
        }

        for step_data in self.profile_steps:
            step_dict = {
                'temperature': step_data['temp_spin'].value(),
                'hold_time': step_data['hold_spin'].value(),
                'tolerance': step_data['tol_spin'].value(),
                'is_bundle': step_data['bundle_radio'].isChecked(),
                'repeats': step_data['repeats_spin'].value()
            }
            profile_data['steps'].append(step_dict)

        return profile_data

    def deserialize_profile(self, profile_data):
        """Deserialize profile data and recreate profile steps"""
        # Clear existing steps
        while len(self.profile_steps) > 0:
            step_data = self.profile_steps.pop()
            step_data['widget'].setParent(None)
            step_data['widget'].deleteLater()

        # Create steps from loaded data
        for step_dict in profile_data.get('steps', []):
            step_data = self.add_profile_step()
            step_data['temp_spin'].setValue(step_dict.get('temperature', 40.0))
            step_data['hold_spin'].setValue(step_dict.get('hold_time', 60))
            step_data['tol_spin'].setValue(step_dict.get('tolerance', 1.0))
            step_data['bundle_radio'].setChecked(step_dict.get('is_bundle', False))
            step_data['repeats_spin'].setValue(step_dict.get('repeats', 1))

        # Update scroll area
        self.update_profile_scroll_height()
        self.update_profile_step_numbers()

    @Slot()
    def save_profile(self):
        """Save current profile to JSON file"""
        if len(self.profile_steps) == 0:
            self.log_message("No profile steps to save!")
            return

        try:
            # Create profiles directory if it doesn't exist
            profiles_dir = Path("profiles")
            profiles_dir.mkdir(exist_ok=True)

            # Open file dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Temperature Profile",
                str(profiles_dir / "profile.json"),
                "JSON Files (*.json)"
            )

            if file_path:
                # Serialize profile
                profile_data = self.serialize_profile()

                # Save to file
                with open(file_path, 'w') as f:
                    json.dump(profile_data, f, indent=2)

                self.log_message(f"Profile saved to: {file_path}")

        except Exception as e:
            self.log_message(f"Error saving profile: {e}")
            print(traceback.format_exc())

    @Slot()
    def load_profile(self):
        """Load profile from JSON file"""
        try:
            # Create profiles directory if it doesn't exist
            profiles_dir = Path("profiles")
            profiles_dir.mkdir(exist_ok=True)

            # Open file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Load Temperature Profile",
                str(profiles_dir),
                "JSON Files (*.json)"
            )

            if file_path:
                # Load from file
                with open(file_path, 'r') as f:
                    profile_data = json.load(f)

                # Deserialize profile
                self.deserialize_profile(profile_data)

                self.log_message(f"Profile loaded from: {file_path}")

        except Exception as e:
            self.log_message(f"Error loading profile: {e}")
            print(traceback.format_exc())

    @Slot()
    def fan_on(self):
        """Turn fan on"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        try:
            cmd = "fan_on"
            self.send_cmd_with_log(cmd)
            self.log_message(f"Sent command: {cmd}")
            self.fan_status_label.setText("Fan: ON")

        except Exception as e:
            self.log_message(f"Error turning fan on: {e}")

    @Slot()
    def fan_off(self):
        """Turn fan off"""
        if not self.board or not self.board.connected:
            self.log_message("Not connected to device!")
            return

        try:
            cmd = "fan_off"
            self.send_cmd_with_log(cmd)
            self.log_message(f"Sent command: {cmd}")
            self.fan_status_label.setText("Fan: OFF")

        except Exception as e:
            self.log_message(f"Error turning fan off: {e}")

    @Slot(float)
    def on_setpoint_changed(self, value):
        """Handle setpoint changes"""
        value = round((value * self.compensation_rate) + self.compensation_offset, 2)
        self.current_setpoint = value

        # If PID is enabled and stream is active, update the setpoint on the device
        if self.pid_toggle_btn.isChecked() and self.stream_active and self.pid_active:
            sensor_group = self.sensor_group_combo.currentText()
            if sensor_group == "None":
                cmd = self.get_heater_cmd(f"pid_{{heater}}_{value}")
            else:
                cmd = self.get_heater_cmd(f"pid_{{heater}}_{value}_{sensor_group}")
            self.send_cmd_with_log(cmd)
            self.log_message(f"Setpoint changed to {value}°C and sent to device")
        else:
            self.log_message(f"Setpoint changed to {value}°C (will apply when PID starts)")

    @Slot(bool)
    def on_pid_toggled(self, checked):
        """Handle PID control checkbox toggle"""
        self.pid_enabled = checked

        # If stream is active, restart with the new mode
        if self.stream_active:
            self.log_message(f"PID mode {'enabled' if checked else 'disabled'}, restarting stream...")
            self.start_stream()
        else:
            # Just log that the setting has changed
            self.log_message(f"PID mode {'enabled' if checked else 'disabled'} (will apply on next stream start)")

    @Slot(bool)
    def on_logging_toggled(self, checked):
        """Handle data logging toggle"""
        self.is_logging = checked
        if checked:
            self.data_logger.start_logging()
            self.log_message("Started data logging")
        else:
            self.data_logger.stop_logging()
            self.log_message("Stopped data logging")

    @Slot()
    def open_log_folder(self):
        """Open the log folder"""
        try:
            log_path = self.data_logger.log_dir.absolute()

            if platform.system() == "Windows":
                subprocess.run(["explorer", str(log_path)])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", str(log_path)])
            else:  # Linux
                subprocess.run(["xdg-open", str(log_path)])

        except Exception as e:
            self.log_message(f"Error opening log folder: {e}")

    @Slot()
    def clear_plot(self):
        """Clear the plot data and reset the display"""
        try:
            if hasattr(self, 'plot_widget') and self.plot_widget:
                # Clear all data arrays
                self.plot_widget.timestamps.clear()
                self.plot_widget.sensor_data.clear()
                self.plot_widget.pid_temp_data.clear()
                self.plot_widget.heater1_pwm_data.clear()
                self.plot_widget.heater2_pwm_data.clear()
                self.plot_widget.setpoint_data.clear()

                # Clear the plot display
                self.plot_widget.ax1.clear()
                self.plot_widget.ax2.clear()

                # Reset plot appearance
                self.plot_widget.setup_plots()
                self.plot_widget.fig.tight_layout()
                self.plot_widget.draw()

                self.last_timestamp = 0
            else:
                self.log_message("Plot widget not available")

        except Exception as e:
            self.log_message(f"Error clearing plot: {e}")

    def log_message(self, message):
        """Add message to log display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.log_display.append(formatted_message)

        # Auto-scroll to bottom
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def get_heater_cmd(self, cmd_template):
        """Generate heater-specific command using current heater selection
        
        Args:
            cmd_template: Command template with {heater} placeholder
                         e.g. "pid_{heater}_enable" or "pwm_{heater}_50"
        
        Returns:
            Command string with heater name substituted
        """
        if not self.current_heater:
            # Fallback to tec1 if no heater selected
            return cmd_template.replace("{heater}", "tec1")
        return cmd_template.replace("{heater}", self.current_heater)

    def _build_menu_bar(self):
        menu_bar = self.menuBar()
        tools_menu = menu_bar.addMenu("&Tools")
        sensor_cfg_action = QAction("Configure 1-Wire Sensors...", self)
        sensor_cfg_action.triggered.connect(self._open_sensor_config_dialog)
        tools_menu.addAction(sensor_cfg_action)

    def _open_sensor_config_dialog(self):
        dialog = SensorConfigDialog(self.board, self)
        dialog.exec()

    def send_cmd_with_log(self, command):
        """Send command to board and log it"""
        try:
            self.board.send_cmd(command)
            self.log_message(f"[DEBUG]: {command}")

            # Update stream button state when stream_stop is sent
            if command == "stream_stop":
                self.set_stream_active(False)

        except Exception as e:
            self.log_message(f"Error sending command '{command}': {e}")

    def closeEvent(self, event):
        """Handle application close"""
        try:
            # Stop animation first
            if hasattr(self, 'plot_widget') and self.plot_widget:
                self.plot_widget.stop_animation()

            if self.board:
                self.board.close()
            if self.is_logging:
                self.data_logger.stop_logging()
        except Exception as e:
            print(f"Error during close: {e}")

        event.accept()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)

    # Set application properties
    app.setApplicationName("Heater Control System")
    app.setApplicationVersion("1.0")

    # Create and show main window
    window = HeaterControlUI()
    window.show()

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
