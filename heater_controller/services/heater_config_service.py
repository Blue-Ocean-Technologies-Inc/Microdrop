from traits.api import provides, HasTraits, Instance

from ..interfaces.i_heater_control_mixin_service import IHeaterControlMixinService
from ..heater_serial_proxy import HeaterSerialProxy

from logger.logger_service import get_logger
logger = get_logger(__name__)


@provides(IHeaterControlMixinService)
class HeaterConfigService(HasTraits):
    """Board operations for the 'Configure Sensors & Heaters' editor.

    ``on_dump_config_request``  -> send ``dump_config``; the proxy captures the
        CONFIG_BEGIN/END reply and publishes it on CONFIG_DUMPED.
    ``on_scan_sensors_request`` -> run a 1-Wire bus scan; the proxy collects the
        ``Sensor N: <rom>`` reply lines and publishes them on SENSORS_SCANNED.

    Both only run while connected (the base listener gates requests on the
    connection), so a missing proxy can't be hit here.
    """
    proxy = Instance(HeaterSerialProxy)

    def on_dump_config_request(self, message):
        logger.info("Heater dump_config requested")
        with self.proxy.transaction_lock:
            self.proxy.send_command("dump_config")

    def on_scan_sensors_request(self, message):
        logger.info("Heater 1-Wire sensor scan requested")
        self.proxy.scan_sensors()
