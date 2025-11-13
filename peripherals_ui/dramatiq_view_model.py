from traits.has_traits import HasTraits
from traits.trait_types import Instance

# local imports
from logger.logger_service import get_logger
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.datetime_helpers import TimestampedMessage

from peripheral_controller.consts import RETRY_CONNECTION

from .model import PeripheralModel

logger = get_logger(__name__)

class DramatiqStatusViewModel(HasTraits):

    model = Instance(PeripheralModel)

    def traits_init(self):
        self.connected_message = TimestampedMessage("", 0) # We initialize it timestamp 0 so any message will be newer. The string is not important.
        self.realtime_mode_message = TimestampedMessage("", 0)

    ###################################################################################################################
    # Publisher methods
    ###################################################################################################################
    def request_retry_connection(self):
        logger.info(f"{self.model.device_name}Retrying connection...")
        publish_message("Retry connection button triggered", RETRY_CONNECTION)

    ###################################################################################################################
    # Subscriber methods
    ###################################################################################################################

    ######################################### Handler methods #############################################

    @timestamped_value('connected_message')
    def _on_disconnected_triggered(self, body):
        logger.info(f"{self.model.device_name}Disconnected: {body}")
        self.model.status = False

    @timestamped_value('connected_message')
    def _on_connected_triggered(self, body):
        logger.info(f"{self.model.device_name}Connected: {body}")
        self.model.status = True

    @timestamped_value('realtime_mode_message')
    def _on_set_realtime_mode_triggered(self, body):
        self.model.realtime_mode = body == 'True'

    def _on_position_updated_triggered(self, body):
        self.model.position = float(body)