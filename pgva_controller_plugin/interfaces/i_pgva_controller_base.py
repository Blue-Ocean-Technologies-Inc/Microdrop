from traits.api import Bool, Float, Str
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase


class IPGVAControllerBase(IDramatiqControllerBase):
    """
    Interface for the PGVA Controller Service.
    Provides methods for controlling and monitoring a Festo PGVA device.
    """

    # Connection properties
    pgva_connection_active = Bool(
        desc="Specifies if the controller is actively connected to the PGVA device"
    )
    
    # Device properties
    device_ip = Str(desc="IP address of the PGVA device")
    device_port = Str(desc="Port number for communication with PGVA device")
    unit_id = Str(desc="Modbus unit ID for the PGVA device")
    
    # Current values
    current_pressure = Float(desc="Current pressure reading from PGVA")
    current_vacuum = Float(desc="Current vacuum reading from PGVA")
    target_pressure = Float(desc="Target pressure setpoint")
    target_vacuum = Float(desc="Target vacuum setpoint")
    
    # Status
    device_status = Str(desc="Current status of the PGVA device")
    is_enabled = Bool(desc="Whether the PGVA device is enabled")

    def _on_pgva_connected(self):
        """
        Method that should be called once a PGVA connection has been established.
        There should be a routine here to setup the new connection, such as:
        - Reading initial device status
        - Setting up periodic status updates
        - Configuring device parameters
        """
        pass

    def _on_pgva_disconnected(self):
        """
        Method that should be called when the PGVA connection is lost.
        Should handle cleanup and notify other components.
        """
        pass
