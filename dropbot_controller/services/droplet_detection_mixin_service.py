import json
import time
from typing import Optional, Dict

import numpy as np
import pandas as pd
from traits.api import provides, HasTraits, Str, Int, List, Float

from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from dropbot_controller.consts import DROPLETS_DETECTED

logger = get_logger(__name__, level="DEBUG")

# Constants for droplet detection
DROPLET_DETECTION_FREQUENCY = 1000  # 1 kHz for droplet detection

class DetectionResult(HasTraits):
    """A structured data class for droplet detection results."""
    detected_channels = List(Int)
    error = Str("")


@provides(IDropbotControlMixinService)
class DropletDetectionMixinService(HasTraits):
    """
    A mixin service that provides droplet detection functionality.
    Automatically manages frequency settings during detection.
    """

    id = Str('droplet_detection_mixin_service')
    name = Str('Droplet Detection Mixin Service')

    _detection_timeout = Float(10.0)  # seconds
    _max_detection_retries = Int(2)

    #--------- IDropbotControlMixinService Interface ---------------------------
    def on_detect_droplets_request(self, message):
        """
        Handle droplet detection request.
        
        Parameters
        ---------
        message (str): A JSON string that is a dict[str, float]
            Contains channel id as the key, and corresponding total scaled area as the value:
            That is the sum of the electrode areas affected by the channel on the chip
        """
        try:
            channels = json.loads(message)
            
            # check if proxy is available
            if not hasattr(self, 'proxy') or self.proxy is None:
                self._publish_detection_response(error_message="Dropbot proxy not available")
                return
            
            result: DetectionResult = self._perform_safe_droplet_detection(channels)

            self._publish_detection_response(detected_channels=result.detected_channels, error_message=result.error)

                
        except Exception as e:
            logger.error(f"Critical error in droplet detection: {e}")
            self._publish_detection_response(error_message=f"Critical error: {str(e)}")

    def _attempt_single_detection(self, channels: list[int]):
        """
        Performs one attempt at droplet detection, restoring state upon completion.

        Returns:
            A list of detected channel integers on success.

        Raises:
            DetectionPreconditionError: If preconditions are not met.
            Exception: For other failures during the detection process.
        """
        with self.proxy_state_manager.safe_proxy_access("droplet_detection", timeout=self._detection_timeout):
            # Validate proxy state before starting
            if not self._validate_detection_preconditions():
                raise Exception("Validation of preconditions failed.")

            # Store and restore settings safely
            original_state = self._store_original_settings()
            try:
                self._prepare_for_detection()
                return self._execute_droplet_detection(channels)
            finally:
                self._restore_original_settings(original_state)

    def _perform_safe_droplet_detection(self, channels: list[int]) -> DetectionResult:
        """
        Performs droplet detection with retries and safety measures.

        This method orchestrates multiple detection attempts, handling exceptions
        and ensuring a consistent result format.
        """
        last_error: Optional[Exception] = None
        total_attempts = self._max_detection_retries + 1

        for attempt in range(total_attempts):
            try:
                logger.debug(f"Droplet detection attempt {attempt + 1}/{total_attempts}")

                # Execute a single, isolated detection attempt.
                detected_channels = self._attempt_single_detection(channels)

                # If the attempt succeeds, return the result immediately.
                return DetectionResult(detected_channels=detected_channels, error="")

            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

                # If more attempts are left, wait before retrying.
                if attempt < self._max_detection_retries:
                    logger.info("Retrying detection in 1 second...")
                    time.sleep(1)

        # If the loop completes, all attempts have failed.
        error_message = f"All {total_attempts} detection attempts failed. Last error: {last_error}"
        logger.error(error_message)
        return DetectionResult(detected_channels=[], error=error_message)

    def _execute_droplet_detection(self, channels: list[int]) -> list[int]:
        """
        Execute the actual droplet detection.

        Parameters
        ----------
        channels : list or None
            List of channel numbers to check

        Returns
        -------
        list
            List of channels where droplets were detected.
        """
        proxy = self.proxy_state_manager.proxy

        capacitances = pd.Series(proxy.channel_capacitances(channels), index=channels) * 1e12 # scale to log values in in pF units

        logger.critical(f"Capacitances: {capacitances}")
        logger.critical(f"Minimum Capacitance: {capacitances.min()}")

        liquid_channels = capacitances[capacitances > 10 * capacitances.min()]

        logger.critical(f"Liquid channels: {liquid_channels}")

        detected_drops = liquid_channels.index.tolist()

        if detected_drops is None:
            logger.warning("Droplet detection returned None")
            return []

        return detected_drops


    def _validate_detection_preconditions(self) -> bool:
        """Validate that proxy is ready for droplet detection."""
        try:
            proxy = self.proxy_state_manager.proxy
            
            # Check basic proxy state
            channel_count = proxy.number_of_channels
            if channel_count != 120:
                logger.error(f"Invalid channel count for detection: {channel_count}")
                return False
            
            # Check state consistency
            current_state = proxy.state_of_channels
            if len(current_state) != channel_count:
                logger.error(f"State inconsistency detected: {len(current_state)} != {channel_count}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Precondition validation failed: {e}")
            return False

    def _store_original_settings(self) -> Dict[str, any]:
        """Store original proxy settings for restoration."""
        try:
            proxy = self.proxy_state_manager.proxy
            return {
                'state': np.copy(proxy.state_of_channels),
                'frequency': proxy.frequency,
                'voltage': proxy.voltage
            }
        except Exception as e:
            logger.error(f"Failed to store original settings: {e}")
            return {}

    def _prepare_for_detection(self):
        """Prepare proxy for droplet detection."""
        proxy = self.proxy_state_manager.proxy
        
        # Turn off all channels
        logger.debug("Turning off all channels for droplet detection")
        proxy.turn_off_all_channels()
        
        # Small delay for channel settling
        time.sleep(0.05)
        
        # Set detection frequency
        if proxy.frequency > DROPLET_DETECTION_FREQUENCY:
            proxy.update_state(frequency=DROPLET_DETECTION_FREQUENCY)
            logger.debug(f"Set frequency to {DROPLET_DETECTION_FREQUENCY} Hz")

            # Small delay for frequency settling
            time.sleep(0.05)

    def _restore_original_settings(self, original_settings: Dict[str, any]):
        """Restore original proxy settings."""
        if not original_settings:
            logger.warning("No original settings to restore")
            return
        
        try:
            proxy = self.proxy_state_manager.proxy
            
            # Restore frequency
            if 'frequency' in original_settings:
                proxy.update_state(frequency=original_settings['frequency'])
                logger.debug(f"Restored frequency to {original_settings['frequency']} Hz")
            
            # # Restore voltage
            # if 'voltage' in original_settings:
            #     proxy.update_state(frequency=original_settings['voltage'])
            #     logger.debug(f"Restored voltage to {original_settings['voltage']} V")
            
            # # Restore electrode state
            # if 'state' in original_settings:
            #     original_state = original_settings['state']
            #     if len(original_state) == proxy.number_of_channels:
            #         proxy.state_of_channels = original_state
            #         logger.debug(f"Restored electrode state: {original_state.sum()} active channels")
            #     else:
            #         logger.error(f"Cannot restore state: size mismatch {len(original_state)} != {proxy.number_of_channels}")
                    
        except Exception as e:
            logger.error(f"Failed to restore original settings: {e}")

    def _publish_detection_response(
            self,
            detected_channels: Optional[list[int]] = None,
            error_message: Optional[str] = None
    ):
        """
        Publishes a droplet detection response for success or failure cases.

        If an `error_message` is provided, it publishes a failure response.
        Otherwise, it publishes a success response with the `detected_channels`.

        Args:
            detected_channels: A list of channel integers for a success response.
            error_message: A string describing an error, indicating a failure response.
        """
        # Determine if the operation was successful based on the presence of an error message.

        if error_message == "":
            # For a success case, use the provided channels or an empty list.
            channels = detected_channels if detected_channels is not None else []
            log_msg = f"Published successful droplet detection response: {len(channels)} channels"
        else:
            # For an error case, the channel list is always empty.
            channels = []
            log_msg = f"Published error droplet detection response: {error_message}"

        # Construct the response payload.
        response = {
            "success": error_message == "",
            "detected_channels": channels,
            "error": error_message,
        }

        # Publish the JSON-serialized message and log the action.
        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(response))
        logger.debug(log_msg)