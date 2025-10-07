import json
import time
from contextlib import contextmanager
from typing import Dict, Generator, List, Optional, Tuple

import dramatiq
import numpy as np
import pandas as pd
from traits.api import HasTraits, List, Str, Int, Float, provides

from microdrop_application.consts import APP_GLOBALS_REDIS_HASH
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_dropbot_serial_proxy import DramatiqDropbotSerialProxy
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.pandas_helpers import map_series_to_array
from microdrop_utils.redis_manager import get_redis_hash_proxy
from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from dropbot_controller.consts import (
    DROPLETS_DETECTED,
    DROPLET_DETECTION_CAPACITANCE_THRESHOLD_FACTOR,
    DROPLET_DETECTION_FREQUENCY,
    DROPLET_DETECTION_CAPACITANCE_THRESHOLD_FACTOR_NO_AREA_NORMALIZATION,
)
from ..models.dropbot_channels_properties_model import DropbotChannelsPropertiesModel

logger = get_logger(__name__, level="DEBUG")

# --- Constants ---
PF_SCALE_FACTOR = 1e12  # Scale capacitances to picoFarads for logging


# --- Data Structures ---
class DetectionResult(HasTraits):
    """A structured data class for droplet detection results."""
    detected_channels = List(Int)
    error = Str("")


