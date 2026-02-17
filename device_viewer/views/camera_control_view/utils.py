from pathlib import Path
from PySide6.QtCore import QUrl

from device_viewer.models.media_capture_model import MediaType, MediaCaptureMessageModel
from microdrop_application.dialogs.pyface_wrapper import success
from microdrop_application.helpers import get_microdrop_redis_globals_manager

app_globals = get_microdrop_redis_globals_manager()

from logger.logger_service import get_logger
logger = get_logger(__name__)


def _cache_media_capture(name: MediaType, save_path: str):
    media_capture_message = MediaCaptureMessageModel(
        path=Path(save_path), type=name.lower()
    )

    message=media_capture_message.model_dump_json()

    if not app_globals.get("media_captures"):
        app_globals["media_captures"] = [message]

    else:
        app_globals["media_captures"] += [message]

    logger.critical(app_globals["media_captures"])


def _show_media_capture_dialog(
    name: MediaType, save_path: str
):

    if name.lower() not in MediaType.get_media_types():
        raise ValueError(f"Invalid media type: {name}")

    file_url = QUrl.fromLocalFile(save_path).toString()
    formatted_message = f"File saved to:<br><a href='{file_url}' style='color: #0078d7;'>{save_path}</a><br><br>"

        # Create a non-modal popup (doesn't block the rest of the UI)
    success(
        None, formatted_message, title=f"{name.name.title()} Captured", modal=False, timeout=5000
    )

    logger.critical(f"Saved {name} media to {save_path}.")
    return True
