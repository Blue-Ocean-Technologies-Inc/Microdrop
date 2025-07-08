from typing import List, Dict, Any, Optional, Callable
import copy
import json

class DeviceState:
    def __init__(self, activated_electrodes: Optional[Dict[str, bool]] = None,
                 paths: Optional[List[List[str]]] = None):
        
        self.activated_electrodes = activated_electrodes or {}
        self.paths = paths or []

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
            'paths': self.paths
        }
    
    def from_dict(self, data: Dict):
        self.activated_electrodes = data.get('activated_electrodes', {})
        self.paths = data.get('paths', [])

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
    activated_electrodes = {str(k): bool(v) for k, v in dv_msg.channels_activated.items()}
    paths = [route[0] for route in dv_msg.routes]
    return DeviceState(activated_electrodes=activated_electrodes, paths=paths)
        