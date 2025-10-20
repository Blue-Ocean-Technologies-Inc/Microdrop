"""
PGVA Controller Base Class
Handles communication and control of Festo PGVA pressure/vacuum generator via ethernet.
"""

import json
import time
from datetime import datetime
from typing import Optional

from traits.api import HasTraits, provides, Bool, Str, Float, Instance, Dict
import dramatiq
from dramatiq.middleware import CurrentMessage

from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor, invoke_class_method, TimestampedMessage
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from .consts import (
    PKG, PGVA_CONNECTED, PGVA_DISCONNECTED, PGVA_PRESSURE_UPDATED, PGVA_VACUUM_UPDATED,
    PGVA_OUTPUT_PRESSURE_UPDATED, PGVA_STATUS_UPDATED, PGVA_WARNINGS_UPDATED, 
    PGVA_ERRORS_UPDATED, PGVA_COMPREHENSIVE_STATUS_UPDATED, PGVA_HEALTH_CHECK_UPDATED,
    PGVA_DEVICE_INFO_UPDATED, PGVA_ERROR_SIGNAL, SET_PRESSURE, SET_VACUUM, SET_OUTPUT_PRESSURE,
    GET_PRESSURE, GET_VACUUM, GET_OUTPUT_PRESSURE, GET_STATUS, GET_WARNINGS, GET_ERRORS,
    GET_COMPREHENSIVE_STATUS, GET_HEALTH_CHECK, GET_DEVICE_INFO, ENABLE_PGVA, DISABLE_PGVA, 
    RESET_PGVA, TRIGGER_MANUAL, STORE_TO_EEPROM, CONNECT_PGVA, DISCONNECT_PGVA,
    PGVA_DEFAULT_IP, PGVA_DEFAULT_PORT, PGVA_DEFAULT_UNIT_ID
)
from .interfaces.i_pgva_controller_base import IPGVAControllerBase
from .services.pgva_ethernet_communication import PGVAEthernetCommunication

logger = get_logger(__name__)


