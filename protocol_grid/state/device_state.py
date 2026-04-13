from typing import List, Dict, Optional

from device_viewer.models.messages import DeviceViewerMessageModel
from logger.logger_service import get_logger

logger = get_logger(__name__)

#TODO: Convert to pydantic
class DeviceState:
    def __init__(self, activated_electrodes: list[int] = None,
                 paths: Optional[List[List[str]]] = None,
                 id_to_channel: Optional[Dict[str, int]] = None,
                 route_colors: Optional[List[str]] = None,
                 activated_electrodes_area_mm2: Optional[float] = 0):
        self.activated_electrodes = activated_electrodes or []
        self.paths = paths or []
        self.id_to_channel = id_to_channel or {}
        self.route_colors = route_colors or []
        self.activated_electrodes_area_mm2 = activated_electrodes_area_mm2

    def longest_path_length(self):
        if not self.paths:
            return 0
        return max(len(path) for path in self.paths)#.values())

    def has_paths(self):
        return len(self.paths) > 0

    def calculated_duration(self, step_duration: float, repetitions: int,
                            repeat_duration: float = 1.0, trail_length: int = 1, trail_overlay: int = 0,
                            soft_start: bool = False, soft_end: bool = False):
        """Calculate the total duration for this step including idle/balance phases.

        When repeat_duration > 0 and the step has loops, each loop independently
        calculates how many full cycles fit within repeat_duration. Idle phases
        pad the remaining balance time.  Soft start/end add ramp phases on top.
        The total step duration is driven by the longest loop.
        """
        from protocol_grid.services.path_execution_service import PathExecutionService

        if not self.has_paths():
            calculated_time = step_duration * repetitions
        else:
            max_open_path_length = 0
            max_loop_total_phases = 0

            for i, path in enumerate(self.paths):
                is_loop = len(path) >= 2 and path[0] == path[-1]

                if is_loop:
                    effective_repetitions = PathExecutionService.calculate_effective_repetitions_for_path(
                        path, repetitions, step_duration, repeat_duration, trail_length, trail_overlay
                    )

                    cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
                    cycle_length = len(cycle_phases)

                    if effective_repetitions > 1:
                        active_phases = (effective_repetitions - 1) * cycle_length + cycle_length + 1
                    else:
                        active_phases = cycle_length + 1

                    idle_phases = PathExecutionService.calculate_loop_balance_idle_phases(
                        path, effective_repetitions, step_duration, repeat_duration, trail_length, trail_overlay
                    )
                    loop_total_phases = active_phases + idle_phases

                    if soft_start and cycle_phases:
                        loop_total_phases += len(
                            PathExecutionService.calculate_soft_start_phases(cycle_phases[0])
                        )
                    if soft_end and cycle_phases:
                        loop_total_phases += len(
                            PathExecutionService.calculate_soft_terminate_phases(cycle_phases[-1])
                        )

                    max_loop_total_phases = max(max_loop_total_phases, loop_total_phases)
                else:
                    cycle_phases = PathExecutionService.calculate_trail_phases_for_path(
                        path, trail_length, trail_overlay,
                        soft_start=soft_start, soft_terminate=soft_end,
                    )
                    cycle_length = len(cycle_phases)
                    max_open_path_length = max(max_open_path_length, cycle_length)

            # calculate total phases based on the longest duration needed
            total_phases = max(max_loop_total_phases, max_open_path_length)
            calculated_time = total_phases * step_duration

        result = max(calculated_time, repeat_duration)
        return result

    def to_dict(self) -> Dict:
        return {
            'activated_electrodes': self.activated_electrodes,
            'activated_electrodes_area_mm2': self.activated_electrodes_area_mm2,
            'paths': self.paths,
            'route_colors': self.route_colors,
            'id_to_channel': self.id_to_channel,
        }
    
    def from_dict(self, data: Dict):
        self.activated_electrodes = data.get('activated_electrodes', [])
        self.activated_electrodes_area_mm2 = data.get('activated_electrodes_area_mm2', 0)
        self.paths = data.get('paths', [])
        self.route_colors = data.get('route_colors', [])
        self.id_to_channel = data.get('id_to_channel', {})
    
    def update_id_to_channel_mapping(self, new_id_to_channel, new_route_colors=None):        
        old_mapping = self.id_to_channel.copy()
        
        self.id_to_channel = new_id_to_channel.copy()
        
        # Update route colors if provided
        if new_route_colors is not None:
            self.route_colors = new_route_colors.copy()
        
        # update activated_electrodes to use new mapping
        updated_activated_electrodes = set()
        for electrode_id in self.activated_electrodes:
            if electrode_id in new_id_to_channel:
                updated_activated_electrodes.add(electrode_id)
            else:
                # find the electrode in the old mapping and map it according to new mapping
                if electrode_id in old_mapping:
                    old_channel = old_mapping[electrode_id]
                    for new_electrode_id, new_channel in new_id_to_channel.items():
                        if new_channel == old_channel:
                            updated_activated_electrodes.add(new_electrode_id)
                            break
        
        self.activated_electrodes = list(updated_activated_electrodes)
        
        # update paths to use new electrode IDs
        updated_paths = []
        for path in self.paths:
            updated_path = []
            for electrode_id in path:
                if electrode_id in new_id_to_channel:
                    updated_path.append(electrode_id)
                else:
                    if electrode_id in old_mapping:
                        old_channel = old_mapping[electrode_id]
                        for new_electrode_id, new_channel in new_id_to_channel.items():
                            if new_channel == old_channel:
                                updated_path.append(new_electrode_id)
                                break
                        else:
                            updated_path.append(electrode_id)
                    else:
                        updated_path.append(electrode_id)
            updated_paths.append(updated_path)
        
        self.paths = updated_paths
            
    def __str__(self):
        active_count = len(self.activated_electrodes)
        return (f"DeviceState(active_electrodes={active_count}, activated_area_mm2={self.activated_electrodes_area_mm2}"
                f"paths={len(self.paths)}, longest_path={self.longest_path_length()})")
    
    def __repr__(self):
        return self.__str__()
    
