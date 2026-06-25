# -*- coding: utf-8 -*-
# Standard library imports
import os
import re
import io
import sys
import json
import time
import asyncio
import logging
import threading
import importlib

from pathlib import Path
from contextlib import redirect_stdout

# Third-party imports
import yaml
import serial
import serial.tools.list_ports
from bleak import BleakClient, BleakScanner

# Local application imports
from fail_safe import fail_safe
from PySide6.QtCore import QObject, Signal, Slot

# Silence bleak debug messages
logging.getLogger('bleak').setLevel(logging.WARNING)

serial_echo = logging.getLogger("telemetry")
serial_echo.setLevel(logging.INFO)          # will only print json packets

# UART UUIDs used by the BLE UART service
UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write to this characteristic (device RX)
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Read from this characteristic (device TX)


class Board(QObject):
    # Define signals for thread-safe communication
    connection_changed = Signal(bool)
    status_message = Signal(str)
    upload_progress = Signal(int, int)  # (current_file, total_files)
    upload_file_progress = Signal(int, int, str)  # (current_bytes, total_bytes, filename)
    reconnect_signal = Signal()  # New signal to trigger reconnection
    callback_signal = Signal(bool, object)  # New signal for callbacks (success, callback_func)
    telemetry = Signal(dict)
    message_received = Signal(str)
    # Connection modes
    MODE_BLUETOOTH = "bluetooth"
    MODE_SERIAL = "serial"

    # Constants
    DEFAULT_BAUDRATE = 115200
    SERIAL_TIMEOUT = 2.0
    SERIAL_WRITE_TIMEOUT = 2.0
    MESSAGE_TIMEOUT = 0.5  # Seconds to wait for more data before considering a message complete
    MAX_COMMAND_RETRIES = 3
    DEFAULT_CONNECTION_TIMEOUT = 10.0
    SHORT_CONNECTION_TIMEOUT = 4.0
    QUICK_RECONNECT_TIMEOUT = 3.0
    RECONNECT_TIMEOUT = 5.0
    BLE_DISCOVERY_TIMEOUT = 5.0
    BLE_SERVICE_DISCOVERY_DELAY = 0.5
    COMMAND_RETRY_DELAY = 0.5
    SERIAL_RESPONSE_DELAY = 0.2
    REPL_ENTER_DELAY = 0.1
    REPL_RETRY_DELAY = 0.5
    FIRMWARE_UPLOAD_DELAY = 1.0
    FIRMWARE_UPLOAD_RETRY_DELAY = 1.0
    FIRMWARE_UPLOAD_MAX_TRIES = 10
    RECEIVE_BUFFER_THRESHOLD = 500
    EVENT_LOOP_FUTURE_TIMEOUT = 10.0
    CONNECTION_THREAD_JOIN_TIMEOUT = 3.0
    SERIAL_VID_PID_PATTERN = r'(?:vid:pid=?|vid[_:]?)(?P<vid>[0-9a-f]+)(?:(?:[_&:=+]?)|(?:[_&:=+]?pid[_:]))(?P<pid>[0-9a-f]+)'

    def __init__(self, addr, port=None, baudrate=115200,
                 characteristic_uuid=None, logger=None,
                 connection_mode=None, config_path='config.yml', device_name="Controller"):
        """Initialize the controller for Bluetooth or Serial communication
        
        Args:
            addr: Bluetooth device address or serial port name
            port: Serial port name (used when connection_mode is explicitly set to serial)
            baudrate: Serial baudrate when in serial mode, ignored for Bluetooth
            characteristic_uuid: UUID for the Bluetooth write characteristic
            logger: Logger instance
            connection_mode: Force connection mode, "bluetooth" or "serial"
            config_path: Path to the config file
        """
        super().__init__()  # Initialize QObject
        self.address = addr
        self.port = port  # Store port separately from baudrate
        self.baudrate = baudrate  # Store baudrate separately
        self.client = None
        self.serial_port = None
        self.loop = None  # Will be initialized in setup
        self._connected = False
        self.connection_thread = None
        self.connecting = False
        self.characteristic_uuid = characteristic_uuid
        self._loop_lock = threading.Lock()  # Add lock for event loop access
        self.config_path = config_path
        self.device_name = device_name
        
        # Serial device identifiers
        self.vid = None  # Vendor ID
        self.pid = None  # Product ID

        # Track if Bluetooth has been tried to avoid retries
        self._bt_tried = False

        # BLE UART settings
        self.message_timeout = self.MESSAGE_TIMEOUT
        self.receive_buffer = ""
        self.message_complete = False
        self.rx_event = asyncio.Event()

        # Task tracking
        self._message_complete_tasks = set()  # Track all message complete check tasks
        self._task_lock = threading.Lock()  # Lock for task set access

        # Set the connection mode (Bluetooth or Serial)
        self.connection_mode = connection_mode

        # Set up logger - only use the provided logger or get the existing one
        self.logger = logger if logger is not None else logging.getLogger(__name__)

        # Connect signals to slots
        self.reconnect_signal.connect(self._reconnect_slot)
        self.callback_signal.connect(self._callback_slot)

        # Load VID/PID from config if available
        self._load_device_ids_from_config()

    def _is_bluetooth_uuid(self, address):
        """Check if an address is a Bluetooth UUID format.

        Args:
            address: Address string to check

        Returns:
            bool: True if address is a Bluetooth UUID, False otherwise
        """
        return len(address) == 36 and address.count('-') == 4

    def _is_bluetooth_mac(self, address):
        """Check if an address is a Bluetooth MAC address format.

        Args:
            address: Address string to check

        Returns:
            bool: True if address is a Bluetooth MAC, False otherwise
        """
        return len(address) == 17 and address.count(':') == 5

    def _create_serial_port(self, port, baudrate, timeout=None, write_timeout=None):
        """Create a serial port connection with standard settings.

        Args:
            port: Port name to open
            baudrate: Baudrate to use
            timeout: Read timeout (defaults to SERIAL_TIMEOUT)
            write_timeout: Write timeout (defaults to SERIAL_WRITE_TIMEOUT)

        Returns:
            serial.Serial: Serial port object if successful, None otherwise
        """
        try:
            if timeout is None:
                timeout = self.SERIAL_TIMEOUT
            if write_timeout is None:
                write_timeout = self.SERIAL_WRITE_TIMEOUT

            return serial.Serial(
                port=port,
                baudrate=int(baudrate),
                timeout=timeout,
                writeTimeout=write_timeout
            )
        except Exception as e:
            self.logger.error(f"Error creating serial port {port}: {e}")
            return None

    def _reopen_serial_port(self, port, baudrate):
        """Reopen a serial port with standard settings.

        Args:
            port: Port name to open
            baudrate: Baudrate to use

        Returns:
            bool: True if successfully opened, False otherwise
        """
        self.logger.info(f"Reopening serial port {port}")
        self.serial_port = self._create_serial_port(port, baudrate)
        if self.serial_port and self.serial_port.is_open:
            self._connected = True
            self.logger.info(f"Successfully reopened serial port {port}")
            return True
        else:
            self.logger.warning("Serial port didn't reopen properly")
            return False

    def _emit_connection_status(self, connected, message=None):
        """Helper method to emit connection status and message.

        Args:
            connected: Connection status (bool)
            message: Optional status message to emit
        """
        self.connection_changed.emit(connected)
        if message:
            self.status_message.emit(message)

    @property
    def connected(self):
        # check if serial port is open
        if self.connection_mode == self.MODE_SERIAL:
            self._connected = self.serial_port and self.serial_port.is_open
        else:
            # check if client is connected
            self._connected = self.client and self.client.is_connected
        return self._connected

    @Slot()
    def _reconnect_slot(self):
        """Slot to handle reconnection requests from threads"""
        try:
            self.logger.info("Reconnecting from signal request")

            # If we were previously connected in serial mode, reopen that specific port
            if self.connection_mode == self.MODE_SERIAL and hasattr(self, 'serial_port') and self.serial_port:
                port_to_use = self.serial_port.port if hasattr(self.serial_port, 'port') else self.address

                # Extra logging
                self.logger.info(f"Reopening serial port {port_to_use} at {self.baudrate} baud")
                self.status_message.emit(f"Reconnecting to {port_to_use}...")

                # Close the serial port if it's open
                if hasattr(self.serial_port, 'is_open') and self.serial_port.is_open:
                    self.serial_port.close()

                # Try to reopen the port with a small delay
                time.sleep(self.COMMAND_RETRY_DELAY)
                if self._reopen_serial_port(port_to_use, self.baudrate):
                    self.logger.info(f"Successfully reconnected to {port_to_use}")
                    self._emit_connection_status(True, f"Reconnected to {port_to_use}")
                    return

            # Fall back to regular setup if direct reconnection fails
            self.setup()
        except Exception as e:
            self.logger.error(f"Error in reconnection slot: {e}")
            # Last resort fallback - try a completely fresh connection
            try:
                self.logger.info("Attempting full reconnection")
                if self.connection_mode == self.MODE_SERIAL:
                    self._connect_serial()
                else:
                    self.setup()
            except Exception as inner_e:
                self.logger.error(f"Final reconnection attempt failed: {inner_e}")

    @Slot(bool, object)
    def _callback_slot(self, success, callback_func):
        """Slot to safely execute callbacks on the main thread
        
        Args:
            success: Success status to pass to the callback
            callback_func: The callback function to call
        """
        try:
            if callback_func:
                callback_func(success)
        except Exception as e:
            self.logger.error(f"Error executing callback: {e}")

    def _load_device_ids_from_config(self):
        """Load device identifiers from config file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as file:
                    config = yaml.safe_load(file)

                if config and 'serial' in config:
                    if 'vid' in config['serial']:
                        self.vid = config['serial']['vid']
                        self.logger.debug(f"Loaded VID from config: {self.vid}")
                    if 'pid' in config['serial']:
                        self.pid = config['serial']['pid']
                        self.logger.debug(f"Loaded PID from config: {self.pid}")
        except Exception as e:
            self.logger.error(f"Error loading device IDs from config: {e}")

    def _save_device_ids_to_config(self):
        """Save device identifiers to config file"""
        try:
            config = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as file:
                    config = yaml.safe_load(file) or {}

            # Create serial section if it doesn't exist
            if 'serial' not in config:
                config['serial'] = {}

            # Update VID/PID
            if self.vid is not None:
                config['serial']['vid'] = self.vid
            if self.pid is not None:
                config['serial']['pid'] = self.pid

            # Save the updated config
            with open(self.config_path, 'w') as file:
                yaml.dump(config, file, default_flow_style=False)

            self.logger.info(f"Saved device IDs to config: VID={self.vid}, PID={self.pid}")
        except Exception as e:
            self.logger.error(f"Error saving device IDs to config: {e}")

    def _get_event_loop(self):
        """Get a new event loop or create one if it doesn't exist
        
        Returns:
            asyncio.AbstractEventLoop: The event loop to use
        """
        with self._loop_lock:
            if self.loop is None or self.loop.is_closed():
                self.loop = asyncio.new_event_loop()
            return self.loop

    def _run_coroutine(self, coroutine, wait_for_result=True):
        """Safely run a coroutine in the event loop
        
        Args:
            coroutine: The coroutine to run
            wait_for_result: If False, schedule the coroutine and return immediately.

        Returns:
            The result of the coroutine if wait_for_result is True, else None
        """
        # Skip if using serial - no coroutines needed
        if self.connection_mode == self.MODE_SERIAL:
            return None

        loop = self._get_event_loop()

        # Check if we're in the same thread as the loop
        if threading.current_thread() is threading.main_thread() and loop.is_running():
            # We can't use run_until_complete in a running loop
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
            if wait_for_result:
                # self.logger.debug("Event loop already running, using future and waiting for result")
                return future.result(self.EVENT_LOOP_FUTURE_TIMEOUT)  # Wait up to EVENT_LOOP_FUTURE_TIMEOUT seconds for result
            else:
                self.logger.debug("Event loop already running, scheduling coroutine without waiting")
                return None
        else:
            return loop.run_until_complete(coroutine)

    def _find_serial_device_by_vid_pid(self):
        """Find a serial device by VID and PID
        
        Returns:
            str: Serial port path if found, None otherwise
        """
        if not self.vid and not self.pid:
            self.logger.warning("No VID/PID specified for serial device detection")
            return None

        try:
            ports = self._get_available_serial_ports()
            if len(ports) and self.vid is None and self.pid is None:
                self.logger.info(f"Auto-selected serial port: {ports[0].device}")
                self.status_message.emit(f"Auto-selected serial port: {ports[0].device}")
                return ports[0].device

            for port in ports:
                # Check if VID/PID matches
                if self.vid is None:
                    vid_match = True
                else:
                    vid_match = f"{port.vid:04x}".lower() == str(self.vid).lower()

                if self.pid is None:
                    pid_match = True
                else:
                    pid_match = f"{port.pid:04x}".lower() == str(self.pid).lower()

                if vid_match and pid_match:
                    self.logger.info(f"Found matching serial device: {port.device} ({port.description})")
                    self.status_message.emit(f"Found matching serial device: {port.device}")
                    return port.device

            self.logger.warning(f"No serial device found with VID={self.vid}, PID={self.pid}")
            self.status_message.emit(f"No serial device found with VID={self.vid}, PID={self.pid}")
            return None
        except Exception as e:
            self.logger.error(f"Error finding serial device by VID/PID: {e}")
            return None

    def _get_available_serial_ports(self):
        """Get available serial ports matching USB serial device pattern.

        Returns:
            list: List of serial port objects, or empty list if none found
        """
        try:
            # Use grep to filter for USB serial devices (more elegant than manual filtering)
            # Pattern matches VID/PID in hardware ID (from connections.py pattern)
            ports = list(serial.tools.list_ports.grep(self.SERIAL_VID_PID_PATTERN))
            return ports
        except Exception as e:
            self.logger.debug(f"Error getting serial ports: {e}")
            return []

    @staticmethod
    def list_serial_ports_filtered():
        """List serial ports filtered to likely board devices (VID/PID-present entries).

        Returns:
            list: List of serial port objects filtered similarly to _get_available_serial_ports().
        """
        try:
            return list(serial.tools.list_ports.grep(Board.SERIAL_VID_PID_PATTERN))
        except Exception:
            return []

    def setup(self, only_once=False):
        """Initialize the connection (Serial or Bluetooth)
        
        Returns:
            bool: True if successful initialization (or already connected), False otherwise
        """
        # If already connected or connecting, don't try again
        if self._connected:
            return True

        if self.connecting:
            self.logger.info("Connection already in progress")
            return True

        try:
            self.connecting = True

            # Determine connection mode if not already set
            if not self.connection_mode:
                # Auto-detect: Check for available serial ports first (fast check)
                ports = self._get_available_serial_ports()
                if len(ports):
                    self.connection_mode = self.MODE_SERIAL
                    self.logger.info("Serial ports available, trying Serial connection first")
                else:
                    self.logger.info("No serial ports available, trying Bluetooth connection")
                    # Check address format first
                    if self._is_bluetooth_uuid(self.address) or self._is_bluetooth_mac(self.address):
                        # Explicit Bluetooth address - use Bluetooth
                        self.connection_mode = self.MODE_BLUETOOTH
                        self.logger.info("Detected Bluetooth address format, using Bluetooth mode")
                    else:
                        self.connection_mode = None
                        self.logger.info("No available devices found")
                        return False

            if self.connection_mode == self.MODE_SERIAL:
                connection_result = self._connect_serial()

                # If serial fails and we haven't tried Bluetooth yet, try Bluetooth as fallback
                if not connection_result and not self._bt_tried:
                    self.logger.info("Serial connection failed, trying Bluetooth fallback")
                    self.status_message.emit("Serial connection failed, trying Bluetooth...")
                    self.connection_mode = self.MODE_BLUETOOTH
                    # Reset Bluetooth tried flag to allow retry
                    self._bt_tried = False
                    # Use shorter timeout for Bluetooth to avoid freezing
                    connection_result = self._run_coroutine(
                        self._connect_with_timeout(self.SHORT_CONNECTION_TIMEOUT,
                                                   try_serial=False)
                    )
                    if connection_result:
                        self._bt_tried = True

                if only_once:
                    self.connecting = False
                    return connection_result
            else:  # MODE_BLUETOOTH
                self.logger.info("Attempting Bluetooth connection")
                # Mark Bluetooth as tried
                self._bt_tried = True
                # Do not fall back to serial implicitly; honor explicit user actions
                connection_result = self._run_coroutine(
                    self._connect_with_timeout(self.SHORT_CONNECTION_TIMEOUT,
                                               try_serial=False)
                )

                if only_once:
                    self.connecting = False
                    return connection_result

            self.connecting = False
            return connection_result

        except Exception as e:
            self.logger.error(f"Setup failed: {e}")
            self.connecting = False
            return False

    def _connect_serial(self):
        """Connect to the device using a serial port
        
        Returns:
            bool: True if connected, False otherwise
        """
        try:
            # Handle special addressing modes
            if self.port is None:
                # First try to find by VID/PID
                device_path = self._find_serial_device_by_vid_pid()
                if device_path:
                    self.port = device_path
                else:
                    return False
            else:
                device_path = self.port

            self.logger.info(f"Connecting to serial port {device_path} at {self.baudrate} baud")
            self.status_message.emit(f"Connecting to serial port {device_path}...")

            # Connect to the serial port
            self.serial_port = self._create_serial_port(device_path, self.baudrate)
            if not self.serial_port:
                self.port = None
                return False
            else:
                self.port = device_path

            # Test the connection
            if self.serial_port.is_open:
                # Flush any stale data from the port before starting
                try:
                    self.serial_port.reset_input_buffer()
                    self.serial_port.reset_output_buffer()
                except Exception as e:
                    self.logger.debug(f"Could not flush serial buffers (may be expected): {e}")

                # Send a test command (|||) and wait for a response
                try:
                    self.serial_port.write(b"|||\n")
                    time.sleep(self.SERIAL_RESPONSE_DELAY)  # Give time for response
                except Exception as e:
                    self.logger.warning(f"Failed to send test command: {e}")

                # ── START reader thread ─────────────────────────────
                self._stop_reader = threading.Event()
                self.reader_thread = threading.Thread(
                    target=self._serial_reader, daemon=True)
                self.reader_thread.start()
                # ────────────────────────────────────────────────────
                # Try to read any response (some devices don't respond)
                try:
                    if self.serial_port.in_waiting > 0:
                        response = self.serial_port.read(self.serial_port.in_waiting)
                        response = response.decode('utf-8')
                        # self.logger.debug(f"Serial response: {response}")
                except (OSError, IOError) as e:
                    # Handle "device reports readiness" error gracefully
                    if "readiness to read" in str(e).lower() or "no data" in str(e).lower():
                        self.logger.debug(f"Serial port ready but no data available (expected): {e}")
                    else:
                        self.logger.debug(f"Serial read error (may be expected): {e}")
                except Exception:
                    # No response is OK for some devices
                    pass

                self._connected = True
                self.logger.info(f"Connected to serial port: {self.port}")
                self._emit_connection_status(True, f"Connected to serial port: {self.port}")
                return True
            else:
                self.logger.warning(f"Failed to open serial port: {self.port}")
                self._emit_connection_status(False, f"Failed to open serial port: {self.port}")
                return False

        except Exception as e:
            self.logger.error(f"Serial connection failed: {e}")
            self._emit_connection_status(False, f"Serial connection failed: {str(e)}")
            return False

    def setup_async(self, callback=None):
        """Initialize the connection in a separate thread
        
        Args:
            callback: Function to call when connection is complete (with success boolean)
        """
        if self.connection_thread and self.connection_thread.is_alive():
            self.logger.info("Connection thread already running")
            return

        def connect_thread():
            try:
                # Perform the connection (setup() will auto-detect if mode not set)
                result = self.setup()  # This now includes fallback mechanism

                # Emit signal for connection status change
                self.connection_changed.emit(result)

                # Emit status message about connection mode
                if result:
                    mode_str = "Bluetooth" if self.connection_mode == self.MODE_BLUETOOTH else "USB"
                    self.status_message.emit(f"Connected via {mode_str}")
                else:
                    self.status_message.emit("Connection failed")

                if callback:
                    # Only call callback if our connection succeeded to avoid NoneType errors
                    if result:
                        callback(result)
                    else:
                        self.logger.warning("Connection failed, skipping callback")
            except Exception as e:
                self.logger.error(f"Error in connection thread: {e}")
                # Emit signal even on exception
                self._emit_connection_status(False, f"Connection error: {str(e)}")

        self.connection_thread = threading.Thread(target=connect_thread)
        self.connection_thread.daemon = True
        self.connection_thread.start()

    @staticmethod
    def search_devices(timeout=5.0, device_name="Controller"):
        """Search for available devices (Bluetooth devices or serial ports)
        
        Returns:
            list: List of device descriptors
        """
        device_list = []
        logger = logging.getLogger(__name__)

        # Search for Bluetooth devices
        logger.info("Searching for BLE devices...")
        try:
            async def run_scan():
                return await BleakScanner.discover(timeout=timeout)

            devices = asyncio.run(run_scan())

            for device in devices:
                name = device.name or "Unknown"
                device_list.append({
                    "address": device.address,
                    "name": name,
                    "type": "bluetooth",
                    "display_name": f"{device.address} - {name} (Bluetooth)"
                })
                logger.debug(f"Found BLE device: {device.address} - {name}")
        except Exception as e:
            logger.error(f"Error searching for BLE devices: {e}")

        # Return the combined list or just the string descriptions for backward compatibility
        return [device["display_name"] for device in device_list if device_name in device["display_name"]]

    def store_device_info(self, address, device_type, vid=None, pid=None):
        """Store device information for future connections
        
        Args:
            address: Device address (for Bluetooth) or port (for serial)
            device_type: 'bluetooth' or 'serial'
            vid: Vendor ID (for serial devices)
            pid: Product ID (for serial devices)
        """
        if device_type == self.MODE_SERIAL and (vid or pid):
            self.vid = vid
            self.pid = pid
            self._save_device_ids_to_config()

        self.address = address
        self.connection_mode = device_type

    async def _connect_with_timeout(self, timeout=None, try_serial=True):
        """Attempt to connect with a timeout (Bluetooth mode)
        
        Args:
            timeout: Timeout in seconds (defaults to DEFAULT_CONNECTION_TIMEOUT)
            try_serial: Whether to try serial fallback
            
        Returns:
            bool: True if connected, False otherwise
        """
        if timeout is None:
            timeout = self.DEFAULT_CONNECTION_TIMEOUT
        try:
            # Use asyncio.wait_for to add a timeout
            await self._connect(timeout=timeout)
            return self._connected
        except asyncio.TimeoutError:
            self.logger.warning(f"Connection timed out after {timeout} seconds")
            self.status_message.emit(f"Connection timed out after {timeout} seconds")

            # Check if we actually connected despite the timeout
            if self._connected:
                return True

            if try_serial:
                # Try to fall back to serial if Bluetooth fails
                self.logger.info("Bluetooth connection failed, trying serial fallback")
                self.status_message.emit("Bluetooth connection failed, trying USB connection...")
                self.connection_mode = self.MODE_SERIAL

                # Don't use Bluetooth address for serial connection
                if self._is_bluetooth_uuid(self.address):
                    self.address = "auto"

                return self._connect_serial()
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.status_message.emit(f"Connection failed: {str(e)}")

            # If Bluetooth fails, try to fall back to serial
            if not self._connected:
                self.logger.info("Bluetooth connection failed, trying serial fallback")
                self.status_message.emit("Bluetooth connection failed, trying USB connection...")
                self.connection_mode = self.MODE_SERIAL

                # Don't use Bluetooth address for serial connection
                if self._is_bluetooth_uuid(self.address):
                    self.address = "auto"

                return self._connect_serial()

            return False

    async def _connect(self, timeout=None):
        """
        Manages the entire lifecycle of the BLE connection within the event loop.
        This function replaces the previous, short-lived _connect function logic.
        """
        if not (self._is_bluetooth_uuid(self.address) or self._is_bluetooth_mac(self.address)):
            self.logger.info(f"Scanning for {self.device_name} devices...")
            self.status_message.emit(f"Scanning for {self.device_name} devices...")
            devices = await BleakScanner.discover(timeout=self.BLE_DISCOVERY_TIMEOUT)
            for device in devices:
                if device.name and self.device_name in device.name:
                    self.address = device.address
                    self.logger.info(f"Found {self.device_name} at {self.address}")
                    self.status_message.emit(f"Found {self.device_name} at {self.address}")
                    break
            if not self.client:
                msg = f"{self.device_name} device not found"
                self.status_message.emit(msg)
                raise Exception(msg)

        self.logger.info(f"Starting BLE connection manager for {self.address}")
        self.disconnect_event = asyncio.Event() # Initialize this in the async function

        try:
            # Use the robust context manager that handles disconnects automatically on exit
            async with BleakClient(self.address, timeout=self.DEFAULT_CONNECTION_TIMEOUT) as client:
                self.client = client
                self._connected = True
                self.logger.info(f"Connected successfully to {self.address}")
                self.connection_changed.emit(True)
                self.status_message.emit(f"Connected to {self.address}")

                # --- This is where start_notify is robustly called and awaited ---
                await client.start_notify(UART_TX_CHAR_UUID, self.notification_handler)
                self.logger.info("Notifications started successfully.")

                await self.disconnect_event.wait()
                # Keep the async task running until the application disconnects
                # (e.g., self.connected is set to False by a disconnect button press)
                while self.connected:
                    if self.disconnect_event.is_set():
                        break
                    await asyncio.sleep(0.5) # Prevents blocking the event loop entirely
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            self.logger.error("BLE connection or notification setup timed out.")
            self.status_message.emit("Connection timed out.")
        except Exception as e:
            self.logger.error(f"An error occurred during BLE connection: {e}")
            self.status_message.emit(f"Connection error: {e}")
        finally:
            # Cleanup happens automatically when exiting the 'async with' block
            self.client = None
            if self._connected:
                self._connected = False
                self.connection_changed.emit(False)
                self.status_message.emit("Disconnected.")
            self.logger.info("BLE Connection manager finished.")

    def off(self):
        """Turn off all illumination - convenience method"""
        return self.send_cmd("all_off")

    async def _send_command_bt(self, command: str, timeout: float = None):
        """Send command to the device via Bluetooth"""
        if not self.connected or not self.client:
            self.logger.warning("Cannot send command: Board not connected.")
            return None

        if timeout is None:
            timeout = self.MESSAGE_TIMEOUT

        # 1. Clear state before sending the command
        self.receive_buffer = ""
        self.message_complete = False
        self.rx_event.clear()

        # 2. Send the command (assuming you have a write function)
        data = f"{command}\n".encode('utf-8')
        # This function should exist in your class for writing data over BLE/Serial
        await self.client.write_gatt_char(UART_RX_CHAR_UUID, data, response=True)
        self.logger.debug(f"Sent command: {command}")

        response = None
        try:
            response = await self._wait_for_response_async(timeout=timeout)

        except asyncio.TimeoutError:
            # Timeout occurred before the event was set
            self.logger.warning(
                f"Timeout while waiting for response to '{command}'. Current buffer: {len(self.receive_buffer)} bytes.")
            # The message is considered complete via timeout in this scenario
            pass
        finally:
            # 4. Process the response and clean up
            self.receive_buffer = ""  # Clear the buffer
            self.message_complete = False
            self.rx_event.clear()  # Clear the event for next time

            if response:
                return response
            else:
                return None

    def _send_command_serial(self, command):
        """Send command to the device via Serial port"""
        if not self._connected or not self.serial_port or not self.serial_port.is_open:
            if not self.reconnect_if_needed():
                raise Exception("Serial device not connected")

        try:
            # Add newline to command if needed and encode
            if not isinstance(command, bytes):
                if not command.endswith('\n'):
                    command = command + '\n'
                command = command.encode()

            self.logger.debug(f"Sending serial command: {command}")

            # Use a retry mechanism for sending commands
            for attempt in range(self.MAX_COMMAND_RETRIES):
                try:
                    self.serial_port.write(command)                    
                    # response = self.serial_port.read_until(b'\n')
                    # self.logger.debug(f"Serial response: {response}")
                    return  # Success
                except Exception as e:
                    if attempt == self.MAX_COMMAND_RETRIES - 1:  # Last attempt
                        raise
                    self.logger.warning(f"Serial command failed (attempt {attempt+1}/{self.MAX_COMMAND_RETRIES}): {e}")
                    # Check connection before retry
                    if not self.serial_port or not self.serial_port.is_open:
                        # Try to reconnect
                        if not self._connect_serial():
                            raise Exception("Failed to reconnect serial port")
                    time.sleep(self.COMMAND_RETRY_DELAY)  # Short delay before retry

        except Exception as e:
            self.logger.error(f"Error sending serial command: {e}")
            raise

    def notification_handler(self, sender, data):
        """Handle notifications from the device using thread-safe signaling."""
        try:
            text = data.decode()
            self.receive_buffer += text
            self.last_data_time = time.time()  # Update the last data time

            loop = self.loop  # Get the reference to the main event loop

            if not loop or loop.is_closed() or not loop.is_running():
                self.logger.warning("Event loop is not available or running in handler.")
                return

            # Check for immediate completion conditions without creating tasks here
            is_complete = False
            if text.rstrip().endswith(">>>") or len(self.receive_buffer) > self.RECEIVE_BUFFER_THRESHOLD:
                is_complete = True

            if is_complete:
                # Use call_soon_threadsafe to set the event in the *correct* loop
                self.message_complete = True
                loop.call_soon_threadsafe(self.rx_event.set)

        except Exception as e:
            self.logger.error(f"Bluetooth notification error: {e}")

    async def _wait_for_response_async(self, timeout=None):
        """Waits for the rx_event to be set and returns the buffer content."""
        if timeout is None:
            timeout = self.MESSAGE_TIMEOUT

        try:
            # Wait for the notification handler to set the event (thread safe)
            await asyncio.wait_for(self.rx_event.wait(), timeout=timeout)

            # CRITICAL STEP: Extract the message and reset state *after* the event is set
            response_buffer = self.receive_buffer
            self.receive_buffer = ""  # <<< Clear the buffer after reading it
            self.message_complete = False
            self.rx_event.clear()  # <<< Clear the event for the next message

            # Post-process the response here to clean up the prompt characters
            cleaned_response = response_buffer.split(">>>")[0].strip()
            self.logger.info(f"Processed response: {cleaned_response}")
            # self.telemetry.emit({"raw": cleaned_response})  # Emit the signal to QObject

            return cleaned_response

        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout while waiting for response. Current buffer: {self.receive_buffer}")
            # Ensure buffer is cleared on timeout as well, to prevent accumulation
            self.receive_buffer = ""
            self.rx_event.clear()
            raise
        except Exception as e:
            self.logger.error(f"Error processing response: {e}")
            self.receive_buffer = ""
            self.rx_event.clear()
            raise

    async def _check_connection(self):
        """Check if the Bluetooth connection is still active
        
        Returns:
            bool: True if connected, False otherwise
        """
        if not self.client:
            return False

        try:
            return self.client.is_connected
        except Exception:
            return False

    def reconnect_if_needed(self, only_once=False):
        """Attempt to reconnect if not connected
        
        Returns:
            bool: True if connected (already connected or reconnected), False otherwise
        """
        if self._connected:
            if self.connection_mode == self.MODE_SERIAL:
                # For serial, check if port is still open
                if not self.serial_port or not self.serial_port.is_open:
                    self._connected = False
                    return self.setup(only_once=False)
                return True
            else:
                # For Bluetooth, trust the connected flag
                return True

        try:
            # When only_once is True, do a single fast attempt without scanning/discovery
            if only_once:
                self.logger.info("Quick reconnect attempt (single try, no discovery)")
                # Auto-detect connection mode if not set
                if not self.connection_mode:
                    # Try to determine mode from address format first
                    if self._is_bluetooth_uuid(self.address) or self._is_bluetooth_mac(self.address):
                        self.connection_mode = self.MODE_BLUETOOTH
                    elif self.address.lower().startswith("com") or "/dev/" in self.address.lower():
                        self.connection_mode = self.MODE_SERIAL
                    else:
                        # Check for available serial ports (fast check)
                        ports = self._get_available_serial_ports()
                        if ports:
                            self.connection_mode = self.MODE_SERIAL
                            # If address is "auto", use the first available port
                            if self.address == "auto":
                                self.address = ports[0].device
                                self.logger.info(f"Auto-selected serial port: {self.address}")
                        else:
                            self.connection_mode = self.MODE_BLUETOOTH

                # If we have a known mode, try that once with short timeout for BT
                if self.connection_mode == self.MODE_SERIAL:
                    return self._connect_serial()
                elif self.connection_mode == self.MODE_BLUETOOTH:
                    # Shorter timeout and no discovery path because address should be set
                    return self._run_coroutine(self._connect_with_timeout(self.QUICK_RECONNECT_TIMEOUT, try_serial=False))
                # If unknown mode, do not attempt discovery; bail fast
                return False

            self.logger.info("Attempting to reconnect")
            self.status_message.emit("Attempting to reconnect...")
            return self.setup(only_once=False)
        except Exception as e:
            self.logger.error(f"Reconnection failed: {e}")
            self._emit_connection_status(False, f"Reconnection failed: {str(e)}")
            return False

    def close(self):
        """Close the connection (Bluetooth or Serial)"""
        if self.connecting:
            # Wait for connecting to finish
            if self.connection_thread and self.connection_thread.is_alive():
                self.connection_thread.join(timeout=self.CONNECTION_THREAD_JOIN_TIMEOUT)

        if self._connected:
            try:
                # Disconnect based on mode
                if self.connection_mode == self.MODE_BLUETOOTH:
                    # Turn off LEDs before disconnecting (only for Bluetooth)
                    if self.loop and self.loop.is_running():
                        # self.disconnect_event needs to be an asyncio.Event() initialized in __init__
                        self.send_cmd_bt_async("all_off")
                        self.loop.call_soon_threadsafe(self.disconnect_event.set)
                else:  # MODE_SERIAL
                    # For serial, send command first (while port is still open and reader is running)
                    # Then stop reader threads, then close port
                    try:
                        if self.serial_port and self.serial_port.is_open:
                            self.send_cmd("all_off")
                    except Exception as e:
                        self.logger.warning(f"Failed to turn off LEDs during disconnect: {e}")
                    # Now disconnect (this will stop reader threads and close port)
                    self._disconnect_serial()

                self.logger.info(f"{self.connection_mode.capitalize()} connection closed")
            except Exception as e:
                self.logger.error(f"Error closing connection: {e}")

        # Clean up the event loop if in Bluetooth mode
        if self.connection_mode == self.MODE_BLUETOOTH:
            with self._loop_lock:
                if self.loop and not self.loop.is_closed():
                    try:
                        # Cancel any remaining tasks before closing the loop
                        pending = asyncio.all_tasks(self.loop)
                        if pending:
                            # Cancel all pending tasks
                            for task in pending:
                                if not task.done():
                                    task.cancel()

                            # Use run_until_complete with proper error handling
                            try:
                                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                            except (RuntimeError, asyncio.CancelledError):
                                # This can happen if we're already in the process of closing the loop
                                self.logger.debug("Error when gathering pending tasks during shutdown (expected)")

                        # Make sure we close the loop in the same thread it was created in
                        self.loop.close()
                        self.logger.info("Successfully closed asyncio event loop")
                    except Exception as e:
                        self.logger.warning(f"Error closing event loop: {e}")
                    finally:
                        # Always set loop to None to prevent further access attempts
                        self.loop = None

    def _disconnect_serial(self):
        """Disconnect from serial port"""
        try:
            # Stop reader threads BEFORE closing the port to avoid "Bad file descriptor" errors
            # Set flags to stop reader threads
            self._connected = False
            if hasattr(self, '_stop_reader'):
                self._stop_reader.set()  # Stop _serial_reader()
            
            # Wait for the reader thread to stop
            if hasattr(self, 'reader_thread') and self.reader_thread and self.reader_thread.is_alive():
                self.reader_thread.join(timeout=0.5)
            
            # Now close the port
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                self.logger.debug("Serial port closed")

        except Exception as e:
            self.logger.error(f"Error during serial disconnect: {e}")
            self._connected = False

    # ─────────────────────────────────────────────────────────────
    #  Background reader: handles §{json} telemetry + plain text
    # ─────────────────────────────────────────────────────────────
        def _serial_reader(self):
            """
            Runs in a daemon thread. Reads one line at a time, decodes UTF-8,
            and routes:
                • lines that start with '§'  → json → self.telemetry signal
                • everything else            → message_received signal
            """
            try:
                while not self._stop_reader.is_set():
                    # Check if port is still open
                    if not self.serial_port or not self.serial_port.is_open:
                        self.logger.debug("Serial port closed, reader thread exiting")
                        break
                    
                    try:
                        raw = self.serial_port.readline()
                    except (OSError, serial.SerialException) as e:
                        # Port was closed or error reading
                        self.logger.debug(f"Serial read error: {e}, thread exiting")
                        break
                    
                    if not raw:
                        continue           # timeout → just loop again
                    
                    try:
                        line = raw.decode(errors='ignore').strip()
                    except UnicodeDecodeError:
                        continue

                    # Parse JSON telemetry packets
                    if line.startswith('§'):
                        try:
                            pkt = json.loads(line[line.find("{"):])  # strip leading §
                            self.telemetry.emit(pkt)                 # Qt → App
                            serial_echo.debug("RX  %s", pkt)         # console log
                        except Exception as e:
                            self.logger.warning("Bad json %s  (%s)", line, e)
                        continue    # handled, next line

                    # Emit non-JSON messages (regular serial output)
                    if line:
                        self.message_received.emit(line)
            except Exception as e:
                self.logger.error("Serial reader crashed: %s", e)
            finally:
                self.logger.debug("Serial reader thread terminated")
            
    def _serial_reader(self):
        """
        Runs in a daemon thread.  Reads one line at a time, decodes UTF-8,
        and routes:
           • lines that start with '§'  → json → self.telemetry signal
           • everything else            → DEBUG log (kept for backwards-compat)
        """
        try:
            while not self._stop_reader.is_set():
                # Check if port is still open before reading (race condition protection)
                if not self.serial_port or not self.serial_port.is_open:
                    break

                raw = self.serial_port.readline()
                if not raw:
                    continue           # timeout → just loop again
                try:
                    line = raw.decode(errors='ignore').strip()
                except UnicodeDecodeError:
                    continue

                # Parse JSON telemetry packets
                if line.startswith('§'):
                    try:
                        # Frame header sits between '§' and the JSON object —
                        # e.g. '§PID_TEC1{...}' -> 'PID_TEC1'. Tagging it onto
                        # the dict lets the UI route TEMP/PID frames vs INFO,
                        # ERR, and WHOAMI events instead of treating them all
                        # as the same telemetry shape.
                        json_start_index = line.find('{')
                        if json_start_index != -1:
                            frame = line[1:json_start_index]
                            pkt_txt = line[json_start_index:]
                            pkt = json.loads(pkt_txt)
                            if isinstance(pkt, dict):
                                pkt['_frame'] = frame
                            self.telemetry.emit(pkt)
                            serial_echo.debug("RX  %s %s", frame, pkt)
                        else:
                            self.logger.warning("Found telemetry marker '§' but no JSON object: %s", line)
                    except Exception as e:
                        self.logger.warning("Bad json %s  (%s)", line, e)
                    continue    # handled, next line
                
                elif line:
                    # Emit non-JSON messages (regular serial output)                 
                    self.message_received.emit(line)
                    # self.logger.debug("SERIAL %s", line)        # legacy output
        except (OSError, IOError):
            # Handle "Bad file descriptor" and similar errors gracefully
            # These are expected when the port is closed
            pass
        except Exception as e:
            self.logger.error("Serial reader crashed: %s", e)
    # ─────────────────────────────────────────────────────────────

    async def _disconnect(self):
        """Disconnect from Bluetooth device"""
        try:
            if self.client:
                # Stop notifications first
                try:
                    await self.client.stop_notify(UART_TX_CHAR_UUID)
                except Exception as e:
                    self.logger.warning(f"Error stopping notifications: {e}")

                # Then disconnect
                if self.client is not None:
                    await self.client.disconnect()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")
            raise
        finally:
            self._connected = False
            self.client = None

    @fail_safe
    def send_cmd(self, command):
        """Send a command to the device (via Bluetooth or Serial)
        
        Args:
            command: The command string to send directly to the device
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._connected:
            self.logger.warning("Device not connected")
            # Fast path: avoid expensive BLE discovery unless explicitly requested elsewhere
            if not self.reconnect_if_needed(only_once=True):
                return False

        try:
            # Send via appropriate channel based on connection mode
            if self.connection_mode == self.MODE_BLUETOOTH:
                self._run_coroutine(self._send_command_bt(command))
            else:  # MODE_SERIAL
                self._send_command_serial(command)

            # self.logger.debug(f"Sent command: {command}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send command {command}: {e}")
            self.reconnect_if_needed()
            return False

    def send_cmd_bt_async(self, command):
        """Send a command to the device via Bluetooth without blocking."""
        if self.connection_mode != self.MODE_BLUETOOTH:
            self.logger.warning("send_cmd_bt_async called when not in Bluetooth mode.")
            return

        if not self._connected:
            self.logger.warning("Device not connected")
            return

        try:
            self._run_coroutine(self._send_command_bt(command), wait_for_result=False)
        except Exception as e:
            self.logger.error(f"Failed to send async command {command}: {e}")

    def change_connection_mode(self, mode, address=None, port=None, baudrate=None):
        """Change the connection mode between Bluetooth and Serial
        
        This method initiates the connection asynchronously. The result is
        communicated via the `connection_changed` signal.

        Args:
            mode: The connection mode (MODE_BLUETOOTH or MODE_SERIAL)
            address: Optional new address to use
            port: Optional new port to use for serial
            baudrate: Optional new baudrate to use for serial
        """
        if mode not in [self.MODE_BLUETOOTH, self.MODE_SERIAL]:
            self.logger.error(f"Invalid connection mode: {mode}")
            return

        # If already in this mode and connected, only proceed if parameters require a change
        if self.connection_mode == mode and self._connected:
            if mode == self.MODE_SERIAL:
                needs_change = False
                if port is not None and port != getattr(self, "port", None):
                    needs_change = True
                if baudrate is not None and baudrate != getattr(self, "baudrate", None):
                    needs_change = True
                if not needs_change:
                    return
            else:  # MODE_BLUETOOTH
                if address is None or address == getattr(self, "address", None):
                    return

        # Close existing connection
        self.close()

        # Update parameters
        self.connection_mode = mode

        # Handle address settings
        if address:
            self.address = address

        # Update port and baudrate if provided
        if port is not None:
            self.port = port

        if baudrate is not None:
            self.baudrate = baudrate

        # Try to connect with new mode
        self.setup_async()

    def upload_firmware(self, firmware_path, reset_device=True, callback=None):
        """Upload MicroPython firmware to the device over serial connection

        Args:
            firmware_path: Path to the directory containing firmware files
            reset_device: Whether to reset the device after upload
            callback: Optional callback function to be called after firmware upload
            
        Returns:
            bool: True if successful, False otherwise
        """
        if self.connection_mode != self.MODE_SERIAL:
            self.logger.error("Firmware upload is only supported in serial mode")
            self.status_message.emit("Firmware upload requires serial connection")
            return False

        if not self._connected or not self.serial_port or not self.serial_port.is_open:
            self.logger.error("Serial device not connected")
            self.status_message.emit("Not connected to device")
            return False

        # Start upload in a separate thread using mpremote
        upload_thread = threading.Thread(
            target=self._upload_firmware_mpremote,
            args=(firmware_path, reset_device, callback)
        )
        upload_thread.daemon = True
        upload_thread.start()
        return True

    def _upload_firmware_mpremote(self, firmware_path, reset_device=True, callback=None):
        """Upload firmware using mpremote Python module
        
        Args:
            firmware_path: Path to the directory containing firmware files
            reset_device: Whether to reset the device after upload
            callback: Optional callback function to be called after firmware upload
        """
        try:
            self.status_message.emit("Preparing to upload firmware with mpremote module...")
            self.logger.info(f"Using mpremote module to upload firmware from {firmware_path}")

            # Need to close our serial connection so mpremote can access the device
            original_port = self.serial_port.port
            baudrate = self.baudrate
            self.logger.info(f"Temporarily closing serial port {original_port} for mpremote access")
            self.serial_port.close()
            self._connected = False

            # Get list of Python files
            fw_path = Path(firmware_path)
            if fw_path.is_dir():
                files = [f for f in fw_path.glob('**/*')
                         if f.suffix not in ['', '.md'] or f.is_dir()]

                files.sort(key=lambda f: (
                    0 if f.name == "boot.py" else (
                        1 if f.name == "main.py" else 2
                    )
                ))
                self.logger.info(f"Found {len(files)} files to upload")
            else:
                self.logger.error(f"Firmware path {firmware_path} is not a directory")
                self.status_message.emit(f"Invalid firmware path: {firmware_path}")

                # Manually reopen port before signaling
                self._reopen_serial_port(original_port, baudrate)

                # Use signal to ensure reconnection happens on the main thread
                self.reconnect_signal.emit()

                if callback:
                    # Use signal to ensure callback is called on the main thread
                    self.callback_signal.emit(False, callback)
                return

            if not files:
                self.logger.warning("No Python files found in firmware directory")
                self.status_message.emit("No Python files found to upload")

                # Manually reopen port before signaling
                self._reopen_serial_port(original_port, baudrate)

                # Use signal to ensure reconnection happens on the main thread
                self.reconnect_signal.emit()

                if callback:
                    # Use signal to ensure callback is called on the main thread
                    self.callback_signal.emit(False, callback)
                return

            try:
                # Import mpremote module
                try:
                    mpremote = importlib.import_module('mpremote.main')
                    self.logger.info("Successfully imported mpremote module")
                except ImportError:
                    self.logger.error("Failed to import mpremote module. Is it installed?")
                    self.status_message.emit("Error: mpremote module not found. Install with 'pip install mpremote'")

                    # Manually reopen port before signaling
                    self._reopen_serial_port(original_port, baudrate)

                    # Use signal to ensure reconnection happens on the main thread
                    self.reconnect_signal.emit()

                    if callback:
                        # Use signal to ensure callback is called on the main thread
                        self.callback_signal.emit(False, callback)
                    return

                # Format the filesystem first if requested
                # if reset_device:
                self.status_message.emit("Formatting device filesystem...")
                self.logger.info("Formatting device filesystem")

                # Use mpremote module to run the format command
                format_cmd = ["connect", original_port, "rm", "-rv", ":/"]
                try:
                    # Save original sys.argv and restore it after
                    original_argv = sys.argv.copy()
                    sys.argv = ["mpremote"] + format_cmd
                    mpremote.main()
                    sys.argv = original_argv
                except SystemExit:
                    # mpremote calls sys.exit() when done, so we catch it
                    pass

                # Upload each file
                all_successful = True
                for i, filename in enumerate(files):
                    self.status_message.emit(f"Uploading file {i+1}/{len(files)}: {filename}")
                    self.upload_progress.emit(i+1, len(files))

                    local_path = str(filename.absolute())
                    remote_path = str(filename.relative_to(fw_path))  # Upload to root directory

                    # Use mpremote module to upload the file
                    if filename.is_dir():
                        upload_cmd = ["connect", original_port, "mkdir", f"{remote_path}"]
                    else:
                        upload_cmd = ["connect", original_port, "cp", local_path, f":{remote_path}"]

                    try:
                        # Save original sys.argv and restore it after
                        original_argv = sys.argv.copy()
                        sys.argv = ["mpremote"] + upload_cmd
                        self.logger.info(f"Running: mpremote {' '.join(upload_cmd)}")
                        mpremote.main()
                        sys.argv = original_argv
                        self.logger.info(f"Successfully uploaded {filename}")
                    except SystemExit:
                        # mpremote calls sys.exit() when done, so we catch it
                        self.logger.info(f"Uploaded {filename} (with SystemExit)")
                    except Exception as e:
                        self.logger.error(f"Failed to upload {filename}: {e}")
                        self.status_message.emit(f"Failed: {filename}")
                        all_successful = False
                        break

                # Reset the device if requested
                if reset_device:
                    self.status_message.emit("Resetting device...")
                    reset_cmd = ["connect", original_port, "reset"]
                    try:
                        # Save original sys.argv and restore it after
                        original_argv = sys.argv.copy()
                        sys.argv = ["mpremote"] + reset_cmd
                        mpremote.main()
                        sys.argv = original_argv
                    except SystemExit:
                        # mpremote calls sys.exit() when done, so we catch it
                        pass

                if all_successful:
                    self.status_message.emit("Firmware upload complete")
                    self.logger.info("Firmware upload completed successfully")
                else:
                    self.status_message.emit("Firmware upload incomplete - some files failed")
                    self.logger.warning("Firmware upload incomplete - some files failed")

                # Make sure mpremote has closed the port
                time.sleep(self.FIRMWARE_UPLOAD_DELAY)  # Longer delay before reconnection to give device time to reboot

                # When the device reboots, it often connects on a different port
                # Scan available ports to find the new port name
                self.logger.info("Looking for the device on available ports after firmware upload...")

                # Try to find the device with same identifiers
                new_port = None
                tries = 0

                while tries < self.FIRMWARE_UPLOAD_MAX_TRIES and not new_port:
                    try:
                        # List all available ports
                        ports = self._get_available_serial_ports()

                        # First try to match by VID/PID
                        if self.vid and self.pid:
                            for port in ports:
                                if (hasattr(port, 'vid') and port.vid is not None and
                                    hasattr(port, 'pid') and port.pid is not None and
                                    f"{port.vid:04x}".lower() == str(self.vid).lower() and
                                    f"{port.pid:04x}".lower() == str(self.pid).lower()):
                                    new_port = port.device
                                    self.logger.info(f"Found device with matching VID/PID on port {new_port}")
                                    break

                        # If not found by VID/PID, try the original port
                        if not new_port and original_port in [p.device for p in ports]:
                            new_port = original_port
                            self.logger.info(f"Original port {original_port} is still available")

                        # If still not found, look for any compatible port
                        if not new_port:
                            for port in ports:
                                if "usbmodem" in port.device or "ttyACM" in port.device:
                                    new_port = port.device
                                    self.logger.info(f"Found potential device port {new_port}")
                                    break

                        # If no port found, wait and retry
                        if not new_port:
                            tries += 1
                            self.logger.info(f"No suitable port found. Waiting and retrying ({tries}/{self.FIRMWARE_UPLOAD_MAX_TRIES})...")
                            time.sleep(self.FIRMWARE_UPLOAD_RETRY_DELAY)

                    except Exception as e:
                        self.logger.error(f"Error finding ports: {e}")
                        tries += 1
                        time.sleep(self.FIRMWARE_UPLOAD_RETRY_DELAY)

                # If we found a new port, try to reconnect to it
                if new_port:
                    try:
                        self.logger.info(f"Attempting to connect to port {new_port} after firmware upload")
                        self.status_message.emit(f"Reconnecting to {new_port}...")

                        # Update our address to the new port
                        self.address = new_port

                        # Try to open the serial port directly first
                        self._reopen_serial_port(new_port, baudrate)

                        if self.serial_port.is_open:
                            self._connected = True
                            self.logger.info(f"Successfully reconnected to {new_port}")
                            self.status_message.emit(f"Connected to {new_port}")
                        else:
                            self.logger.warning(f"Could not open port {new_port}")
                            self._connected = False
                    except Exception as e:
                        self.logger.error(f"Error connecting to new port {new_port}: {e}")
                        self._connected = False
                else:
                    self.logger.warning("Could not find a suitable port after firmware upload")
                    self._connected = False

                # Use signal to ensure reconnection happens on main thread regardless
                # This will handle the case where we couldn't reconnect directly
                self.reconnect_signal.emit()

                if callback:
                    # Use signal to ensure callback is called on the main thread
                    self.callback_signal.emit(all_successful, callback)

            except Exception as e:
                self.logger.error(f"mpremote module error: {e}")
                self.status_message.emit(f"Upload error: {str(e)}")

                # Use signal to ensure reconnection happens on the main thread
                self.reconnect_signal.emit()

                if callback:
                    # Use signal to ensure callback is called on the main thread
                    self.callback_signal.emit(False, callback)

        except Exception as e:
            self.logger.error(f"Error during mpremote firmware upload: {e}")
            self.status_message.emit(f"Upload error: {str(e)}")

            # Use signal to ensure reconnection happens on the main thread
            self.reconnect_signal.emit()

            if callback:
                # Use signal to ensure callback is called on the main thread
                self.callback_signal.emit(False, callback)

    def list_firmware_files(self):
        """List files on the MicroPython device using mpremote

        Returns:
            list: List of files on the device
        """
        if self.connection_mode != self.MODE_SERIAL:
            self.logger.error("Listing firmware files is only supported in serial mode")
            return []

        if not self._connected or not self.serial_port or not self.serial_port.is_open:
            self.logger.error("Serial device not connected")
            return []

        try:
            import importlib
            import sys

            # Remember current serial port
            port = self.serial_port.port
            baudrate = self.baudrate
            self.logger.info(f"Temporarily closing serial port {port} for mpremote access")

            # Close our serial connection so mpremote can access the device
            self.serial_port.close()
            self._connected = False

            try:
                # Import mpremote module
                mpremote = importlib.import_module('mpremote.main')
                self.logger.info("Successfully imported mpremote module for file listing")

                # Create command to list files
                list_cmd = ["connect", port, "ls"]

                # Capture output
                output = io.StringIO()
                try:
                    # Save original sys.argv and restore it after
                    original_argv = sys.argv.copy()
                    with redirect_stdout(output):
                        sys.argv = ["mpremote"] + list_cmd
                        mpremote.main()
                    sys.argv = original_argv
                except SystemExit:
                    # mpremote calls sys.exit() when done, so we catch it
                    pass

                # Process output to extract files
                file_list = []
                for line in output.getvalue().splitlines():
                    line = line.strip()
                    if line:
                        if ":" in line:  # Skip directory headers like "/:"
                            continue
                        # Skip directory markers and empty lines
                        if not line.startswith('/') and not line.endswith('/') and not line.startswith('mode') and line:
                            # Try to extract the filename (usually the last field)
                            parts = line.split()
                            if parts:
                                file_list.append(parts[-1])

                self.logger.info(f"Found {len(file_list)} files on device")

                # Make sure to force mpremote to close its port
                time.sleep(self.COMMAND_RETRY_DELAY)  # Small delay before reconnection

                # Manually reopen our serial port before emitting the signal
                self._reopen_serial_port(port, baudrate)

                # Use signal to handle main thread reconnection
                self.reconnect_signal.emit()

                return file_list

            except ImportError:
                self.logger.error("Failed to import mpremote module. Is it installed?")
                self.status_message.emit("Error: mpremote module not found. Install with 'pip install mpremote'")
                # Fall back to traditional method
                self.reconnect_signal.emit()
                return self._list_firmware_files_traditional()

            except Exception as e:
                self.logger.error(f"Error listing files with mpremote: {e}")
                # Fall back to traditional method
                self.reconnect_signal.emit()
                return self._list_firmware_files_traditional()

        except Exception as e:
            self.logger.error(f"Error in list_firmware_files: {e}")
            # Attempt to reconnect
            self.reconnect_signal.emit()
            return []

    def _list_firmware_files_traditional(self):
        """Legacy method to list files on the MicroPython device

        Returns:
            list: List of files on the device
        """
        try:
            # Enter REPL mode
            self._enter_repl_mode()

            # Import necessary modules
            self._execute_command("import os")

            # Get list of files
            response = self._execute_command("print(os.listdir())")

            # Parse response
            if response:
                # Try to extract Python list from response
                match = re.search(r'\[(.*)\]', response.decode('utf-8', errors='ignore'))
                if match:
                    files_str = match.group(1)
                    # Parse the list items
                    files = []
                    for item in re.finditer(r"'([^']*)'", files_str):
                        files.append(item.group(1))
                    return files

            return []
        except Exception as e:
            self.logger.error(f"Error listing firmware files (traditional method): {e}")
            return []

    def _enter_repl_mode(self):
        """Enter MicroPython REPL mode"""
        try:
            # Send Ctrl+C to interrupt any running program
            self.serial_port.write(b'\x03\x03')
            time.sleep(self.REPL_ENTER_DELAY)

            # Flush any pending output
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            # Send Enter to get a clean prompt
            self.serial_port.write(b'\r\n')
            time.sleep(self.REPL_ENTER_DELAY)

            # Read response to check if we're in REPL
            response = self.serial_port.read_all()
            self.logger.debug(f"REPL response: {response}")

            # If we don't see a prompt, try again
            if not response or b'>>>' not in response:
                self.logger.debug("REPL prompt not found, trying again")
                self.serial_port.write(b'\x03\r\n')
                time.sleep(self.REPL_RETRY_DELAY)

            return True
        except Exception as e:
            self.logger.error(f"Error entering REPL mode: {e}")
            return False

    def _execute_command(self, command):
        """Execute a Python command on the device

        Args:
            command: Python command to execute
        """
        try:
            # Send the command
            lines = command.strip().split('\n')
            for i, line in enumerate(lines):
                self.serial_port.write(line.encode() + b'\r\n')
                time.sleep(0.01)

            # Read response
            time.sleep(0.1)
            response = self.serial_port.read_all()
            self.logger.debug(f"Command response: {response}")
            return response
        except Exception as e:
            self.logger.error(f"Error executing command: {e}")
            return None