@provides(IPGVAControllerBase)
class PGVAControllerBase(HasTraits):
    """
    Base controller class for Festo PGVA pressure/vacuum generator.
    Provides ethernet communication and control capabilities via Dramatiq messaging.
    """
    
    # Interface properties
    pgva_connection_active = Bool(False)
    device_ip = Str(PGVA_DEFAULT_IP)
    device_port = Str(str(PGVA_DEFAULT_PORT))
    unit_id = Str(str(PGVA_DEFAULT_UNIT_ID))
    current_pressure = Float(0.0)
    current_vacuum = Float(0.0)
    target_pressure = Float(0.0)
    target_vacuum = Float(0.0)
    device_status = Str("Disconnected")
    is_enabled = Bool(False)
    
    # Communication layer
    ethernet_comm = Instance(PGVAEthernetCommunication)
    
    # Dramatiq properties
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = Str(f"{PKG}_listener")
    timestamps = Dict(str, datetime)
    
    def __init__(self, **traits):
        super().__init__(**traits)
        self.ethernet_comm = PGVAEthernetCommunication(
            ip_address=self.device_ip,
            port=int(self.device_port),
            unit_id=int(self.unit_id)
        )
    
    def __del__(self):
        """Cleanup when the controller is destroyed."""
        self.cleanup()
    
    def cleanup(self):
        """Cleanup resources when the controller is stopped."""
        logger.info("Cleaning up PGVA Controller resources")
        if self.ethernet_comm and self.ethernet_comm.connected:
            try:
                self.ethernet_comm.disconnect()
                logger.info("PGVA ethernet connection terminated")
            except Exception as e:
                logger.error(f"Error terminating PGVA ethernet connection: {e}")
            finally:
                self.pgva_connection_active = False
                self.device_status = "Disconnected"
    
    def listener_actor_routine(self, timestamped_message: TimestampedMessage, topic: str):
        """
        Dramatiq actor that listens to PGVA-related messages.
        
        Args:
            timestamped_message: The received message with timestamp
            topic: The topic of the message
        """
        logger.debug(f"PGVA BACKEND LISTENER: Received message: '{timestamped_message}' from topic: {topic} at {timestamped_message.timestamp}")
        
        # Parse topic hierarchy
        topics_tree = topic.split("/")
        head_topic = topics_tree[0]
        primary_sub_topic = topics_tree[1] if len(topics_tree) > 1 else ""
        specific_sub_topic = topics_tree[-1]
        
        requested_method = None
        
        # Handle PGVA-related topics
        if head_topic == 'pgva':
            if primary_sub_topic == 'requests':
                # Handle PGVA control requests
                if specific_sub_topic in ['connect', 'disconnect']:
                    requested_method = f"on_{specific_sub_topic}_request"
                elif self.pgva_connection_active:
                    requested_method = f"on_{specific_sub_topic}_request"
                else:
                    logger.warning(f"Request for {specific_sub_topic} denied: PGVA is not connected.")
            elif primary_sub_topic == 'signals':
                # Handle PGVA status signals
                requested_method = f"on_{specific_sub_topic}_signal"
        else:
            logger.debug(f"Ignored request from topic '{topic}': Not a PGVA-related request.")
        
        if requested_method:
            # Check for duplicate messages
            if self.timestamps.get(topic, datetime.min) > timestamped_message.timestamp_dt:
                logger.debug(f"PGVAController: Ignoring older message from topic: {topic} received at {timestamped_message.timestamp_dt}")
                return
            
            self.timestamps[topic] = timestamped_message.timestamp_dt
            
            # Execute the requested method
            err_msg = invoke_class_method(self, requested_method, timestamped_message)
            
            if err_msg:
                logger.error(f"{self.listener_name}; Received message: {timestamped_message} from topic: {topic} Failed to execute due to error: {err_msg}")
    
    def traits_init(self):
        """Initialize the controller and set up the Dramatiq listener."""
        logger.info("Starting PGVA Controller listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine
        )
    
    # Connection management methods
    def on_connect_request(self, timestamped_message: TimestampedMessage):
        """Handle connect request."""
        try:
            # Parse connection parameters if provided in message
            message_data = json.loads(timestamped_message) if timestamped_message else {}
            
            ip = message_data.get('ip', self.device_ip)
            port = int(message_data.get('port', self.device_port))
            unit_id = int(message_data.get('unit_id', self.unit_id))
            
            # Update communication parameters if different
            if ip != self.device_ip or port != int(self.device_port) or unit_id != int(self.unit_id):
                self.device_ip = ip
                self.device_port = str(port)
                self.unit_id = str(unit_id)
                self.ethernet_comm = PGVAEthernetCommunication(ip, port, unit_id)
            
            # Attempt connection
            if self.ethernet_comm.connect():
                self.pgva_connection_active = True
                self.device_status = "Connected"
                self._on_pgva_connected()
                publish_message(topic=PGVA_CONNECTED, message=json.dumps({
                    'ip': ip, 'port': port, 'unit_id': unit_id
                }))
                logger.info(f"Successfully connected to PGVA at {ip}:{port}")
            else:
                publish_message(topic=PGVA_ERROR_SIGNAL, message="Failed to connect to PGVA device")
                logger.error("Failed to connect to PGVA device")
                
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Connection error: {str(e)}")
            logger.error(f"Error connecting to PGVA: {e}")
    
    def on_disconnect_request(self, timestamped_message: TimestampedMessage):
        """Handle disconnect request."""
        try:
            self.ethernet_comm.disconnect()
            self.pgva_connection_active = False
            self.device_status = "Disconnected"
            self._on_pgva_disconnected()
            publish_message(topic=PGVA_DISCONNECTED, message="")
            logger.info("Disconnected from PGVA")
        except Exception as e:
            logger.error(f"Error disconnecting from PGVA: {e}")
    
    # Control methods
    def on_set_pressure_request(self, timestamped_message: TimestampedMessage):
        """Handle set pressure request."""
        try:
            message_data = json.loads(timestamped_message) if timestamped_message else {}
            pressure = float(message_data.get('pressure', 0.0))
            
            if self.ethernet_comm.set_pressure_threshold_mbar(pressure):
                self.target_pressure = pressure
                logger.info(f"Set pressure threshold to {pressure} mbar")
            else:
                publish_message(topic=PGVA_ERROR_SIGNAL, message="Failed to set pressure threshold")
                
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error setting pressure threshold: {str(e)}")
            logger.error(f"Error setting pressure threshold: {e}")
    
    def on_set_vacuum_request(self, timestamped_message: TimestampedMessage):
        """Handle set vacuum request."""
        try:
            message_data = json.loads(timestamped_message) if timestamped_message else {}
            vacuum = float(message_data.get('vacuum', 0.0))
            
            if self.ethernet_comm.set_vacuum_threshold_mbar(vacuum):
                self.target_vacuum = vacuum
                logger.info(f"Set vacuum threshold to {vacuum} mbar")
            else:
                publish_message(topic=PGVA_ERROR_SIGNAL, message="Failed to set vacuum threshold")
                
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error setting vacuum threshold: {str(e)}")
            logger.error(f"Error setting vacuum threshold: {e}")
    
    def on_get_pressure_request(self, timestamped_message: TimestampedMessage):
        """Handle get pressure request."""
        try:
            pressure = self.ethernet_comm.read_pressure_mbar()
            self.current_pressure = pressure
            publish_message(topic=PGVA_PRESSURE_UPDATED, message=json.dumps({
                'pressure': pressure, 'unit': 'mbar', 'timestamp': datetime.now().isoformat()
            }))
            logger.debug(f"Current pressure: {pressure} mbar")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error reading pressure: {str(e)}")
            logger.error(f"Error reading pressure: {e}")
    
    def on_get_vacuum_request(self, timestamped_message: TimestampedMessage):
        """Handle get vacuum request."""
        try:
            vacuum = self.ethernet_comm.read_vacuum_mbar()
            self.current_vacuum = vacuum
            publish_message(topic=PGVA_VACUUM_UPDATED, message=json.dumps({
                'vacuum': vacuum, 'unit': 'mbar', 'timestamp': datetime.now().isoformat()
            }))
            logger.debug(f"Current vacuum: {vacuum} mbar")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error reading vacuum: {str(e)}")
            logger.error(f"Error reading vacuum: {e}")
    
    def on_get_status_request(self, timestamped_message: TimestampedMessage):
        """Handle get status request."""
        try:
            status = self.ethernet_comm.get_status()
            self.device_status = f"Status: {status}"
            publish_message(topic=PGVA_STATUS_UPDATED, message=json.dumps({
                'status': status, 'timestamp': datetime.now().isoformat()
            }))
            logger.debug(f"Device status: {status}")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error reading status: {str(e)}")
            logger.error(f"Error reading status: {e}")
    
    def on_get_warnings_request(self, timestamped_message: TimestampedMessage):
        """Handle get warnings request."""
        try:
            warnings = self.ethernet_comm.get_warnings()
            publish_message(topic=PGVA_WARNINGS_UPDATED, message=json.dumps({
                'warnings': warnings, 'timestamp': datetime.now().isoformat()
            }))
            logger.debug(f"Device warnings: {warnings}")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error reading warnings: {str(e)}")
            logger.error(f"Error reading warnings: {e}")
    
    def on_get_errors_request(self, timestamped_message: TimestampedMessage):
        """Handle get errors request."""
        try:
            errors = self.ethernet_comm.get_errors()
            publish_message(topic=PGVA_ERRORS_UPDATED, message=json.dumps({
                'errors': errors, 'timestamp': datetime.now().isoformat()
            }))
            logger.debug(f"Device errors: {errors}")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error reading errors: {str(e)}")
            logger.error(f"Error reading errors: {e}")
    
    def on_get_comprehensive_status_request(self, timestamped_message: TimestampedMessage):
        """Handle get comprehensive status request."""
        try:
            comprehensive_status = self.ethernet_comm.get_comprehensive_status()
            publish_message(topic=PGVA_COMPREHENSIVE_STATUS_UPDATED, message=json.dumps({
                'comprehensive_status': comprehensive_status, 'timestamp': datetime.now().isoformat()
            }))
            logger.debug(f"Comprehensive status: {comprehensive_status['summary']}")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error reading comprehensive status: {str(e)}")
            logger.error(f"Error reading comprehensive status: {e}")
    
    def on_get_health_check_request(self, timestamped_message: TimestampedMessage):
        """Handle get health check request."""
        try:
            health_check = self.ethernet_comm.check_device_health()
            publish_message(topic=PGVA_HEALTH_CHECK_UPDATED, message=json.dumps({
                'health_check': health_check, 'timestamp': datetime.now().isoformat()
            }))
            logger.info(f"Health check: {health_check['overall_health']} - {health_check['status_summary']}")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error performing health check: {str(e)}")
            logger.error(f"Error performing health check: {e}")
    
    def on_get_device_info_request(self, timestamped_message: TimestampedMessage):
        """Handle get device info request."""
        try:
            device_info = self.ethernet_comm.get_device_info()
            publish_message(topic=PGVA_DEVICE_INFO_UPDATED, message=json.dumps({
                'device_info': device_info, 'timestamp': datetime.now().isoformat()
            }))
            logger.debug(f"Device info: {device_info}")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error reading device info: {str(e)}")
            logger.error(f"Error reading device info: {e}")
    
    def on_get_output_pressure_request(self, timestamped_message: TimestampedMessage):
        """Handle get output pressure request."""
        try:
            output_pressure = self.ethernet_comm.read_output_pressure_mbar()
            publish_message(topic=PGVA_OUTPUT_PRESSURE_UPDATED, message=json.dumps({
                'output_pressure': output_pressure, 'unit': 'mbar', 'timestamp': datetime.now().isoformat()
            }))
            logger.debug(f"Current output pressure: {output_pressure} mbar")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error reading output pressure: {str(e)}")
            logger.error(f"Error reading output pressure: {e}")
    
    def on_set_output_pressure_request(self, timestamped_message: TimestampedMessage):
        """Handle set output pressure request."""
        try:
            message_data = json.loads(timestamped_message) if timestamped_message else {}
            pressure = float(message_data.get('pressure', 0.0))
            
            if self.ethernet_comm.set_output_pressure_mbar(pressure):
                logger.info(f"Set output pressure to {pressure} mbar")
            else:
                publish_message(topic=PGVA_ERROR_SIGNAL, message="Failed to set output pressure")
                
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error setting output pressure: {str(e)}")
            logger.error(f"Error setting output pressure: {e}")
    
    def on_trigger_manual_request(self, timestamped_message: TimestampedMessage):
        """Handle manual trigger request."""
        try:
            if self.ethernet_comm.trigger_manual():
                logger.info("Manual trigger activated")
            else:
                publish_message(topic=PGVA_ERROR_SIGNAL, message="Failed to trigger manual operation")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error triggering manual: {str(e)}")
            logger.error(f"Error triggering manual: {e}")
    
    def on_store_to_eeprom_request(self, timestamped_message: TimestampedMessage):
        """Handle store to EEPROM request."""
        try:
            if self.ethernet_comm.store_to_eeprom():
                logger.info("Parameters stored to EEPROM")
            else:
                publish_message(topic=PGVA_ERROR_SIGNAL, message="Failed to store parameters to EEPROM")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error storing to EEPROM: {str(e)}")
            logger.error(f"Error storing to EEPROM: {e}")
    
    def on_enable_request(self, timestamped_message: TimestampedMessage):
        """Handle enable request."""
        try:
            if self.ethernet_comm.enable_pump():
                self.is_enabled = True
                logger.info("PGVA pump enabled")
            else:
                publish_message(topic=PGVA_ERROR_SIGNAL, message="Failed to enable PGVA pump")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error enabling pump: {str(e)}")
            logger.error(f"Error enabling pump: {e}")
    
    def on_disable_request(self, timestamped_message: TimestampedMessage):
        """Handle disable request."""
        try:
            if self.ethernet_comm.disable_pump():
                self.is_enabled = False
                logger.info("PGVA pump disabled")
            else:
                publish_message(topic=PGVA_ERROR_SIGNAL, message="Failed to disable PGVA pump")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error disabling pump: {str(e)}")
            logger.error(f"Error disabling pump: {e}")
    
    def on_reset_request(self, timestamped_message: TimestampedMessage):
        """Handle reset request."""
        try:
            # For reset, we'll disable the pump and then re-enable it
            if self.ethernet_comm.disable_pump():
                import time
                time.sleep(0.1)  # Brief pause
                if self.ethernet_comm.enable_pump():
                    self.is_enabled = True
                    logger.info("PGVA device reset (pump disabled and re-enabled)")
                else:
                    self.is_enabled = False
                    logger.warning("PGVA device reset: pump disabled but failed to re-enable")
            else:
                publish_message(topic=PGVA_ERROR_SIGNAL, message="Failed to reset PGVA device")
        except Exception as e:
            publish_message(topic=PGVA_ERROR_SIGNAL, message=f"Error resetting device: {str(e)}")
            logger.error(f"Error resetting device: {e}")
    
    # Signal handlers (for future use)
    def on_connected_signal(self, timestamped_message: TimestampedMessage):
        """Handle connected signal."""
        pass
    
    def on_disconnected_signal(self, timestamped_message: TimestampedMessage):
        """Handle disconnected signal."""
        pass
    
    def on_pressure_updated_signal(self, timestamped_message: TimestampedMessage):
        """Handle pressure updated signal."""
        pass
    
    def on_vacuum_updated_signal(self, timestamped_message: TimestampedMessage):
        """Handle vacuum updated signal."""
        pass
    
    def on_status_updated_signal(self, timestamped_message: TimestampedMessage):
        """Handle status updated signal."""
        pass
    
    def on_error_signal(self, timestamped_message: TimestampedMessage):
        """Handle error signal."""
        pass
    
    # Interface methods
    def _on_pgva_connected(self):
        """
        Called when PGVA connection is established.
        Override this method to add custom connection setup logic.
        """
        logger.info("PGVA connection established")
        # Could add periodic status updates here
        # Could read initial device state here
    
    def _on_pgva_disconnected(self):
        """
        Called when PGVA connection is lost.
        Override this method to add custom disconnection cleanup logic.
        """
        logger.info("PGVA connection lost")
        self.is_enabled = False
