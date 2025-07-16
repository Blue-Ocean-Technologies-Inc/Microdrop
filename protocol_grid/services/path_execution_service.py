import time
import copy
import json
from typing import List, Dict, Any

from device_viewer.models.messages import DeviceViewerMessageModel
from protocol_grid.state.device_state import DeviceState
from protocol_grid.state.protocol_state import ProtocolStep
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

class PathExecutionService:

    @staticmethod
    def is_loop_path(path: List[str]) -> bool:
        return len(path) >= 2 and path[0] == path[-1] # (first == last electrode)

    @staticmethod
    def has_any_loops(device_state: DeviceState) -> bool:
        return any(PathExecutionService.is_loop_path(path) for path in device_state.paths)

    @staticmethod
    def calculate_effective_repetitions(step: ProtocolStep, device_state: DeviceState) -> int:
        # always return 1 - repetitions are handled by extending the cycle phases
        return 1
    
    @staticmethod
    def calculate_num_phases_for_path(path_length: int, trail_length: int, trail_overlay: int) -> int:
        if path_length == 0:
            return 0
        
        step_size = trail_length - trail_overlay
        if step_size <= 0:
            # not possible, fallback to current behavior
            return path_length
        
        phases = 0
        position = 0
        
        # cover the entire path
        while position < path_length:
            phases += 1
            
            # check if this phase includes the last electrode
            phase_end = position + trail_length - 1
            if phase_end >= path_length - 1:
                # this phase includes the last electrode, so it should be the final phase
                break
                
            position += step_size
        
        # check the last phase adjustment logic
        if phases > 0:
            last_phase_start = (phases - 1) * step_size
            electrodes_in_last_phase = min(trail_length, path_length - last_phase_start)
            
            # if the last phase has fewer than "trail_length" no.of active electrodes, 
            # needs to be adjusted
            if electrodes_in_last_phase < trail_length and path_length >= trail_length:
                # check if adjusted last phase would be identical to second-last phase
                if phases > 1:
                    second_last_phase_start = (phases - 2) * step_size
                    second_last_phase_electrodes = list(range(second_last_phase_start, 
                                                            second_last_phase_start + trail_length))
                    
                    adjusted_last_start = path_length - trail_length
                    adjusted_last_electrodes = list(range(adjusted_last_start, path_length))
                    
                    # if adjusted last phase is identical to second-last phase, remove the last phase
                    if second_last_phase_electrodes == adjusted_last_electrodes:
                        phases -= 1
                        
            elif electrodes_in_last_phase < trail_length:
                phases = max(1, phases - 1) if phases > 1 else 1
        
        return phases

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
        logger.info(f"calculate_loop_cycle_phases called with path={path}, trail_length={trail_length}, trail_overlay={trail_overlay}")
        
        if not PathExecutionService.is_loop_path(path):
            logger.info(f"Path {path} is not a loop, using regular trail calculation")
            result = PathExecutionService.calculate_trail_phases_for_path(path, trail_length, trail_overlay)
            logger.info(f"Open path phases: {result}")
            return result
        
        # for loops, make it a path without duplicating last electrode
        effective_path = path[:-1]
        effective_length = len(effective_path)
        logger.info(f"Loop detected, effective_path={effective_path}, effective_length={effective_length}")
        
        step_size = trail_length - trail_overlay
        logger.info(f"Step size calculated: {step_size}")
        
        if step_size <= 0:
            # all positions, no smooth transition needed
            phases = [[i] for i in range(effective_length)]
            logger.info(f"Step size <= 0, generated phases: {phases}")
            return phases
        
        phases = []
        position = 0
        
        # generate phases for the loop
        logger.info(f"Starting phase generation for loop")
        while position < effective_length:
            phase_electrodes = []
            for i in range(trail_length):
                electrode_idx = (position + i) % effective_length  # wrap around
                phase_electrodes.append(electrode_idx)
            
            phases.append(phase_electrodes)
            logger.info(f"Generated phase at position {position}: {phase_electrodes}")
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
        trail_length = int(step.parameters.get("Trail Length", "1"))
        trail_overlay = int(step.parameters.get("Trail Overlay", "0"))
        
        # additional safety check: clamp trail overlay (remove if not needed)
        # trail_overlay = min(trail_overlay, max(0, trail_length - 1))
        
        if not device_state.has_paths():
            return duration
        
        has_loops = PathExecutionService.has_any_loops(device_state)
        effective_repetitions = repetitions if has_loops else 1
        
        logger.info(f"has_loops={has_loops}, effective_repetitions={effective_repetitions}")
        
        # calculate maximum phases across all paths
        max_cycle_length = 0
        for i, path in enumerate(device_state.paths):
            if PathExecutionService.is_loop_path(path):
                cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
                logger.info(f"Loop path {i} cycle_length={cycle_length}")
            else:
                cycle_phases = PathExecutionService.calculate_trail_phases_for_path(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
                logger.info(f"Open path {i} cycle_length={cycle_length}")
            
            max_cycle_length = max(max_cycle_length, cycle_length)
        
        if effective_repetitions > 1:
            total_phases = (effective_repetitions - 1) * max_cycle_length + max_cycle_length + 1
        else:
            total_phases = max_cycle_length + 1
        
        total_time = duration * total_phases
        logger.info(f"max_cycle_length={max_cycle_length}, total_phases={total_phases}, total_time={total_time}")
        
        return total_time
    
    @staticmethod
    def calculate_step_execution_plan(step: ProtocolStep, device_state: DeviceState) -> List[Dict[str, Any]]:
        duration = float(step.parameters.get("Duration", "1.0"))
        repetitions = int(step.parameters.get("Repetitions", "1"))
        trail_length = int(step.parameters.get("Trail Length", "1"))
        trail_overlay = int(step.parameters.get("Trail Overlay", "0"))
        
        # additional safety check: clamp trail overlay (remove if not needed)
        # trail_overlay = min(trail_overlay, max(0, trail_length - 1))
        
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
        effective_repetitions = repetitions if has_loops else 1
        
        logger.info(f"has_loops={has_loops}, effective_repetitions={effective_repetitions}")
        
        # calculate phases for each path
        path_info = []
        max_cycle_length = 0
        
        for i, path in enumerate(device_state.paths):
            is_loop = PathExecutionService.is_loop_path(path)
            logger.info(f"Processing path {i}: {path}, is_loop={is_loop}")
            
            if is_loop:
                cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
            else:
                cycle_phases = PathExecutionService.calculate_trail_phases_for_path(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
            
            logger.info(f"Path {i} cycle_length={cycle_length}, cycle_phases={cycle_phases}")
            
            path_info.append({
                "path": path,
                "is_loop": is_loop,
                "cycle_length": cycle_length,
                "cycle_phases": cycle_phases
            })
            
            max_cycle_length = max(max_cycle_length, cycle_length)
        
        logger.info(f"max_cycle_length={max_cycle_length}")
        
        # return phase only for the last repetition
        total_phases = 0
        if effective_repetitions > 1:
            total_phases = (effective_repetitions - 1) * max_cycle_length + max_cycle_length + 1
        else:
            total_phases = max_cycle_length + 1
        
        logger.info(f"total_phases={total_phases}")
        
        for phase_idx in range(total_phases):
            # individually activated electrodes always active
            phase_electrodes = copy.deepcopy(device_state.activated_electrodes)
            
            # Determine current repetition and phase
            if phase_idx < (effective_repetitions - 1) * max_cycle_length:
                current_repetition = phase_idx // max_cycle_length
                phase_in_cycle = phase_idx % max_cycle_length
                is_return_phase = False
            else:
                # last repetition (return phase)
                current_repetition = effective_repetitions - 1
                phase_in_last_rep = phase_idx - (effective_repetitions - 1) * max_cycle_length
                if phase_in_last_rep < max_cycle_length:
                    phase_in_cycle = phase_in_last_rep
                    is_return_phase = False
                else:
                    phase_in_cycle = 0
                    is_return_phase = True
            
            logger.info(f"Phase {phase_idx}: repetition={current_repetition}, phase_in_cycle={phase_in_cycle}, is_return_phase={is_return_phase}")
            
            for path_idx, path_data in enumerate(path_info):
                path = path_data["path"]
                is_loop = path_data["is_loop"]
                cycle_length = path_data["cycle_length"]
                cycle_phases = path_data["cycle_phases"]
                
                if is_loop:
                    # loop path - continues for all repetitions with seamless transitions
                    if current_repetition < effective_repetitions:
                        if is_return_phase:
                            # return phase = first phase
                            if 0 < len(cycle_phases):
                                electrode_indices = cycle_phases[0]
                                logger.info(f"Loop path {path_idx} return phase: electrodes {electrode_indices}")
                                for electrode_idx in electrode_indices:
                                    if electrode_idx < len(path) - 1: # exclude duplicate
                                        electrode_id = path[electrode_idx]
                                        phase_electrodes[electrode_id] = True
                                        logger.info(f"  Activated electrode {electrode_id}")
                            else:
                                logger.info(f"Loop path {path_idx} return phase but no phases available")
                        else:
                            phase_in_path_cycle = phase_in_cycle % cycle_length
                            if phase_in_path_cycle < len(cycle_phases):
                                electrode_indices = cycle_phases[phase_in_path_cycle]
                                logger.info(f"Loop path {path_idx} at phase {phase_in_path_cycle}: electrodes {electrode_indices}")
                                for electrode_idx in electrode_indices:
                                    if electrode_idx < len(path) - 1: # exclude duplicate
                                        electrode_id = path[electrode_idx]
                                        phase_electrodes[electrode_id] = True
                                        logger.info(f"  Activated electrode {electrode_id}")
                            else:
                                logger.info(f"Loop path {path_idx} waiting (phase {phase_in_path_cycle} >= {len(cycle_phases)})")
                    else:
                        logger.info(f"Loop path {path_idx} finished (repetition {current_repetition} >= {effective_repetitions})")
                else:
                    if current_repetition == 0 and not is_return_phase and phase_in_cycle < cycle_length:
                        if phase_in_cycle < len(cycle_phases):
                            electrode_indices = cycle_phases[phase_in_cycle]
                            logger.info(f"Open path {path_idx} at phase {phase_in_cycle}: electrodes {electrode_indices}")
                            for electrode_idx in electrode_indices:
                                if electrode_idx < len(path):
                                    electrode_id = path[electrode_idx]
                                    phase_electrodes[electrode_id] = True
                                    logger.info(f"  Activated electrode {electrode_id}")
                        else:
                            logger.info(f"Open path {path_idx} waiting")
                    else:
                        logger.info(f"Open path {path_idx} deactivated (repetition {current_repetition} > 0 or return phase or phase {phase_in_cycle} >= {cycle_length})")
            
            logger.info(f"Final phase_electrodes for phase {phase_idx}: {phase_electrodes}")
            
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
        logger.info(f"Creating dynamic message with active_electrodes: {active_electrodes}")
        logger.info(f"Original device state id_to_channel: {original_device_state.id_to_channel}")
        
        # electrode IDs to channels
        channels_activated = {}
        for electrode_id, activated in active_electrodes.items():
            if activated:
                #  try direct electrode_id lookup
                if electrode_id in original_device_state.id_to_channel:
                    channel = original_device_state.id_to_channel[electrode_id]
                    channels_activated[str(channel)] = True
                    logger.info(f"Found direct mapping: {electrode_id} -> channel {channel}")
                else:
                    # try finding electrode by channel number
                    # convert electrode_id to channel if it's a number
                    try:
                        channel_num = int(electrode_id)
                        # find electrode that maps to this channel
                        for elec_id, elec_channel in original_device_state.id_to_channel.items():
                            if elec_channel == channel_num:
                                channels_activated[str(channel_num)] = True
                                logger.info(f"Found channel mapping: electrode {electrode_id} -> channel {channel_num}")
                                break
                    except ValueError:
                        logger.warning(f"Could not convert electrode_id {electrode_id} to channel")
        
        logger.info(f"Final channels_activated: {channels_activated}")
        
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
            "step_label": step_label
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
        
        # initialize all channels to False
        for channel in all_channels:
            message_obj[str(channel)] = False
        
        for electrode_id, activated in active_electrodes.items():
            if activated:
                # try direct electrode_id lookup first
                if electrode_id in device_state.id_to_channel:
                    channel = device_state.id_to_channel[electrode_id]
                    message_obj[str(channel)] = True
                else:
                    # find electrode by channel number
                    try:
                        channel_num = int(electrode_id)
                        for elec_id, elec_channel in device_state.id_to_channel.items():
                            if elec_channel == channel_num:
                                message_obj[str(channel_num)] = True
                                break
                    except ValueError:
                        logger.warning(f"Could not convert electrode_id {electrode_id} to channel for hardware message")
        
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