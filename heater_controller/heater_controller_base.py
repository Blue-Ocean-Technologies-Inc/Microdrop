from traits.api import Instance, Str

from peripheral_device_controller_base.peripheral_device_controller_base import PeripheralDeviceControllerBase

from .heater_serial_proxy import HeaterSerialProxy
from .consts import DEVICE_NAME

from logger.logger_service import get_logger
logger = get_logger(__name__, level="INFO")


class HeaterControllerBase(PeripheralDeviceControllerBase):
    """Backend controller for the heater peripheral.

    All listener/routing/connection machinery is inherited from
    ``PeripheralDeviceControllerBase``; this subclass only pins the device
    identity and narrows the proxy trait type. No preferences yet.
    """
    _device_name = Str(DEVICE_NAME)
    listener_name = Str("heater_controller_listener")
    proxy = Instance(HeaterSerialProxy)
