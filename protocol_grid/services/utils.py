import json

import dramatiq

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from protocol_grid.consts import DEVICE_VIEWER_CAMERA_ACTIVE, DEVICE_VIEWER_SCREEN_CAPTURE, \
    DEVICE_VIEWER_SCREEN_RECORDING

from logger.logger_service import get_logger
logger = get_logger(__name__)


@dramatiq.actor
def _publish_camera_video_control(active):
    """Publish camera video control message."""
    publish_message(topic=DEVICE_VIEWER_CAMERA_ACTIVE, message=active)
    logger.debug(f"Published camera video control message: {active}")

@dramatiq.actor
def _publish_camera_capture_control(step_id, step_description, experiment_dir):
    """Publish camera capture control message."""
    try:
        message_data = {
            "directory": experiment_dir,
            "step_description": step_description,
            "step_id": step_id,
            "show_dialog": False
        }
        publish_message(topic=DEVICE_VIEWER_SCREEN_CAPTURE, message=json.dumps(message_data))
        logger.info(f"Published camera capture control for step {step_id}")
    except Exception as e:
        logger.error(f"Error publishing camera capture control: {e}")

@dramatiq.actor
def _start_step_recording(step_id, step_description, experiment_dir):
    """Start step recording."""
    message_data = {
        "action": "start",
        "directory": experiment_dir,
        "step_description": step_description,
        "step_id": step_id,
        "show_dialog": False
    }
    publish_message(topic=DEVICE_VIEWER_SCREEN_RECORDING, message=json.dumps(message_data))
    logger.info(f"Started recording for step {step_id}")

@dramatiq.actor
def _stop_step_recording():
    """Stop step recording."""
    message_data = {"action": "stop"}
    publish_message(topic=DEVICE_VIEWER_SCREEN_RECORDING, message=json.dumps(message_data))
    logger.info("Stopped recording for step")