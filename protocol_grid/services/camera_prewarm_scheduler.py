"""
Camera Pre-warm Scheduler
=========================

logic for pre-warming the camera video feed before steps
that require video, image capture, or recording.
"""

import numpy as np
from numpy import ndarray

from logger.logger_service import get_logger
from protocol_grid.logic.prewarm_mask import get_prewarm_step_mask

logger = get_logger(__name__)

def compile_camera_schedule(run_order: list, prewarm_seconds: float) -> tuple | None:
    """
    Scan *run_order*, build a camera on/off timeline, and start the
    background scheduler.

    Parameters
    ----------
    run_order : list[dict]
        The flattened protocol run order as produced by
        ``flatten_protocol_for_run``.  Each entry has a ``"step"`` key
        whose value is a protocol step with ``.parameters`` and
        ``.device_state``.

    prewarm_seconds : float
        Prewarm seconds lead time for camera step
    """

    try:
        user_set_video_mask, video_needed_mask = _get_video_on_array(run_order)
        prewarm_step_mask, offset_seconds = get_prewarm_step_mask(video_needed_mask, prewarm_seconds)

        # camera is on if user requests or if its needed for recording or capture (with prewarm).
        video_flip_needed_mask = user_set_video_mask  | prewarm_step_mask

        # Non-Zero offsets only needed when its not a step where user already requested video and a prewarm is needed.
        # Except the first step since a prewarm would be negative
        offset_seconds[1:] = ~user_set_video_mask[1:] * offset_seconds[1:]

        return video_flip_needed_mask, offset_seconds

    except Exception as e:
        logger.error(e, exc_info=True)
        raise Exception(e)

def _get_video_on_array(sequence: list) -> tuple[ndarray, ndarray] | None:

    video_needed_arr = []
    user_set_video_arr = []
    for entry in sequence:

        try:
            parameters = entry.get("step").parameters
        except Exception as e:
            logger.error(e, exc_info=True)
            return None

        video_required = (int(parameters.get("Capture", 0)) or
                       int(parameters.get("Record", 0)))

        user_set_video_on = int(parameters.get("Video", 0))

        run_time = float(parameters.get("Run Time", 0))
        video_needed_arr.append([video_required, run_time])
        user_set_video_arr.append(user_set_video_on)

    return np.array(user_set_video_arr, dtype=bool), np.array(video_needed_arr)
