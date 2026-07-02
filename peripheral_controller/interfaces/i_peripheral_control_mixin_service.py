from traits.api import Instance

from peripheral_controller.dramatiq_peripheral_serial_proxy import DramatiqPeripheralSerialProxy
from peripheral_device_controller_base.interfaces.i_peripheral_device_control_mixin_service import (
    IPeripheralDeviceControlMixinService,
)


class IPeripheralControlMixinService(IPeripheralDeviceControlMixinService):
    """Interface for the z-stage magnet control mixins. Narrows ``proxy`` to the
    mr-box serial proxy. This subclass is the magnet's OWN service protocol so the
    plugin only composes magnet mixins.
    """

    proxy = Instance(DramatiqPeripheralSerialProxy)
