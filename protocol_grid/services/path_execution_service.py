import copy
import json
from typing import List, Dict, Any

from device_viewer.models.messages import DeviceViewerMessageModel
from protocol_grid.state.device_state import DeviceState
from protocol_grid.state.protocol_state import ProtocolStep
from protocol_grid.services.voltage_frequency_service import VoltageFrequencyService
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import ELECTRODES_STATE_CHANGE
from logger.logger_service import get_logger

logger = get_logger(__name__)

class PathExecutionService:

    @staticmethod
    def is_loop_path(path: List[str]) -> bool:
        return len(path) >= 2 and path[0] == path[-1] # (first == last electrode)

    @staticmethod
    def has_any_loops(device_state: DeviceState) -> bool:
        return any(PathExecutionService.is_loop_path(path) for path in device_state.paths)
    
    @staticmethod
    def calculate_effective_repetitions_for_path(path: List[str], original_repetitions: int, 
                                            duration: float, repeat_duration: float, 
                                            trail_length: int, trail_overlay: int) -> int:
        if not PathExecutionService.is_loop_path(path):
            return 1
        
        cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
        single_cycle_duration = len(cycle_phases) * duration
        
        if original_repetitions > 1:
            repetition_based_duration = (original_repetitions - 1) * single_cycle_duration + single_cycle_duration + duration  # +1 for return phase
        else:
            repetition_based_duration = single_cycle_duration + duration
                
        if repetition_based_duration >= repeat_duration:
            return original_repetitions
        
        min_repetitions = original_repetitions
        while True:
            if min_repetitions > 1:
                test_duration = (min_repetitions - 1) * single_cycle_duration + single_cycle_duration + duration
            else:
                test_duration = single_cycle_duration + duration
            
            if test_duration >= repeat_duration:
                break
            min_repetitions += 1
        
        return min_repetitions

    @staticmethod
    def calculate_trail_phases_for_path(path: List[str], trail_length: int, trail_overlay: int) -> List[List[int]]:
        """calculate phase electrode indices for a path."""
        path_length = len(path)
        if path_length == 0:
            return []
        
        step_size = trail_length - trail_overlay
        if step_size <= 0:
            # not possible, fallback to current behavior
            return [[i] for i in range(path_length)]
        
        phases = []
        position = 0
        
        # cover the entire path
        while position < path_length:
            phase_electrodes = []
            for i in range(trail_length):
                electrode_index = position + i
                if electrode_index < path_length:
                    phase_electrodes.append(electrode_index)
            
            phases.append(phase_electrodes)
            
            # check if this phase includes the last electrode
            if phase_electrodes and max(phase_electrodes) == path_length - 1:
                break
                
            position += step_size
        
        # adjust the last phase if needed and if possible
        if len(phases) > 0:
            last_phase = phases[-1]
            
            # if the last phase has fewer than "trail_length" no.of active electrodes
            if len(last_phase) < trail_length and path_length >= trail_length:
                end_position = path_length - 1
                start_position = end_position - trail_length + 1
                
                start_position = max(0, start_position)
                
                adjusted_last_phase = list(range(start_position, end_position + 1))
                
                # check if adjusted last phase is identical to second-last phase
                if len(phases) > 1 and phases[-2] == adjusted_last_phase:
                    phases.pop()
                else:
                    phases[-1] = adjusted_last_phase
            
            # if the last phase still has fewer electrodes than trail_length after adjustment,
            # it means the path is shorter than trail_length, so remove the incomplete phase
            # and merge it with the previous phase (if it exists)
            elif len(last_phase) < trail_length:
                if len(phases) > 1:
                    phases.pop()
                # if there is only one phase and it is incomplete, keep it as is
        
        return phases

    @staticmethod
    def calculate_loop_cycle_phases(path: List[str], trail_length: int, trail_overlay: int) -> List[List[int]]:        
        if not PathExecutionService.is_loop_path(path):
            result = PathExecutionService.calculate_trail_phases_for_path(path, trail_length, trail_overlay)
            logger.info(f"Open path phases: {result}")
            return result
        
        # for loops, make it a path without duplicating last electrode
        effective_path = path[:-1]
        effective_length = len(effective_path)
        
        step_size = trail_length - trail_overlay
        
        if step_size <= 0:
            # all positions, no smooth transition needed
            phases = [[i] for i in range(effective_length)]
            logger.info(f"Step size <= 0, generated phases: {phases}")
            return phases
        
        phases = []
        position = 0
        
        # generate phases for the loop
        while position < effective_length:
            phase_electrodes = []
            for i in range(trail_length):
                electrode_idx = (position + i) % effective_length  # wrap around
                phase_electrodes.append(electrode_idx)
            
            phases.append(phase_electrodes)
            position += step_size
            
            # check if the loop is completed
            if position >= effective_length:
                logger.info(f"Loop completed at position {position}")
                break
        
        logger.info(f"Final loop cycle phases: {phases}")
        return phases

    @staticmethod
    def calculate_step_execution_time(step: ProtocolStep, device_state: DeviceState) -> float:
        duration = float(step.parameters.get("Duration", "1.0"))
        repetitions = int(step.parameters.get("Repetitions", "1"))
        repeat_duration = float(step.parameters.get("Repeat Duration", "1.0"))
        trail_length = int(step.parameters.get("Trail Length", "1"))
        trail_overlay = int(step.parameters.get("Trail Overlay", "0"))
        
        if not device_state.has_paths():
            return duration
        
        has_loops = PathExecutionService.has_any_loops(device_state)
                
        max_open_path_length = 0
        max_loop_total_phases = 0
        
        for i, path in enumerate(device_state.paths):
            if PathExecutionService.is_loop_path(path):
                # calculate effective repetitions for this loop
                effective_repetitions = PathExecutionService.calculate_effective_repetitions_for_path(
                    path, repetitions, duration, repeat_duration, trail_length, trail_overlay
                )
                
                cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
                
                # calculate total phases for this specific loop
                if effective_repetitions > 1:
                    loop_total_phases = (effective_repetitions - 1) * cycle_length + cycle_length + 1
                else:
                    loop_total_phases = cycle_length + 1
                
                max_loop_total_phases = max(max_loop_total_phases, loop_total_phases)
            else:
                cycle_phases = PathExecutionService.calculate_trail_phases_for_path(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
                max_open_path_length = max(max_open_path_length, cycle_length)
        
        # calculate total phases based on the longest duration needed
        total_phases = max(max_loop_total_phases, max_open_path_length)
        total_time = duration * total_phases
                
        return total_time
    
    @staticmethod
    def calculate_step_repetition_info(step: ProtocolStep, device_state: DeviceState) -> Dict[str, int]:
        """calculate repetition information for status bar display."""
        duration = float(step.parameters.get("Duration", "1.0"))
        repetitions = int(step.parameters.get("Repetitions", "1"))
        repeat_duration = float(step.parameters.get("Repeat Duration", "1.0"))
        trail_length = int(step.parameters.get("Trail Length", "1"))
        trail_overlay = int(step.parameters.get("Trail Overlay", "0"))
        
        if not device_state.has_paths():
            return {"max_cycle_length": 1, "max_effective_repetitions": 1}
        
        has_loops = PathExecutionService.has_any_loops(device_state)
        
        if not has_loops:
            return {"max_cycle_length": 1, "max_effective_repetitions": 1}
        
        max_cycle_length = 0
        max_effective_repetitions = 1
        
        for i, path in enumerate(device_state.paths):
            if PathExecutionService.is_loop_path(path):
                effective_repetitions = PathExecutionService.calculate_effective_repetitions_for_path(
                    path, repetitions, duration, repeat_duration, trail_length, trail_overlay
                )
                
                cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
                
                # track largest loop
                if cycle_length > max_cycle_length or (cycle_length == max_cycle_length and effective_repetitions > max_effective_repetitions):
                    max_cycle_length = cycle_length
                    max_effective_repetitions = effective_repetitions
                                
        return {
            "max_cycle_length": max_cycle_length,
            "max_effective_repetitions": max_effective_repetitions
        }
    
    @staticmethod
    def calculate_step_execution_plan(step: ProtocolStep, device_state: DeviceState) -> List[Dict[str, Any]]:
        duration = float(step.parameters.get("Duration", "1.0"))
        repetitions = int(step.parameters.get("Repetitions", "1"))
        repeat_duration = float(step.parameters.get("Repeat Duration", "1.0"))
        trail_length = int(step.parameters.get("Trail Length", "1"))
        trail_overlay = int(step.parameters.get("Trail Overlay", "0"))
        
        step_uid = step.parameters.get("UID", "")
        step_id = step.parameters.get("ID", "")
        step_description = step.parameters.get("Description", "Step")
        
        execution_plan = []
        
        if not device_state.has_paths():
            execution_plan.append({
                "time": 0.0,
                "duration": duration,
                "activated_electrodes": copy.deepcopy(device_state.activated_electrodes),
                "step_uid": step_uid,
                "step_id": step_id,
                "step_description": step_description
            })
            return execution_plan
        
        has_loops = PathExecutionService.has_any_loops(device_state)
                
        # calculate effective repetitions for each path
        path_repetitions = {}
        path_info = []
        max_open_path_length = 0
        
        for i, path in enumerate(device_state.paths):
            is_loop = PathExecutionService.is_loop_path(path)
            
            if is_loop:
                effective_repetitions = PathExecutionService.calculate_effective_repetitions_for_path(
                    path, repetitions, duration, repeat_duration, trail_length, trail_overlay
                )
                path_repetitions[i] = effective_repetitions
                
                cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
                
                # calculate total phases for this specific loop
                if effective_repetitions > 1:
                    loop_total_phases = (effective_repetitions - 1) * cycle_length + cycle_length + 1
                else:
                    loop_total_phases = cycle_length + 1
            else: # open path
                path_repetitions[i] = 1
                cycle_phases = PathExecutionService.calculate_trail_phases_for_path(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
                max_open_path_length = max(max_open_path_length, cycle_length)
                loop_total_phases = cycle_length
            
            path_info.append({
                "path": path,
                "is_loop": is_loop,
                "cycle_length": cycle_length,
                "cycle_phases": cycle_phases,
                "loop_total_phases": loop_total_phases,
                "effective_repetitions": path_repetitions[i]
            })
        
        # calculate total phases based on the longest duration needed
        max_loop_total_phases = 0
        for path_data in path_info:
            if path_data["is_loop"]:
                max_loop_total_phases = max(max_loop_total_phases, path_data["loop_total_phases"])
        
        total_phases = max(max_loop_total_phases, max_open_path_length)
        
        for phase_idx in range(total_phases):
            # individually activated electrodes always active
            phase_electrodes = copy.deepcopy(device_state.activated_electrodes)
                        
            for path_idx, path_data in enumerate(path_info):
                path = path_data["path"]
                is_loop = path_data["is_loop"]
                cycle_length = path_data["cycle_length"]
                cycle_phases = path_data["cycle_phases"]
                path_total_phases = path_data["loop_total_phases"]
                effective_repetitions = path_data["effective_repetitions"]
                
                if is_loop:
                    # check if the loop has completed all its repetitions
                    if phase_idx >= path_total_phases:
                        continue
                    
                    if effective_repetitions > 1:
                        # Determine which repetition and phase within that repetition
                        if phase_idx < (effective_repetitions - 1) * cycle_length:
                            # Intermediate repetitions (no return phase)
                            current_repetition = phase_idx // cycle_length
                            phase_in_cycle = phase_idx % cycle_length
                            is_return_phase = False
                        else:
                            # Last repetition (with return phase)
                            current_repetition = effective_repetitions - 1
                            phase_in_last_rep = phase_idx - (effective_repetitions - 1) * cycle_length
                            if phase_in_last_rep < cycle_length:
                                phase_in_cycle = phase_in_last_rep
                                is_return_phase = False
                            else:
                                phase_in_cycle = 0
                                is_return_phase = True
                    else:
                        if phase_idx < cycle_length:
                            current_repetition = 0
                            phase_in_cycle = phase_idx
                            is_return_phase = False
                        else:
                            current_repetition = 0
                            phase_in_cycle = 0
                            is_return_phase = True
                    
                    if is_return_phase:
                        # Return phase - use first phase of the cycle
                        if 0 < len(cycle_phases):
                            electrode_indices = cycle_phases[0]
                            for electrode_idx in electrode_indices:
                                if electrode_idx < len(path) - 1: # exclude duplicate
                                    electrode_id = path[electrode_idx]
                                    phase_electrodes[electrode_id] = True
                    else:
                        # Regular phase
                        if phase_in_cycle < len(cycle_phases):
                            electrode_indices = cycle_phases[phase_in_cycle]
                            for electrode_idx in electrode_indices:
                                if electrode_idx < len(path) - 1: # exclude duplicate
                                    electrode_id = path[electrode_idx]
                                    phase_electrodes[electrode_id] = True
                else:
                    if phase_idx < cycle_length:
                        if phase_idx < len(cycle_phases):
                            electrode_indices = cycle_phases[phase_idx]
                            for electrode_idx in electrode_indices:
                                if electrode_idx < len(path):
                                    electrode_id = path[electrode_idx]
                                    phase_electrodes[electrode_id] = True            
            
            execution_plan.append({
                "time": phase_idx * duration,
                "duration": duration,
                "activated_electrodes": phase_electrodes,
                "step_uid": step_uid,
                "step_id": step_id,
                "step_description": step_description
            })
        
        return execution_plan
    
    @staticmethod
    def create_dynamic_device_state_message(original_device_state: DeviceState, 
                                          active_electrodes: Dict[str, bool], 
                                          step_uid: str,
                                          step_description: str = "Step",
                                          step_id: str = "") -> DeviceViewerMessageModel:
        """create a dynamic message combining individual + path electrodes."""        
        # electrode IDs to channels
        channels_activated = {}
        for electrode_id, activated in active_electrodes.items():
            if activated:
                #  try direct electrode_id lookup
                if electrode_id in original_device_state.id_to_channel:
                    channel = original_device_state.id_to_channel[electrode_id]
                    channels_activated[str(channel)] = True
                else:
                    # try finding electrode by channel number
                    # convert electrode_id to channel if it's a number
                    try:
                        channel_num = int(electrode_id)
                        # find electrode that maps to this channel
                        for elec_id, elec_channel in original_device_state.id_to_channel.items():
                            if elec_channel == channel_num:
                                channels_activated[str(channel_num)] = True
                                break
                    except ValueError:
                        logger.warning(f"Could not convert electrode_id {electrode_id} to channel")
            
        # keep original routes and colors
        routes = []
        for i, path in enumerate(original_device_state.paths):
            color = original_device_state.route_colors[i] if i < len(original_device_state.route_colors) else "#000000"
            routes.append((path, color))
        
        if step_description != "Step":
            step_label = f"Step: {step_description}, ID: {step_id}"
        else:
            step_label = f"Step, ID: {step_id}"
        
        step_info = {
            "step_id": step_uid,
            "step_label": step_label,
            "free_mode": False
        }
        
        return DeviceViewerMessageModel(
            channels_activated=channels_activated,
            routes=routes,
            id_to_channel=original_device_state.id_to_channel,
            step_info=step_info,
            editable=False 
        )
    
    @staticmethod
    def get_empty_device_state() -> DeviceState:
        return DeviceState()
    

    @staticmethod
    def create_hardware_electrode_message(device_state: DeviceState, active_electrodes: Dict[str, bool]) -> str:
        """Create a hardware electrode message for the ELECTRODES_STATE_CHANGE topic."""
        message_obj = {}
        
        # get all available channels from device state
        all_channels = set()
        for electrode_id, channel in device_state.id_to_channel.items():
            all_channels.add(channel)
        
        # collect channels that should be active
        active_channels = set()
        
        for electrode_id, activated in active_electrodes.items():
            if activated:
                # try direct electrode_id lookup first
                if electrode_id in device_state.id_to_channel:
                    channel = device_state.id_to_channel[electrode_id]
                    active_channels.add(channel)
                else:
                    # find electrode by channel number
                    try:
                        channel_num = int(electrode_id)
                        for elec_id, elec_channel in device_state.id_to_channel.items():
                            if elec_channel == channel_num:
                                active_channels.add(channel_num)
                                break
                    except ValueError:
                        logger.warning(f"Could not convert electrode_id {electrode_id} to channel for hardware message")
        
        # optimization: only include channels that are True, unless all are False
        if active_channels:
            for channel in active_channels:
                message_obj[str(channel)] = True
            logger.debug(f"Optimized electrode message: {len(message_obj)} active channels out of {len(all_channels)} total")
        else:
            for channel in all_channels:
                message_obj[str(channel)] = False
            logger.debug(f"All electrodes False: sending full dict with {len(message_obj)} channels")
        
        return json.dumps(message_obj)

    @staticmethod
    def create_deactivated_hardware_electrode_message(device_state: DeviceState) -> str:
        message_obj = {}
        
        # get all available channels from device state
        all_channels = set()
        for electrode_id, channel in device_state.id_to_channel.items():
            all_channels.add(channel)
        
        for channel in all_channels:
            message_obj[str(channel)] = False
        
        return json.dumps(message_obj)
    
    @staticmethod
    def publish_step_hardware_state(step, device_state, active_electrodes, preview_mode=False):
        """Publish both voltage/frequency and electrode state for a step."""
        VoltageFrequencyService.publish_step_voltage_frequency(step, preview_mode)
        
        if not preview_mode:
            hardware_message = PathExecutionService.create_hardware_electrode_message(
                device_state, active_electrodes
            )
            publish_message(topic=ELECTRODES_STATE_CHANGE, message=hardware_message)