def device_state_from_device_viewer_message(dv_msg):
    # convert channel numbers to electrode IDs
    activated_electrodes = set()
    
    # build reverse mapping from channel to electrode_id
    channel_to_electrode = {}
    for electrode_id, channel in dv_msg.id_to_channel.items():
        channel_to_electrode[channel] = electrode_id
    
    # channels_activated to electrode IDs
    for channel_str in dv_msg.channels_activated:
        channel = int(channel_str)
        if channel in channel_to_electrode:
            electrode_id = channel_to_electrode[channel]
            activated_electrodes.add(electrode_id)
        else:
            # use channel number directly, if no electrode ID found
            activated_electrodes.add(channel_str)
    
    paths = [route[0] for route in dv_msg.routes]
    route_colors = [route[1] for route in dv_msg.routes]
    id_to_channel = dv_msg.id_to_channel
    return DeviceState(
        activated_electrodes=list(activated_electrodes),
        paths=paths,
        id_to_channel=id_to_channel,
        route_colors=route_colors,
        activated_electrodes_area_mm2=dv_msg.activated_electrodes_area_mm2
    )

def device_state_to_device_viewer_message(device_state: DeviceState, step_uid: str=None, 
                                          step_description: str=None, step_id: str=None, 
                                          editable: bool=True) -> DeviceViewerMessageModel:
    # electrode IDs to channels for activated electrodes
    channels_activated = set()
    for electrode_id in device_state.activated_electrodes:
            if electrode_id in device_state.id_to_channel:
                channel = device_state.id_to_channel[electrode_id]
                channels_activated.add(channel)

    routes = []
    for i, path in enumerate(device_state.paths):
        color = device_state.route_colors[i] if i < len(device_state.route_colors) else "#000000"
        routes.append((path, color))
    id_to_channel = device_state.id_to_channel or {}
    
    if step_uid is None and step_description is None and step_id is None:
        step_info = {"step_id": None, "step_label": None, "free_mode": True}
    else:
        step_description = step_description or "Step"
        step_id = step_id or ""
        
        if step_description != "Step":
            step_label = f"Step: {step_description}, ID: {step_id}"
        else:
            step_label = f"Step, ID: {step_id}"
        
        step_info = {
            "step_id": step_uid or "",
            "step_label": step_label,
            "free_mode": False
        }
    
    return DeviceViewerMessageModel(
        channels_activated=channels_activated,
        routes=routes,
        id_to_channel=id_to_channel,
        step_info=step_info,
        editable=editable
    )