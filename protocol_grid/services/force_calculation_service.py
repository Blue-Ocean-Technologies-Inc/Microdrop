import math
from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import Qt

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

class ForceCalculationService:
    """Service for calculating forces based on calibration data and voltages."""
    
    @staticmethod
    def calculate_capacitance_per_unit_area(liquid_capacitance: float, 
                                          filler_capacitance: float,
                                          active_electrodes: List[str],
                                          electrode_areas: Dict[str, float]) -> Optional[float]:
        """
        Calculate capacitance per unit area from calibration data.
        
        Args:
            liquid_capacitance: Total liquid capacitance
            filler_capacitance: Total filler capacitance  
            active_electrodes: List of electrode IDs that were active during calibration
            electrode_areas: Dictionary mapping electrode IDs to their areas
            
        Returns:
            Capacitance per unit area, or None if calculation not possible
        """
        try:
            # validate inputs
            if (liquid_capacitance is None or filler_capacitance is None or
                liquid_capacitance < 0 or filler_capacitance < 0):
                logger.info("Invalid capacitance values for force calculation")
                return None
                
            if not active_electrodes:
                logger.info("No active electrodes for force calculation")
                return None
                
            if liquid_capacitance <= filler_capacitance:
                logger.info("Liquid capacitance must be greater than filler capacitance")
                return None
            
            # calculate total area of active electrodes
            total_area = 0.0
            for electrode_id in active_electrodes:
                if electrode_id in electrode_areas:
                    total_area += electrode_areas[electrode_id]
                else:
                    logger.info(f"No area data for electrode {electrode_id}")
                    return None
            
            if total_area <= 0:
                logger.info("Total area of active electrodes is zero or negative")
                return None
            
            # capacitance_difference = liquid_capacitance - filler_capacitance 
            capacitance_per_unit_area =  (liquid_capacitance - filler_capacitance) / total_area
            logger.info(f"liquid capacitance: {liquid_capacitance}")
            logger.info(f"filler capacitance: {filler_capacitance}")
            logger.info(f"total area: {total_area}")
            logger.info(f"Calculated capacitance per unit area: {capacitance_per_unit_area}")
            return capacitance_per_unit_area
            
        except Exception as e:
            logger.info(f"Error calculating capacitance per unit area: {e}")
            return None
    
    @staticmethod
    def calculate_force_for_step(voltage: float, 
                            capacitance_per_unit_area: float,
                            step_activated_electrodes: Dict[str, bool],
                            calibration_active_electrodes: List[str],
                            electrode_areas: Dict[str, float]) -> Optional[float]:
        """
        Calculate force for a specific step.
        
        Args:
            voltage: Step voltage
            capacitance_per_unit_area: Capacitance per unit area from calibration
            step_activated_electrodes: Dictionary of electrode activation states for THIS step
            calibration_active_electrodes: List of electrodes that were active during calibration
            electrode_areas: Dictionary mapping electrode IDs to their areas
            
        Returns:
            Total force, or None if calculation not possible
        """
        try:
            if voltage <= 0 or capacitance_per_unit_area <= 0:
                logger.info(f"!!RETURNED!! voltage: {voltage}, capacitance/area: {capacitance_per_unit_area}")
                return None
            logger.info(f"voltage: {voltage}, capacitance/area: {capacitance_per_unit_area}")
            force = (capacitance_per_unit_area * voltage * voltage) / 2.0
            
            logger.info(f"returned force: {force}")
            return force if force > 0 else None
            
        except Exception as e:
            logger.info(f"Error calculating force for step: {e}")
            return None
    
    @staticmethod
    def update_step_force_in_model(step_item, protocol_state, voltage: float):
        """
        Update the force value for a single step in the model.
        
        Args:
            step_item: The QStandardItem representing the step
            protocol_state: The protocol state containing calibration data
            voltage: The voltage value for the step
        """
        try:
            if not protocol_state.has_complete_calibration_data():
                return
            
            calibration_data = protocol_state.get_calibration_data()
            active_electrodes_from_calibration = protocol_state.get_active_electrodes_from_calibration()
            
            # Calculate capacitance per unit area
            capacitance_per_unit_area = ForceCalculationService.calculate_capacitance_per_unit_area(
                calibration_data['liquid_capacitance'],
                calibration_data['filler_capacitance'],
                active_electrodes_from_calibration,
                calibration_data['electrode_areas']
            )
            
            if capacitance_per_unit_area is None:
                return
            
            # Get device state for this step
            device_state = step_item.data(Qt.UserRole + 100)
            if not device_state:
                return
            
            # Calculate force for this step
            force = ForceCalculationService.calculate_force_for_step(
                voltage,
                capacitance_per_unit_area,
                device_state.activated_electrodes,  # Step electrodes (not used in calculation)
                active_electrodes_from_calibration,  # Calibration electrodes (used for calculation)
                calibration_data['electrode_areas']
            )
            
            if force is not None:
                # Update Force column
                parent = step_item.parent() or step_item.model().invisibleRootItem()
                row = step_item.row()
                
                from protocol_grid.consts import protocol_grid_fields
                force_col = protocol_grid_fields.index("Force")
                force_item = parent.child(row, force_col)
                
                if force_item:
                    force_item.setText(f"{force:.2f}")
                    logger.info(f"Updated force for step to {force:.2f}")
            
        except Exception as e:
            logger.info(f"Error updating step force: {e}")
    
    @staticmethod
    def update_all_step_forces_in_model(model, protocol_state):
        """
        Update force values for all steps in the model.
        
        Args:
            model: The QStandardItemModel
            protocol_state: The protocol state containing calibration data
        """
        try:
            if not protocol_state.has_complete_calibration_data():
                logger.info("Incomplete calibration data, skipping force updates")
                return
            
            from protocol_grid.consts import protocol_grid_fields, STEP_TYPE, ROW_TYPE_ROLE
            voltage_col = protocol_grid_fields.index("Voltage")
            
            def update_recursive(parent_item):
                for row in range(parent_item.rowCount()):
                    desc_item = parent_item.child(row, 0)
                    if desc_item and desc_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                        # Get voltage value
                        voltage_item = parent_item.child(row, voltage_col)
                        if voltage_item:
                            try:
                                voltage = float(voltage_item.text() or "0")
                                ForceCalculationService.update_step_force_in_model(
                                    desc_item, protocol_state, voltage
                                )
                            except ValueError:
                                logger.info(f"Invalid voltage value: {voltage_item.text()}")
                    elif desc_item and desc_item.hasChildren():
                        update_recursive(desc_item)
            
            update_recursive(model.invisibleRootItem())
            logger.info("Updated forces for all steps")
            
        except Exception as e:
            logger.info(f"Error updating all step forces: {e}")

