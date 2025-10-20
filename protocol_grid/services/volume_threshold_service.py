import json
import time
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal, QTimer

from logger.logger_service import get_logger
from protocol_grid.services.force_calculation_service import ForceCalculationService

logger = get_logger(__name__)

class VolumeThresholdService(QObject):
    """Service for monitoring capacitance during protocol runs for detecting volume thresholds."""
    
    # signal emitted when target capacitance is reached
    threshold_reached = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitoring_active = False
        self._target_capacitance = None
        self._current_capacitance = None
        self._phase_start_time = None
        self._phase_duration = 0.0
        self._threshold_check_timer = QTimer()
        self._threshold_check_timer.setSingleShot(False)
        self._threshold_check_timer.setInterval(50)  # ms
        self._threshold_check_timer.timeout.connect(self._check_threshold)
        
    def calculate_target_capacitance(self, volume_threshold: float, 
                                   actuated_electrodes: Dict[str, bool],
                                   protocol_state) -> Optional[float]:
        """calculate target capacitance for current phase."""
        try:
            if volume_threshold <= 0.0:
                return None
                
            if not protocol_state.has_complete_calibration_data():
                logger.info("Incomplete calibration data for volume threshold calculation")
                return None
            
            calibration_data = protocol_state.get_calibration_data()
            active_electrodes_from_calibration = protocol_state.get_active_electrodes_from_calibration()
            
            # calculate capacitance per unit area
            c_unit_area = ForceCalculationService.calculate_capacitance_per_unit_area(
                calibration_data['liquid_capacitance'],
                calibration_data['filler_capacitance'],
                active_electrodes_from_calibration,
                calibration_data['electrode_areas']
            )
            
            if c_unit_area is None:
                logger.info("Could not calculate capacitance per unit area")
                return None
            
            # calculate actuated area for current phase
            actuated_area = 0.0
            for electrode_id, is_active in actuated_electrodes.items():
                if is_active and electrode_id in calibration_data['electrode_areas']:
                    actuated_area += calibration_data['electrode_areas'][electrode_id]
            
            if actuated_area <= 0:
                logger.info("No actuated area found for volume threshold calculation")
                return None
            
            target_capacitance = volume_threshold * actuated_area * c_unit_area
            
            logger.info(f"Volume threshold calculation: threshold={volume_threshold}, "
                       f"actuated_area={actuated_area}, c_unit_area={c_unit_area}, "
                       f"target_capacitance={target_capacitance}")
            
            return target_capacitance
            
        except Exception as e:
            logger.error(f"Error calculating target capacitance: {e}")
            return None
    
    def start_monitoring(self, target_capacitance: float, phase_duration: float):
        """start monitoring capacitance for threshold detection."""
        if target_capacitance is None or target_capacitance <= 0:
            logger.info("Invalid target capacitance, not starting monitoring")
            return False
            
        self._target_capacitance = target_capacitance
        self._phase_duration = phase_duration
        self._phase_start_time = time.time()
        self._monitoring_active = True
        
        logger.info(f"Starting volume threshold monitoring: target={target_capacitance}, "
                   f"duration={phase_duration}s")
        
        self._threshold_check_timer.start()
        return True
    
    def stop_monitoring(self):
        self._monitoring_active = False
        self._threshold_check_timer.stop()
        self._target_capacitance = None
        self._current_capacitance = None
        self._phase_start_time = None
        logger.info("Stopped volume threshold monitoring")
    
    def update_capacitance(self, capacitance_message: str):
        """Update current capacitance from hardware readings."""
        try:
            capacitance_data = json.loads(capacitance_message)
            capacitance_str = capacitance_data.get('capacitance', None)
            
            if capacitance_str is not None:
                # Extract numeric value from "123.45pF" format
                capacitance_value = float(capacitance_str.split("pF")[0])
                self._current_capacitance = capacitance_value
                
                if self._monitoring_active:
                    logger.debug(f"Capacitance update: {capacitance_value}pF (target: {self._target_capacitance}pF)")
                    
        except Exception as e:
            logger.error(f"Error parsing capacitance message: {e}")
    
    def _check_threshold(self):
        """Check if target capacitance for phase has been reached."""
        if not self._monitoring_active:
            logger.info("skipping check for whether target capacitance reached because not monitoring_active")
            return
            
        if self._target_capacitance is None:
            logger.info("skipping check for whether target capacitance reached because there is no target capacitance")
            return 
        
        if self._current_capacitance is None:
            logger.info("skipping check for whether target capacitance is reached becuase there is no current capacitance")
            return
            
        # check if target is reached
        if self._current_capacitance >= self._target_capacitance:
            elapsed_time = time.time() - self._phase_start_time if self._phase_start_time else 0
            logger.info(f"Volume threshold reached! Current: {self._current_capacitance}pF, "
                       f"Target: {self._target_capacitance}pF, Elapsed: {elapsed_time:.2f}s")
            
            self.stop_monitoring()
            self.threshold_reached.emit()
            return
            
        # check for timeout (this should not happen as phase timer handles it, but safety check)
        if self._phase_start_time:
            elapsed_time = time.time() - self._phase_start_time
            if elapsed_time >= self._phase_duration:
                logger.info(f"Volume threshold monitoring timeout after {elapsed_time:.2f}s "
                           f"(target not reached: {self._current_capacitance}pF < {self._target_capacitance}pF)")
                self.stop_monitoring()
    
    def is_monitoring_active(self) -> bool:
        return self._monitoring_active
    
    def get_current_status(self) -> Dict:
        """Get current monitoring status for debugging."""
        return {
            'monitoring_active': self._monitoring_active,
            'target_capacitance': self._target_capacitance,
            'current_capacitance': self._current_capacitance,
            'phase_start_time': self._phase_start_time,
            'phase_duration': self._phase_duration
        }