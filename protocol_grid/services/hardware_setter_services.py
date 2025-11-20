from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger
from dropbot_controller.consts import SET_VOLTAGE, SET_FREQUENCY
from peripheral_controller.consts import MAX_ZSTAGE_HEIGHT_MM, MIN_ZSTAGE_HEIGHT_MM
from peripheral_controller.datamodels import ZStageConfigData

logger = get_logger(__name__)


class VoltageFrequencyService:
    """Manage voltage and frequency publishing during protocol execution."""
    
    @staticmethod
    def validate_voltage(voltage_str):
        """validate and return voltage value within acceptable range."""
        try:
            voltage = float(voltage_str)
            if 30 <= voltage <= 150:
                return voltage
            else:
                logger.info(f"Voltage {voltage}V out of range (30-150V), using default 100V")
                return 100.0
        except (ValueError, TypeError):
            logger.info(f"Invalid voltage value '{voltage_str}', using default 100V")
            return 100.0
    
    @staticmethod
    def validate_frequency(frequency_str):
        """validate and return frequency value within acceptable range."""
        try:
            frequency = float(frequency_str)
            if 100 <= frequency <= 20000:
                return frequency
            else:
                logger.info(f"Frequency {frequency}Hz out of range (100-20000Hz), using default 10000Hz")
                return 10000.0
        except (ValueError, TypeError):
            logger.info(f"Invalid frequency value '{frequency_str}', using default 10000Hz")
            return 10000.0


    @staticmethod
    def publish_immediate_voltage_frequency(voltage_str, frequency_str, preview_mode=False):
        """publish voltage/frequency immediately for advanced mode edits."""
        if preview_mode:
            logger.info("Skipping voltage/frequency publishing in preview mode")
            return

        voltage = VoltageFrequencyService.validate_voltage(voltage_str)
        frequency = VoltageFrequencyService.validate_frequency(frequency_str)

        try:
            publish_message(topic=SET_VOLTAGE, message=str(voltage))
            logger.info(f"Published voltage: {voltage}V")
        except Exception as e:
            logger.info(f"Failed to publish voltage: {e}")

        try:
            publish_message(topic=SET_FREQUENCY, message=str(frequency))
            logger.info(f"Published immediate frequency: {frequency}Hz")
        except Exception as e:
            logger.info(f"Failed to publish frequency: {e}")


    def publish_step_voltage_frequency(self, step, preview_mode=False):
        """publish voltage and frequency for a step execution."""

        logger.info(f"Trying to Publish voltage and frequency for step {step}")

        voltage_str = step.parameters.get("Voltage", "100.0")
        frequency_str = step.parameters.get("Frequency", "10000")

        self.publish_immediate_voltage_frequency(voltage_str, frequency_str, preview_mode)


class MagnetService:
    @staticmethod
    def validate_magnet_height(magnet_str):
        """validate and return magnet height value within acceptable range."""
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

    # @staticmethod



