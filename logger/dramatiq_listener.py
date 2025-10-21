import json

from microdrop_utils.dramatiq_controller_base import basic_listener_actor_routine, DramatiqControllerBase


from traits.api import Callable

from .consts import listener_name

from .logger_service import get_logger, LEVELS
import logging
logger = get_logger(__name__)


class DramatiqLoggerControl(DramatiqControllerBase):
    listener_name = listener_name
    listener_actor_method = Callable

    def _listener_actor_method_default(self):

        def listener_actor_routine(self, message, topic):
            return basic_listener_actor_routine(self, message, topic)

        return listener_actor_routine

    def _on_change_log_level_triggered(self, message):
        ROOT_LOGGER = logging.getLogger()
        msg = json.loads(message)
        ROOT_LOGGER.setLevel(LEVELS[msg.get("level")])


