from typing import List, Dict, Any, Optional, Callable
import copy
import json

from device_viewer.models.messages import DeviceViewerMessageModel


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
                            repeat_duration: float):
        if self.has_paths():
            calculated_time = self.longest_path_length() * step_duration * repetitions
        else:
            calculated_time = step_duration
        return max(calculated_time, repeat_duration)

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