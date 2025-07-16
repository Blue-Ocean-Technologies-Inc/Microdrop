from typing import List, Dict, Any, Optional, Callable
import copy
import json

from device_viewer.models.messages import DeviceViewerMessageModel
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


class DeviceState:
    def __init__(self, activated_electrodes: Optional[Dict[str, bool]] = None,
                 paths: Optional[List[List[str]]] = None,
                 id_to_channel: Optional[Dict[str, int]] = None,
                 route_colors: Optional[List[str]] = None):
        self.activated_electrodes = activated_electrodes or {}
        self.paths = paths or []
        self.id_to_channel = id_to_channel or {}
        self.route_colors = route_colors or []

    def longest_path_length(self):
        if not self.paths:
            return 0
        return max(len(path) for path in self.paths)#.values())

    def has_paths(self):
        return len(self.paths) > 0
    
    def has_individual_electrodes(self):
        return any(self.activated_electrodes.values())

    def calculated_duration(self, step_duration: float, repetitions: int, 
                            repeat_duration: float, trail_length: int = 1, trail_overlay: int = 0):
        if not self.has_paths():
            calculated_time = step_duration * repetitions
        else:
            has_loops = any(len(path) >= 2 and path[0] == path[-1] for path in self.paths)
            
            if not has_loops:
                effective_repetitions = 1
            else:
                effective_repetitions = repetitions
            
            logger.info(f"effective_repetitions={effective_repetitions}")
            
            max_open_path_length = 0
            max_loop_cycle_length = 0
            
            for i, path in enumerate(self.paths):
                is_loop = len(path) >= 2 and path[0] == path[-1]
                logger.info(f"Path {i}: {path}, is_loop={is_loop}")
                
                if is_loop:
                    effective_length = len(path) - 1
                    step_size = trail_length - trail_overlay
                    if step_size <= 0:
                        cycle_length = effective_length
                    else:
                        phases = 0
                        position = 0
                        while position < effective_length:
                            phases += 1
                            position += step_size
                            if position >= effective_length:
                                break
                        cycle_length = phases
                    max_loop_cycle_length = max(max_loop_cycle_length, cycle_length)
                    logger.info(f"Loop {i} cycle_length={cycle_length}")
                else:
                    path_length = len(path)
                    step_size = trail_length - trail_overlay
                    if step_size <= 0:
                        cycle_length = path_length
                    else:
                        phases = 0
                        position = 0
                        while position < path_length:
                            phases += 1
                            phase_end = position + trail_length - 1
                            if phase_end >= path_length - 1:
                                break
                            position += step_size
                        
                        if phases > 0:
                            last_phase_start = (phases - 1) * step_size
                            electrodes_in_last_phase = min(trail_length, path_length - last_phase_start)
                            
                            if electrodes_in_last_phase < trail_length and path_length >= trail_length:
                                if phases > 1:
                                    second_last_phase_start = (phases - 2) * step_size
                                    second_last_phase_electrodes = list(range(second_last_phase_start, 
                                                                            second_last_phase_start + trail_length))
                                    
                                    adjusted_last_start = path_length - trail_length
                                    adjusted_last_electrodes = list(range(adjusted_last_start, path_length))
                                    
                                    if second_last_phase_electrodes == adjusted_last_electrodes:
                                        phases -= 1
                            elif electrodes_in_last_phase < trail_length:
                                phases = max(1, phases - 1) if phases > 1 else 1
                        
                        cycle_length = phases
                    max_open_path_length = max(max_open_path_length, cycle_length)
                    logger.info(f"Open path {i} cycle_length={cycle_length}")
            
            # calculate total phases based on the longest duration needed
            loop_total_phases = 0
            if max_loop_cycle_length > 0:
                if effective_repetitions > 1:
                    loop_total_phases = (effective_repetitions - 1) * max_loop_cycle_length + max_loop_cycle_length + 1
                else:
                    loop_total_phases = max_loop_cycle_length + 1
            
            total_phases = max(loop_total_phases, max_open_path_length)
            calculated_time = total_phases * step_duration
        
        result = max(calculated_time, repeat_duration)
        logger.info(f"Final result: max({calculated_time}, {repeat_duration}) = {result}")
        return result

    def update_from_device_viewer(self, activated_electrodes_json: str,
                                  paths: List[List[str]]):
        try:
            self.activated_electrodes = json.loads(activated_electrodes_json)
        except (json.JSONDecodeError, TypeError):
            self.activated_electrodes = {}

        self.paths = paths or []

    def to_dict(self) -> Dict:
        return {
            'activated_electrodes': self.activated_electrodes,
            'paths': self.paths,
            'route_colors': self.route_colors,
            'id_to_channel': self.id_to_channel
        }
    
    def from_dict(self, data: Dict):
        self.activated_electrodes = data.get('activated_electrodes', {})
        self.paths = data.get('paths', [])
        self.route_colors = data.get('route_colors', [])
        self.id_to_channel = data.get('id_to_channel', {})

    def get_activated_electrode_ids(self):
        return [electrode_id for electrode_id, activated in 
                self.activated_electrodes.items() if activated]
    
    def get_all_path_electrodes(self):
        all_electrodes = []
        for path in self.paths:
            all_electrodes.extend(path)
        return all_electrodes
    
    def __str__(self):
        active_count = len(self.get_activated_electrode_ids())
        return (f"DeviceState(active_electrodes={active_count}, "
                f"paths={len(self.paths)}, longest_path={self.longest_path_length()})")
    
    def __repr__(self):
        return self.__str__()
    
