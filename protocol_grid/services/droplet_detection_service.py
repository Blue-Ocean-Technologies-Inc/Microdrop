import numpy as np
from typing import Dict, List, Optional, Set
from PySide6.QtCore import QObject, Signal, QTimer

from logger.logger_service import get_logger
from protocol_grid.state.device_state import DeviceState

logger = get_logger(__name__)


class DropletDetectionService(QObject):
    """service for detecting droplets at electrode locations using dropbot proxy."""
    
    detection_failed = Signal(list, list)  # expected_electrodes, detected_electrodes
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dropbot_controller = None
        self._initialized = False
    
    def initialize(self, dropbot_controller):
        """initialize with dropbot controller reference."""
        self._dropbot_controller = dropbot_controller
        self._initialized = True
        logger.info(f"Droplet detection service initialized with controller: {type(dropbot_controller)}")
    
    def is_initialized(self):
        """check if service is properly initialized."""
        is_init = self._initialized and self._dropbot_controller is not None
        if not is_init:
            logger.debug(f"Droplet detection service not initialized: _initialized={self._initialized}, _dropbot_controller={self._dropbot_controller is not None}")
        return is_init
    
    def check_droplets_at_electrodes(self, device_state: DeviceState, 
                                   target_electrodes: Dict[str, bool],
                                   preview_mode: bool = False) -> Dict[str, bool]:
        """
        check if droplets are present at target electrodes.
        
        Parameters
        ----------
        device_state : DeviceState
            Device state containing electrode to channel mapping
        target_electrodes : Dict[str, bool]
            Dictionary of electrode IDs to check (only True values are checked)
        preview_mode : bool
            If True, skip hardware check and return success
            
        Returns
        -------
        Dict[str, bool]
            Result dictionary with keys:
            - 'success': True if all target electrodes have droplets
            - 'expected_electrodes': List of electrode IDs that were expected to have droplets
            - 'detected_electrodes': List of electrode IDs that actually have droplets
            - 'missing_electrodes': List of electrode IDs missing droplets
        """
        if preview_mode:
            logger.info("Skipping droplet detection in preview mode")
            expected_electrodes = [eid for eid, active in target_electrodes.items() if active]
            return {
                'success': True,
                'expected_electrodes': expected_electrodes,
                'detected_electrodes': expected_electrodes.copy(),
                'missing_electrodes': []
            }
        
        if not self.is_initialized():
            logger.info("Droplet detection service not initialized, treating as failure")
            expected_electrodes = [eid for eid, active in target_electrodes.items() if active]
            return {
                'success': False,
                'expected_electrodes': expected_electrodes,
                'detected_electrodes': [],
                'missing_electrodes': expected_electrodes.copy()
            }
        
        # list of electrode IDs that should have droplets
        expected_electrode_ids = [eid for eid, active in target_electrodes.items() if active]
        
        if not expected_electrode_ids:
            # no electrodes to check
            logger.info("No electrodes to check for droplets")
            return {
                'success': True,
                'expected_electrodes': [],
                'detected_electrodes': [],
                'missing_electrodes': []
            }
        
        try:
            # Check if dropbot controller has proxy
            if not hasattr(self._dropbot_controller, 'proxy') or self._dropbot_controller.proxy is None:
                logger.info("Dropbot controller proxy not available")
                return {
                    'success': False,
                    'expected_electrodes': expected_electrode_ids,
                    'detected_electrodes': [],
                    'missing_electrodes': expected_electrode_ids.copy()
                }
            
            # convert electrode IDs to channel numbers
            expected_channels = []
            for electrode_id in expected_electrode_ids:
                if electrode_id in device_state.id_to_channel:
                    channel = device_state.id_to_channel[electrode_id]
                    expected_channels.append(channel)
                else:
                    # try converting directly
                    try:
                        channel = int(electrode_id)
                        if any(ch == channel for ch in device_state.id_to_channel.values()):
                            expected_channels.append(channel)
                        else:
                            logger.info(f"Electrode ID {electrode_id} not found in device mapping")
                    except ValueError:
                        logger.info(f"Could not convert electrode ID {electrode_id} to channel")

            if not expected_channels:
                logger.info("No valid channels found for droplet detection")
                return {
                    'success': False,
                    'expected_electrodes': expected_electrode_ids,
                    'detected_electrodes': [],
                    'missing_electrodes': expected_electrode_ids.copy()
                }
            
            # call dropbot proxy get_drops
            expected_channels_array = np.array(expected_channels, dtype=int)
            logger.info(f"Checking droplets on channels: {expected_channels}")
            
            detected_drops = self._dropbot_controller.proxy.get_drops(
                channels=expected_channels_array,
            )
            
            # flatten detected drops into a set of channels
            detected_channels = set()
            for drop in detected_drops:
                detected_channels.update(drop.tolist())
            
            logger.info(f"Detected drops on channels: {list(detected_channels)}")
            
            # convert detected channels back to electrode IDs
            detected_electrode_ids = []
            channel_to_electrode = {ch: eid for eid, ch in device_state.id_to_channel.items()}
            
            for channel in detected_channels:
                if channel in channel_to_electrode:
                    detected_electrode_ids.append(channel_to_electrode[channel])
                else:
                    # try converting directly
                    detected_electrode_ids.append(str(channel))
            
            # check if all expected electrodes were detected
            expected_set = set(expected_electrode_ids)
            detected_set = set(detected_electrode_ids)
            missing_electrodes = list(expected_set - detected_set)
            
            success = len(missing_electrodes) == 0
            
            logger.info(f"Droplet detection: Expected {len(expected_electrode_ids)} electrodes, "
                       f"detected {len(detected_electrode_ids)}, missing {len(missing_electrodes)}")
            
            return {
                'success': success,
                'expected_electrodes': expected_electrode_ids,
                'detected_electrodes': detected_electrode_ids,
                'missing_electrodes': missing_electrodes
            }
            
        except Exception as e:
            logger.info(f"Error during droplet detection: {e}")
            return {
                'success': False,
                'expected_electrodes': expected_electrode_ids,
                'detected_electrodes': [],
                'missing_electrodes': expected_electrode_ids.copy()
            }