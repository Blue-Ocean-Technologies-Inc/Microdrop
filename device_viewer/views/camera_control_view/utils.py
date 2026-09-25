# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from pyface.qt.QtCore import QUrl

# Local imports.
from ...models.media import MediaType

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _show_media_capture_status_message(
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
