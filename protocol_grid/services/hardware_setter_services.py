import time

import dramatiq

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger
from dropbot_controller.consts import SET_VOLTAGE, SET_FREQUENCY
from peripheral_controller.consts import MAX_ZSTAGE_HEIGHT_MM, MIN_ZSTAGE_HEIGHT_MM, SET_POSITION, MOVE_UP, MOVE_DOWN, \
    GO_HOME

logger = get_logger(__name__)

@dramatiq.actor
def publish_voltage_frequency(voltage, frequency, preview_mode=False):
    """publish voltage and frequency for a step execution."""

    if preview_mode:
        logger.info("Skipping voltage/frequency publishing in preview mode")
        return

    logger.info(f"Trying to Publish voltage and frequency for step: {voltage}V and frequency: {frequency}Hz")
    publish_message(topic=SET_VOLTAGE, message=str(voltage))
    publish_message(topic=SET_FREQUENCY, message=str(frequency))


class MagnetService:
    @staticmethod
    def validate_magnet_height(magnet_str):
        """validate and return magnet height value within acceptable range."""
        if magnet_str == "Default":
            return "Default"
        try:
            magnet_height = float(magnet_str)
            if MIN_ZSTAGE_HEIGHT_MM < magnet_height < MAX_ZSTAGE_HEIGHT_MM:
                return magnet_height
            else:
                return 0

        except Exception as e:
            err = e
            logger.info(f"Failed to validate magnet height: {err}. Returning 0")
            return 0

    @staticmethod
    def publish_magnet_height(magnet_str):
        """publish magnet height for a step execution."""
        logger.info(f"Trying to Publish magnet height for step {magnet_str}")
        # validate height
        magnet_height = MagnetService.validate_magnet_height(magnet_str)
        logger.info(f"Magnet height is {magnet_height}")

        if magnet_height == 'Default':
            publish_message("", MOVE_UP)
            logger.info(f"No magnet height given. Using the configured Default Up height.")

        else:
            logger.info(f"Published magnet height: {magnet_height}")
            publish_message(str(magnet_height), SET_POSITION)


    @staticmethod
    def publish_magnet_home():
        """publish magnet home for a step execution."""
        publish_message("", MOVE_DOWN)
        time.sleep(0.3) # settling time before next command.
        publish_message("", GO_HOME)
