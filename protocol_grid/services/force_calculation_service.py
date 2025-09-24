from pint import UnitRegistry
from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import Qt

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

ureg = UnitRegistry()

class ForceCalculationService:
    """Service for calculating forces based on calibration data and voltages."""
    
    @staticmethod
    def calculate_capacitance_per_unit_area(liquid_capacitance_over_area: float, 
                                          filler_capacitance_over_area: float):
        """
        Calculate capacitance per unit area from calibration data.
        
        Args:
            liquid_capacitance_over_area: Total liquid capacitance (in pF/mm^2)
            filler_capacitance_over_area: Total filler capacitance (in pF/mm^2)

        Returns:
            Capacitance per unit area (in pF/mm^2), or None if calculation not possible
        """
        try:
            # validate inputs
            if (liquid_capacitance_over_area is None or filler_capacitance_over_area is None or
                liquid_capacitance_over_area < 0 or filler_capacitance_over_area < 0):
                logger.info("Invalid capacitance values for force calculation")
                return None
                
            if liquid_capacitance_over_area <= filler_capacitance_over_area:
                logger.info("Liquid capacitance must be greater than filler capacitance")
                return None
            
            # capacitance_difference = liquid_capacitance - filler_capacitance 
            capacitance_per_unit_area =  liquid_capacitance_over_area - filler_capacitance_over_area
            logger.info(f"liquid capacitance over area: {liquid_capacitance_over_area}")
            logger.info(f"filler capacitance over area: {filler_capacitance_over_area}")
            logger.info(f"Calculated capacitance per unit area: {capacitance_per_unit_area}")
            return capacitance_per_unit_area
            
        except Exception as e:
            logger.info(f"Error calculating capacitance per unit area: {e}")
            return None
    
    @staticmethod
    def calculate_force_for_step(voltage: float, 
                            capacitance_per_unit_area: float):
        """
        Calculate force for a specific step.
        
        Args:
            voltage: Step voltage (V)
            capacitance_per_unit_area: Capacitance per unit area from calibration (in pF/mm^2)

        Returns:
            Total force (in mN/m), or None if calculation not possible
        """
        try:
            if voltage <= 0 or capacitance_per_unit_area <= 0:
                logger.info(f"!!RETURNED!! voltage: {voltage}, capacitance/area: {capacitance_per_unit_area}")
                return None
            logger.info(f"voltage: {voltage}, capacitance/area: {capacitance_per_unit_area}")
            
            # create pint quantities with proper units
            cap_quantity = ureg.Quantity(capacitance_per_unit_area, 'pF/mm**2')
            voltage_quantity = ureg.Quantity(voltage, 'V')
            
            # calculate force: F = (C/A × V²) / 2
            force_quantity = cap_quantity * (voltage_quantity ** 2) / 2
            
            # convert to desired unit (mN/m)
            force_in_target_units = force_quantity.to('mN/m')
            
            logger.info(f"calculated force with units: {force_in_target_units}")
            
            # return magnitude (numerical value) in mN/m
            force_magnitude = force_in_target_units.magnitude
            
            logger.info(f"returned force magnitude: {force_magnitude} mN/m")
            return force_magnitude if force_magnitude > 0 else None
            
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
            
            # Calculate capacitance per unit area
            capacitance_per_unit_area = ForceCalculationService.calculate_capacitance_per_unit_area(
                calibration_data['liquid_capacitance_over_area'],
                calibration_data['filler_capacitance_over_area']
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
                capacitance_per_unit_area
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

