import json

from traits.api import observe
from traitsui.api import Controller

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    PMT_ACQUIRE, PMT_POWER, PMT_SET_GAIN,
)

logger = get_logger(__name__)


class PmtController(Controller):
    """Buttons -> request topics; results come back through the
    message handler on PMT_UPDATED."""

    @observe("model:pmt_power")
    def _on_pmt_power_changed(self, event):
        publish_message(topic=PMT_POWER, message=str(bool(event.new)))
        logger.info(f"PMT power --> {'on' if event.new else 'off'}")

    @observe("model:set_gain_button")
    def _set_gain(self, event):
        publish_message(topic=PMT_SET_GAIN,
                        message=str(int(self.model.pmt_gain)))

    @observe("model:acquire_button")
    def _acquire(self, event):
        self.model.pmt_status_display = "acquiring..."
        publish_message(topic=PMT_ACQUIRE, message=json.dumps(
            {"gain": int(self.model.pmt_gain)}))
        logger.info("Requested PMT acquire macro")
