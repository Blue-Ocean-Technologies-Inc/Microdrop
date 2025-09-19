import json
import time
import numpy as np
from typing import Dict, List, Optional

import pandas as pd
from svgwrite.data.pattern import frequency
from traits.api import provides, HasTraits, Str, Float, Instance, Int

from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from .global_proxy_state_manager import GlobalProxyStateManager
from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from dropbot_controller.consts import DROPLETS_DETECTED

logger = get_logger(__name__, level="DEBUG")

# Constants for droplet detection
DROPLET_DETECTION_FREQUENCY = 1000  # 1 kHz for droplet detection


@provides(IDropbotControlMixinService)
class DropletDetectionMixinService(HasTraits):
    """
    A mixin service that provides droplet detection functionality.
    Automatically manages frequency settings during detection.
    """

    id = Str('droplet_detection_mixin_service')
    name = Str('Droplet Detection Mixin Service')

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
            channels_areas_mapping = json.loads(message)
            
            # check if proxy is available
            if not hasattr(self, 'proxy') or self.proxy is None:
                self._publish_error_response("Dropbot proxy not available")
                return
            
            result = self._perform_safe_droplet_detection(target_channels)
            
            if result['success']:
                self._publish_success_response(result['detected_channels'])
            else:
                self._publish_error_response(result['error'])
                
        except Exception as e:
            logger.error(f"Critical error in droplet detection: {e}")
            self._publish_error_response(f"Critical error: {str(e)}")

    def _perform_safe_droplet_detection(self, target_channels=None) -> Dict[str, any]:
        """Perform droplet detection with enhanced safety measures."""
        
        for attempt in range(self._max_detection_retries + 1):
            try:
                logger.debug(f"Droplet detection attempt {attempt + 1}")
                
                with self.proxy_state_manager.safe_proxy_access("droplet_detection", timeout=self._detection_timeout):
                    
                    # Validate proxy state before starting
                    if not self._validate_detection_preconditions():
                        continue
                    
                    # Store original settings
                    original_state = self._store_original_settings()
                    
                    try:
                        # Prepare for detection
                        self._prepare_for_detection()
                        
                        # Perform actual detection
                        detected_channels = self._execute_droplet_detection(target_channels)
                        
                        return {
                            'success': True,
                            'detected_channels': detected_channels,
                            'error': None
                        }
                        
                    finally:
                        # Always restore original state
                        self._restore_original_settings(original_state)
                
            except Exception as e:
                logger.warning(f"Droplet detection attempt {attempt + 1} failed: {e}")
                
                if attempt < self._max_detection_retries:
                    logger.info(f"Retrying droplet detection in 1 second...")
                    time.sleep(1)
                else:
                    return {
                        'success': False,
                        'detected_channels': [],
                        'error': f"All detection attempts failed. Last error: {str(e)}"
                    }
        
        return {
            'success': False,
            'detected_channels': [],
            'error': "Maximum detection attempts exceeded"
        }

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

    def _execute_droplet_detection(self, target_channels=None) -> List[int]:
        """
        Execute the actual droplet detection.
        
        Parameters
        ----------
        target_channels : list or None
            List of channel numbers to check, or None detection on all channels.
            
        Returns
        -------
        list
            List of channels where droplets were detected.
        """
        proxy = self.proxy_state_manager.proxy
        
        # convert target channels to numpy array if specified
        channels_array = None
        if target_channels is not None:
            channels_array = np.array(target_channels, dtype=int)
            logger.debug(f"Performing targeted detection on {len(channels_array)} channels")
        else:
            channels_array = np.array(list(range(0, 50)), dtype=int)
            logger.debug("Performing full-device detection")
        
        # Perform droplet detection
        # detected_drops = proxy.get_drops(channels=channels_array, capacitance_threshold=5e-12)

        capacitances = pd.Series(proxy
                                 .channel_capacitances(channels_array),
                                 index=channels_array) * 1e12

        logger.critical(f"Capacitances: {capacitances}")
        logger.critical(f"Minimum Capacitance: {capacitances.min()}")

        liquid_channels = capacitances[capacitances > 10 * capacitances.min()]

        detected_drops = liquid_channels.index.tolist()

        if detected_drops is None:
            logger.warning("Droplet detection returned None")
            return []

        return detected_drops

        # Process results
        detected_channels = []
        current_channel_count = proxy.number_of_channels
        
        # for drop_array in detected_drops:
        #     if drop_array is not None and len(drop_array) > 0:
        #         # Validate drop array size
        #         if len(drop_array) > current_channel_count:
        #             logger.warning(f"Drop array too large: {len(drop_array)} > {current_channel_count}")
        #             continue
        #         detected_channels.extend(drop_array.tolist())
        
        # Validate and filter channel numbers
        # validated_channels = []
        # for ch in detected_channels:
        #     try:
        #         ch_int = int(ch)
        #         if 0 <= ch_int < current_channel_count:
        #             validated_channels.append(ch_int)
        #         else:
        #             logger.warning(f"Invalid channel number: {ch_int}")
        #     except (ValueError, TypeError) as e:
        #         logger.warning(f"Invalid channel value: {ch}, error: {e}")
        #
        logger.info(f"Detected droplets on channels: {validated_channels}")
        return validated_channels

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

    def _publish_success_response(self, detected_channels: List[int]):
        """Publish successful droplet detection response."""
        response = {
            "success": True,
            "detected_channels": detected_channels,
            "error": None
        }
        
        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(response))
        logger.debug(f"Published successful droplet detection response: {len(detected_channels)} channels")

    def _publish_error_response(self, error_message: str):
        """Publish error droplet detection response."""
        response = {
            "success": False,
            "detected_channels": [],
            "error": error_message
        }
        
        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(response))
        logger.debug(f"Published error droplet detection response: {error_message}")