# --- Main Service Class ---
@provides(IDropbotControlMixinService)
class DropletDetectionMixinService(HasTraits):
    """
    Provides droplet detection by safely managing hardware state.
    """
    id = Str("droplet_detection_mixin_service")
    name = Str("Droplet Detection Mixin Service")

    _detection_timeout = Float(10.0)  # seconds
    _max_detection_retries = Int(2)

    # --------------------------------------------------------------------------
    # IDropbotControlMixinService Interface
    # --------------------------------------------------------------------------
    def on_detect_droplets_request(self, channels_json_str: str):
        """Handle a droplet detection request."""
        try:
            # Check for a valid hardware proxy connection
            if not hasattr(self, "proxy") or not self.proxy:
                self._publish_detection_response(error_message="Dropbot proxy not available.")
                return

            channels = json.loads(channels_json_str) if channels_json_str else []
            result = self._perform_safe_droplet_detection(channels)
            self._publish_detection_response(
                detected_channels=result.detected_channels, error_message=result.error
            )
        except json.JSONDecodeError:
            self._publish_detection_response(error_message="Invalid JSON in request.")
        except Exception as e:
            logger.error(f"Critical error during droplet detection request: {e}", exc_info=True)
            self._publish_detection_response(error_message=f"Critical error: {str(e)}")

    # --------------------------------------------------------------------------
    # Core Detection Logic
    # --------------------------------------------------------------------------
    def _perform_safe_droplet_detection(self, channels: list[int]) -> DetectionResult:
        """Orchestrate droplet detection with a retry mechanism."""
        last_error: Optional[Exception] = None
        total_attempts = self._max_detection_retries + 1

        with self._detection_context(self.proxy) as proxy:
            for attempt in range(total_attempts):
                try:
                    logger.debug(f"Droplet detection attempt {attempt + 1}/{total_attempts}")

                    detected = self._execute_detection_steps(proxy, channels)

                    return DetectionResult(detected_channels=detected)

                except Exception as e:
                    last_error = e
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < self._max_detection_retries:
                        time.sleep(1)  # Wait before retrying

        error_message = f"All {total_attempts} detection attempts failed. Last error: {last_error}"
        logger.error(error_message)
        return DetectionResult(error=error_message)

    def _execute_detection_steps(self, proxy: 'DramatiqDropbotSerialProxy', channels: list[int]) -> list[int]:
        """Run the sequence of operations to detect droplets."""
        capacitances_array = self._get_capacitances(proxy, channels)
        # normalized_caps, threshold_factor = self._normalize_capacitances(proxy, capacitances_array)

        channels_with_drops = self._find_channels_above_threshold(capacitances_array, threshold_factor=DROPLET_DETECTION_CAPACITANCE_THRESHOLD_FACTOR)

        if not channels_with_drops:
            logger.info("No droplets were detected.")
        return channels_with_drops

    # --------------------------------------------------------------------------
    # Helper Methods
    # --------------------------------------------------------------------------

    @staticmethod
    @contextmanager
    def _detection_context(proxy) -> Generator['DramatiqDropbotSerialProxy', None, None]:
        """
        A context manager to safely set and restore hardware state for detection.

        Temporarily applies detection-specific voltage and frequency settings
        and guarantees restoration of the original state, even if errors occur.
        """
        original_state = proxy.state
        logger.debug(f"Storing original state:\n {original_state}")

        try:
            with proxy.transaction_lock:
                proxy.update_state(hv_output_enabled=True, hv_output_selected=True,
                                   frequency=DROPLET_DETECTION_FREQUENCY)

                # proxy.frequency = DROPLET_DETECTION_FREQUENCY
                # proxy.voltage = DROPLET_DETECTION_VOLTAGE # also turns on HV unlike update_state(voltage=num)
                logger.info(f"Set detection state: F={proxy.frequency}Hz, V={proxy.voltage}V")
                time.sleep(0.05)  # Allow settings to settle
                yield proxy

        finally:
            # executes after with block. Get lock again.
            with proxy.transaction_lock:
                proxy.state = original_state
            logger.info(f"Restored original state:\n {proxy.state}")

    @staticmethod
    def _get_capacitances(proxy: 'DramatiqDropbotSerialProxy', channels: list[int]) -> np.ndarray:
        """Measure and scale capacitances from the hardware."""
        with proxy.transaction_lock:
            raw_capacitances = proxy.channel_capacitances(channels or None)
            capacitances = pd.Series(raw_capacitances, index=channels or proxy.active_channels)

        logger.debug(f"Capacitances (pF): {capacitances * PF_SCALE_FACTOR}")
        return map_series_to_array(capacitances)

    @staticmethod
    def _normalize_capacitances(proxy: 'DramatiqDropbotSerialProxy', capacitances: np.ndarray) -> Tuple[np.ndarray, float]:
        """Normalize capacitances by electrode area if available."""

        # check if channel areas are set globally

        microdrop_globals = get_redis_hash_proxy(
            redis_client=dramatiq.get_broker().client, hash_name=APP_GLOBALS_REDIS_HASH
        )
        channel_areas_dict = microdrop_globals.get("channel_electrode_areas")

        if not channel_areas_dict:
            logger.warning("No electrode areas found. Using raw capacitance.")
            return capacitances, DROPLET_DETECTION_CAPACITANCE_THRESHOLD_FACTOR_NO_AREA_NORMALIZATION

        logger.debug("Normalizing capacitances by electrode area.")

        # preparing channel areas to put through model and get channel-props array: keys need to be ints.
        channel_areas = {int(k): v for k, v in channel_areas_dict.items()}

        model = DropbotChannelsPropertiesModel(
            num_available_channels=proxy.number_of_channels,
            property_dtype=float,
            channels_properties_dict=channel_areas,
        )

        # Use np.divide to handle division by zero gracefully if any area is 0
        normalized_caps = np.divide(
            capacitances, model.channels_properties_array,
            out=np.full_like(capacitances, np.nan), where=model.channels_properties_array != 0
        )
        return normalized_caps, DROPLET_DETECTION_CAPACITANCE_THRESHOLD_FACTOR

    @staticmethod
    def _find_channels_above_threshold(capacitances: np.ndarray, threshold_factor: float) -> list[int]:
        """Identify channels where capacitance exceeds a dynamic threshold."""
        if np.all(np.isnan(capacitances)):
            logger.warning("All capacitance values are NaN.")
            return []

        threshold = np.nanmin(capacitances) * threshold_factor

        liquid_channels = np.where(
            (capacitances > threshold) & (~np.isnan(capacitances))
        )[0]

        liquid_channels = liquid_channels.tolist()

        logger.info(f"Detected liquid in channels: {liquid_channels}")
        return liquid_channels

    @staticmethod
    def _publish_detection_response(
            detected_channels: Optional[list[int]] = None,
            error_message: Optional[str] = None
    ):
        """Publish the droplet detection result (success or failure)."""
        is_success = not error_message

        response = {
            "success": is_success,
            "detected_channels": detected_channels or [],
            "error": error_message or "",
        }

        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(response))
        log_msg = f"Published detection result: Success={is_success}, Channels={response['detected_channels']}"
        logger.debug(log_msg)