def device_state_from_device_viewer_message(dv_msg):
    # convert channel numbers to electrode IDs
    activated_electrodes = {}
    
    # build reverse mapping from channel to electrode_id
    channel_to_electrode = {}
    for electrode_id, channel in dv_msg.id_to_channel.items():
        channel_to_electrode[channel] = electrode_id
    
    # channels_activated to electrode IDs
    for channel_str, activated in dv_msg.channels_activated.items():
        channel = int(channel_str)
        if channel in channel_to_electrode:
            electrode_id = channel_to_electrode[channel]
            activated_electrodes[electrode_id] = activated
        else:
            # use channel number directly, if no electrode ID found
            activated_electrodes[channel_str] = activated
    
    paths = [route[0] for route in dv_msg.routes]
    route_colors = [route[1] for route in dv_msg.routes]
    id_to_channel = dv_msg.id_to_channel
    return DeviceState(
        activated_electrodes=activated_electrodes,
        paths=paths,
        id_to_channel=id_to_channel,
        route_colors=route_colors
    )

def device_state_to_device_viewer_message(device_state: DeviceState, step_uid: str=None, 
                                          step_description: str=None, step_id: str=None, 
                                          editable: bool=True) -> DeviceViewerMessageModel:
    # electrode IDs to channels for activated electrodes
    channels_activated = {}
    for electrode_id, activated in device_state.activated_electrodes.items():
        if activated:
            if electrode_id in device_state.id_to_channel:
                channel = device_state.id_to_channel[electrode_id]
                channels_activated[str(channel)] = True
            else:
                # Try to use electrode_id directly if it's a channel number
                try:
                    channel = int(electrode_id)
                    channels_activated[str(channel)] = True
                except ValueError:
                    pass
    
    routes = []
    for i, path in enumerate(device_state.paths):
        color = device_state.route_colors[i] if i < len(device_state.route_colors) else "#000000"
        routes.append((path, color))
    id_to_channel = device_state.id_to_channel or {}
    
    if step_uid is None and step_description is None and step_id is None:
        step_info = {"step_id": None, "step_label": None}
    else:
        step_description = step_description or "Step"
        step_id = step_id or ""
        
        if step_description != "Step":
            step_label = f"Step: {step_description}, ID: {step_id}"
        else:
            step_label = f"Step, ID: {step_id}"
        
        step_info = {
            "step_id": step_uid or "",
            "step_label": step_label
        }
    
    return DeviceViewerMessageModel(
        channels_activated=channels_activated,
        routes=routes,
        id_to_channel=id_to_channel,
        step_info=step_info,
        editable=editable
    )