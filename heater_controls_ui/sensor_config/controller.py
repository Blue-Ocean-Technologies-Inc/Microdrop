"""Handler for the Configure Sensors & Heaters dialog.

Button actions publish board requests; the responses flow back asynchronously
through the heater message handler into the shared SensorConfigModel, so the
dialog never touches the serial port itself.
"""
from traitsui.api import Controller

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from heater_controller.consts import SCAN_SENSORS, DUMP_CONFIG

from logger.logger_service import get_logger
logger = get_logger(__name__)


class SensorConfigController(Controller):
    """TraitsUI handler: maps the dialog's buttons to board-request publishes."""

    def scan_sensors(self, info=None):
        logger.info("Configurator: requesting a 1-Wire sensor scan")
        publish_message(message="", topic=SCAN_SENSORS)

    def refresh_from_board(self, info=None):
        logger.info("Configurator: requesting a config refresh from the board")
        publish_message(message="", topic=DUMP_CONFIG)
