from pathlib import Path

import dramatiq
from PySide6.QtCore import QUrl

from ...models.media import MediaType, MediaCaptureMessageModel
from ...consts import MEDIA_CAPTURES_KEY

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()

from logger.logger_service import get_logger
logger = get_logger(__name__)



@dramatiq.actor
def _cache_media_capture(name: MediaType, save_path: str):
    media_capture_message = MediaCaptureMessageModel(
        path=Path(save_path), type=name.lower()
    )

    message=media_capture_message.model_dump_json()

    if not app_globals.get(MEDIA_CAPTURES_KEY):
        app_globals[MEDIA_CAPTURES_KEY] = [message]

    else:
        app_globals[MEDIA_CAPTURES_KEY] += [message]

    logger.info(app_globals[MEDIA_CAPTURES_KEY])

def _show_media_capture_dialog(
    name: MediaType, save_path: str, status_bar_manager=None
):

    if name.lower() not in MediaType.get_media_types():
        raise ValueError(f"Invalid media type: {name}")

    file_url = QUrl.fromLocalFile(save_path).toString()
    formatted_message = (
        f"{name.name.title()} Captured: "
        f"<a href='{file_url}' style='color: #0078d7;'>{save_path}</a>"
    )

    if status_bar_manager is not None:
        status_bar_manager.show_center_message(formatted_message, timeout=5000)

    logger.info(f"Saved {name} media to {save_path}.")
    return True
