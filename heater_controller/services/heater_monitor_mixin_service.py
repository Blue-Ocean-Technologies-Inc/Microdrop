from serial.tools.list_ports import grep
from traits.api import provides, Str, List

from peripheral_device_controller_base.services.peripheral_device_monitor_mixin_service import (
    PeripheralDeviceMonitorMixinService,
)
from logger.logger_service import get_logger

from ..interfaces.i_heater_control_mixin_service import IHeaterControlMixinService
from ..heater_serial_proxy import HeaterSerialProxy
from ..consts import HEATER_HWID, DEVICE_NAME

logger = get_logger(__name__)


@provides(IHeaterControlMixinService)
class HeaterMonitorMixinService(PeripheralDeviceMonitorMixinService):
    """Monitors for the heater controller (RP2040) connection."""
    id = Str(f"{DEVICE_NAME}_monitor_mixin_service")
    name = Str(f'{DEVICE_NAME.title()} Monitor Mixin')

    _default_hwids = List(Str, [HEATER_HWID])

    def _make_proxy(self, port_name):
        return HeaterSerialProxy(port=port_name)

    def _find_port(self, hwids):
        """Locate the heater's serial port by matching its VID:PID directly.

        The shared ``check_devices_available`` greps for a ``USB Serial``
        description first, which the RP2040 CDC port doesn't always carry; here we
        match the VID:PID against the full hardware id instead.
        """
        for hwid in hwids:
            for port in grep(hwid):
                logger.info(f"Heater found on port {port.device} ({port.description})")
                return str(port.device)
        raise Exception(f"No heater for hwids {hwids} found")
