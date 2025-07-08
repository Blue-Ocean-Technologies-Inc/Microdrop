import random
from protocol_grid.state.device_state import DeviceState


class DeviceStateManager:
    """
    Manages device state creation and validation.
    """
    
    @staticmethod
    def create_random_device_state(total_electrodes=120):
        active = random.sample([str(i) for i in range(total_electrodes)], random.randint(0, 10))
        paths = []
        for _ in range(random.randint(0, 3)):
            path_len = random.randint(2, 8)
            paths.append(random.sample([str(i) for i in range(total_electrodes)], path_len))
        
        activated_electrodes = {str(i): (str(i) in active) for i in range(total_electrodes)}
        return DeviceState(activated_electrodes, paths)
    
    @staticmethod
    def create_default_device_state(total_electrodes=120):
        activated_electrodes = {str(i): False for i in range(total_electrodes)}
        return DeviceState(activated_electrodes, [])