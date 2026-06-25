from traits.api import provides, HasTraits, Instance

from ..interfaces.i_heater_control_mixin_service import IHeaterControlMixinService
from ..heater_serial_proxy import HeaterSerialProxy

from logger.logger_service import get_logger
logger = get_logger(__name__)


@provides(IHeaterControlMixinService)
class HeaterCommandSetterService(HasTraits):
    """Sends plain-text commands to the heater. Generic raw-command channel:
    forwards the message content straight to the device (``whoami``, ``scan``,
    ``stream_all``, ``pid_<heater>_<setpoint>``, ``all_off``, ...). Typed
    convenience commands can be added later as their own request handlers.
    """
    proxy = Instance(HeaterSerialProxy)

    def on_send_command_request(self, message):
        command = message.content
        if not command:
            logger.warning("Heater send_command request with empty content; ignoring")
            return
        with self.proxy.transaction_lock:
            self.proxy.send_command(command)
