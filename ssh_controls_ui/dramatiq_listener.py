import dramatiq

from traits.api import HasTraits, provides, Instance

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    IDramatiqControllerBase, 
    basic_listener_actor_routine, 
    generate_class_method_dramatiq_listener_actor
)

from .view_model import SSHControlViewModel

from .consts import listener_name

logger = get_logger(__name__)


@provides(IDramatiqControllerBase)
class SSHControlUIListener(HasTraits):
    ui = Instance(SSHControlViewModel)

    ###################################################################################
    # IDramatiqControllerBase Interface
    ###################################################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = listener_name

    def traits_init(self):
        logger.info("Starting SSH controls UI listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine)

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self.ui, message, topic)


