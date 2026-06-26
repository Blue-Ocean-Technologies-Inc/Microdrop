from traits.api import provides, Str, List

from microdrop_utils.dramatiq_peripheral_serial_proxy import DramatiqPeripheralSerialProxy
from logger.logger_service import get_logger

from peripheral_device_controller_base.services.peripheral_device_monitor_mixin_service import (
    PeripheralDeviceMonitorMixinService,
)
from ..interfaces.i_peripheral_control_mixin_service import IPeripheralControlMixinService
from ..consts import MR_BOX_HWID, DEVICE_NAME

logger = get_logger(__name__)


@provides(IPeripheralControlMixinService)
class PeripheralMonitorMixinService(PeripheralDeviceMonitorMixinService):
    """Monitors for the z-stage magnet (mr-box peripheral board) connection."""
    id = Str(f"{DEVICE_NAME}_monitor_mixin_service")
    name = Str(f'{DEVICE_NAME.title()} Monitor Mixin')

    _default_hwids = List(Str, [MR_BOX_HWID])

    def _make_proxy(self, port_name):
        return DramatiqPeripheralSerialProxy(port=port_name)
