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


def determine_run_schedule(sequence, prewarm_seconds=10.0, max_idle_seconds=10.0) -> list[tuple[int, int]]:
    """
    Calculates ON/OFF schedule.
    - Turns ON 'prewarm_seconds' before an event starts.
    - Bridges gaps if the OFF time between blocks is <= 'max_idle_seconds'.
    """
    # 1. Calculate raw required intervals [Start - Prewarm, End]
    required_intervals = []
    for event in sequence:
        if event.get('needs_state', False):
            # Clamp start at 0.0 so we don't get negative time
            start = max(0.0, event['start_time'] - prewarm_seconds)
            end = event['start_time'] + event['duration']
            required_intervals.append((start, end))

    if not required_intervals:
        return []

    # 2. Sort by start time
    required_intervals.sort(key=lambda x: x[0])

    # 3. Merge Logic
    merged = []
    if not required_intervals:
        return merged

    # Initialize with the first interval
    curr_start, curr_end = required_intervals[0]

    for next_start, next_end in required_intervals[1:]:
        # Calculate the actual idle gap between the end of the previous
        # block and the start of the NEXT pre-warm period.
        gap = next_start - curr_end

        # If gap is negative, they overlap.
        # If gap is positive but small (<= max_idle), we bridge it.
        if gap <= max_idle_seconds:
            # Merge: Extend current block to cover the next one
            # Note: We take max() because a short event might be fully contained
            # inside a previous long event's duration.
            curr_end = max(curr_end, next_end)
        else:
            # Gap is too big (saving energy is worth it). Close block.
            merged.append((curr_start, curr_end))
            curr_start, curr_end = next_start, next_end

    # Append the final block
    merged.append((curr_start, curr_end))

    return merged
