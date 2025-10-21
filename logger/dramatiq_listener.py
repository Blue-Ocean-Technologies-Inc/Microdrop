import json
from functools import partial

from microdrop_utils.dramatiq_controller_base import basic_listener_actor_routine, DramatiqControllerBase


from traits.api import Callable

from .consts import listener_name

from .logger_service import get_logger, LEVELS
import logging
logger = get_logger(__name__)


class DramatiqLoggerControl(DramatiqControllerBase):
    id = "dramatiq_logger"
    name = "Dramatiq Logger"
    ##################### Dramatiq Controller Base Interface #######################
    listener_name = listener_name
    listener_actor_method = Callable

    def _listener_actor_method_default(self):
        """returns a default listener actor method for message routing"""
        return partial(basic_listener_actor_routine, self)

    def _on_change_log_level_triggered(self, message):
        ROOT_LOGGER = logging.getLogger()

        # set level if it is different from current level
        if LEVELS[message.upper()] != ROOT_LOGGER.getEffectiveLevel():
            ROOT_LOGGER.setLevel(LEVELS[message.upper()])
            logger.critical(f"Logging level changed to to {message}")


