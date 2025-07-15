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
    def calculate_step_execution_time(step: ProtocolStep, device_state: DeviceState) -> float:
        duration = float(step.parameters.get("Duration", "1.0"))
        
        if device_state.has_paths():
            return duration * device_state.longest_path_length()
        else:
            return duration
    
    @staticmethod
    def calculate_step_execution_plan(step: ProtocolStep, device_state: DeviceState) -> List[Dict[str, Any]]:
        duration = float(step.parameters.get("Duration", "1.0"))
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
        else:
            max_path_length = device_state.longest_path_length()
            
            for position in range(max_path_length):
                # individually activated electrodes always active
                position_electrodes = copy.deepcopy(device_state.activated_electrodes)
                
                # current position electrodes from (all) path(s)
                for path in device_state.paths:
                    if position < len(path):
                        electrode_id = path[position]
                        position_electrodes[electrode_id] = True
                
                execution_plan.append({
                    "time": position * duration,
                    "duration": duration,
                    "activated_electrodes": position_electrodes,
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