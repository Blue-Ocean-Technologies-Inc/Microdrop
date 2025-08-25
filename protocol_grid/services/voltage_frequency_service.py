from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils._logger import get_logger
from dropbot_controller.consts import SET_VOLTAGE, SET_FREQUENCY

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
    def publish_step_voltage_frequency(step, preview_mode=False):
        """publish voltage and frequency for a step execution."""
        if preview_mode:
            logger.info("Skipping voltage/frequency publishing in preview mode")
            return
        
        voltage_str = step.parameters.get("Voltage", "100.0")
        frequency_str = step.parameters.get("Frequency", "10000")
        
        voltage = VoltageFrequencyService.validate_voltage(voltage_str)
        frequency = VoltageFrequencyService.validate_frequency(frequency_str)
        
        try:
            publish_message(topic=SET_VOLTAGE, message=str(voltage))
            logger.info(f"Published voltage: {voltage}V for step")
        except Exception as e:
            logger.info(f"Failed to publish voltage: {e}, using runtime default 100V")
            try:
                publish_message(topic=SET_VOLTAGE, message="100.0")
            except Exception as fallback_e:
                logger.info(f"Failed to publish fallback voltage: {fallback_e}")
        
        try:
            publish_message(topic=SET_FREQUENCY, message=str(frequency))
            logger.info(f"Published frequency: {frequency}Hz for step")
        except Exception as e:
            logger.error(f"Failed to publish frequency: {e}, using runtime default 10000Hz")
            try:
                publish_message(topic=SET_FREQUENCY, message="10000")
            except Exception as fallback_e:
                logger.error(f"Failed to publish fallback frequency: {fallback_e}")
    
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
            logger.info(f"Published immediate voltage: {voltage}V (advanced mode edit)")
        except Exception as e:
            logger.info(f"Failed to publish immediate voltage: {e}")

        try:
            publish_message(topic=SET_FREQUENCY, message=str(frequency))
            logger.info(f"Published immediate frequency: {frequency}Hz (advanced mode edit)")
        except Exception as e:
            logger.info(f"Failed to publish immediate frequency: {e}")


