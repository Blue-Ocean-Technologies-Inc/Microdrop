from traits.api import Instance

from peripheral_device_controller_base.interfaces.i_peripheral_device_control_mixin_service import (
    IPeripheralDeviceControlMixinService,
)
from ..heater_serial_proxy import HeaterSerialProxy


class IHeaterControlMixinService(IPeripheralDeviceControlMixinService):
    """Interface for the heater control mixins. Narrows ``proxy`` to the heater
    serial proxy. This subclass is the heater's OWN service protocol so the plugin
    only composes heater mixins.
    """

    proxy = Instance(HeaterSerialProxy)
