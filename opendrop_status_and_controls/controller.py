import functools

from traits.api import observe, Dict
from traitsui.api import (
    Controller,
)

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.decorators import debounce

from dropbot_controller.consts import (
    SET_VOLTAGE,
    SET_FREQUENCY,
    SET_REALTIME_MODE,
)

logger = get_logger(__name__)

class ControlsController(Controller):
    # Use a dict to store the *latest* task for each topic
    message_dict = Dict()
    ###################################################################################
    # Controller interface — debounced setattr
    ###################################################################################

    # This callback will not call update_editor() when it is not debounced!
    # This is likely because update_editor is only called by 'external' trait changes, and the new thread spawned by the decorator appears as such
    @debounce(wait_seconds=1)
    def realtime_mode_setattr(self, info, object, traitname, value):
        logger.debug(f"Set realtime mode to {value}")
        info.realtime_mode.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    ###################################################################################
    # Trait notification handlers
    ###################################################################################

    @observe("model:realtime_mode")
    def _realtime_mode_changed(self, event):
        publish_message(topic=SET_REALTIME_MODE, message=str(event.new))