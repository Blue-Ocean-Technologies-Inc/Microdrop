import dramatiq
import time
from typing import Dict, List, Any

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from protocol_grid.consts import PROTOCOL_GRID_DISPLAY_STATE
from protocol_grid.services.path_execution_service import PathExecutionService
from protocol_grid.state.device_state import DeviceState
from protocol_grid.state.protocol_state import ProtocolStep
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

# these actors are not currently used

@dramatiq.actor(max_retries=0)
def execute_step_actor(step_dict: Dict, device_state_dict: Dict, controller_callback_queue: str):
    """Execute a single step with real-time electrode activation."""
    try:
        # reconstruct step object
        step = ProtocolStep(
            parameters=step_dict["parameters"],
            name=step_dict["name"]
        )
        
        device_state = DeviceState()
        if device_state_dict:
            device_state.from_dict(device_state_dict)
        
        logger.info(f"Executing step {step.parameters.get('ID', 'Unknown')} with device state: {device_state}")
        
        execution_plan = PathExecutionService.calculate_step_execution_plan(step, device_state)
        
        logger.info(f"Execution plan has {len(execution_plan)} phases")
        
        for i, plan_item in enumerate(execution_plan):
            logger.info(f"Executing phase {i+1}/{len(execution_plan)}: {plan_item['activated_electrodes']}")
            
            msg_model = PathExecutionService.create_dynamic_device_state_message(
                device_state, 
                plan_item["activated_electrodes"], 
                plan_item["step_uid"],
                plan_item["step_description"],
                plan_item["step_id"]
            )
            
            publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
            
            logger.info(f"Published electrode state: {msg_model.serialize()}")
            
            # wait for the duration (except for last phase)
            if i < len(execution_plan) - 1:
                logger.info(f"Waiting {plan_item['duration']} seconds")
                time.sleep(plan_item["duration"])
            else:
                # last phase: wait for full duration
                logger.info(f"Final phase - waiting {plan_item['duration']} seconds")
                time.sleep(plan_item["duration"])
        
        logger.info(f"Step {step.parameters.get('UID', 'Unknown')} completed")
        
    except Exception as e:
        logger.error(f"Error in execute_step_actor: {e}")