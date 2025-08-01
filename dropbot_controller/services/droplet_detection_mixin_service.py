import json
import time
import numpy as np
from typing import Dict, List, Optional

from traits.api import provides, HasTraits, Str, Float, Dict as TraitsDict

from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

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
    
    # to track original frequency for restoration
    _original_frequency = Float(10000.0)
    # _detection_in_progress = Dict(key_trait=Str(), value_trait=bool)

    def on_detect_droplets_request(self, message):
        """
        Handle droplet detection request. detection is performed on all channels.
        """
        try:
            logger.info("Starting droplet detection")
            
            # check if proxy is available
            if not hasattr(self, 'proxy') or self.proxy is None:
                self._publish_error_response("Dropbot proxy not available")
                return
            
            # store original frequency
            self._original_frequency = self.proxy.frequency
            logger.debug(f"Stored original frequency: {self._original_frequency} Hz")
            
            # set frequency to 1000Hz for detection
            self.proxy.frequency = DROPLET_DETECTION_FREQUENCY
            logger.debug(f"Set frequency to {DROPLET_DETECTION_FREQUENCY} Hz for detection")
            
            # small delay to let frequency settle
            time.sleep(0.01)
            
            # Perform droplet detection on all channels
            detected_drops = self.proxy.get_drops(channels=None) # check all channels
            
            detected_channels = []
            for drop_array in detected_drops:
                detected_channels.extend(drop_array.tolist())
            
            # convert to integers to ensure JSON serialization works
            detected_channels = [int(ch) for ch in detected_channels]
            
            logger.info(f"Detected droplets on channels: {detected_channels}")
            
            # restore original frequency
            self.proxy.frequency = self._original_frequency
            logger.debug(f"Restored frequency to {self._original_frequency} Hz")
            
            self._publish_success_response(detected_channels)
            
        except Exception as e:
            logger.error(f"Error during droplet detection: {e}")
            
            # restore frequency even if detection fails for any reason
            try:
                if hasattr(self, 'proxy') and self.proxy is not None:
                    self.proxy.frequency = self._original_frequency
                    logger.debug(f"Restored frequency after error to {self._original_frequency} Hz")
            except Exception as restore_error:
                logger.error(f"Failed to restore frequency after error: {restore_error}")
            
            self._publish_error_response(str(e))

    def _publish_success_response(self, detected_channels: List[int]):
        """Publish successful droplet detection response."""
        response = {
            "success": True,
            "detected_channels": detected_channels,
            "error": None
        }
        
        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(response))
        logger.debug(f"Published successful droplet detection response: {response}")

    def _publish_error_response(self, error_message: str):
        """Publish error droplet detection response."""
        response = {
            "success": False,
            "detected_channels": [],
            "error": error_message
        }
        
        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(response))
        logger.debug(f"Published error droplet detection response: {response}")