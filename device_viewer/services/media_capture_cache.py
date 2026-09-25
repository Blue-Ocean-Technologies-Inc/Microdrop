# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The media-capture cache: every saved capture is appended to the run's
app_globals bucket and announced live on DEVICE_VIEWER_MEDIA_CAPTURED."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import dramatiq

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Local imports.
from ..consts import MEDIA_CAPTURES_KEY, media_captured_publisher
from ..models.media import MediaCaptureMessageModel, MediaType

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()


@dramatiq.actor
def _cache_media_capture(name: MediaType, save_path: str, request_id: str = ""):
    media_capture_message = MediaCaptureMessageModel(
        path=Path(save_path), type=name.lower(), request_id=request_id
    )

    message = media_capture_message.model_dump_json()

    if not app_globals.get(MEDIA_CAPTURES_KEY):
        captures = [message]

    else:
        captures = app_globals[MEDIA_CAPTURES_KEY] + [message]

    app_globals[MEDIA_CAPTURES_KEY] = captures

    # Live notification for the run report and for whoever asked for this
    # frame (request_id); the bucket above stays for the flush-time drain.
    media_captured_publisher.publish(media_capture_message.model_dump(mode="json"))

    # Log only the new capture, not the whole accumulated bucket -- logging
    # the full list here grows the log quadratically over a long run.
    logger.info(
        f"Cached {name.lower()} capture {save_path} "
        f"(request_id={request_id!r}); {len(captures)} capture(s) this run."
    )
