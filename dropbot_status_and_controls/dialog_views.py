# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import os

# Third-party imports.
from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QDialog,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

# Microdrop package imports.
from microdrop_application.dialogs.dialog_records import record_dialog
from microdrop_application.dialogs.pyface_wrapper import error
from notifications.consts import SEVERITY_ERROR, help_target

# Local imports.
from .consts import (
    DROPBOT_STATUS_TUTORIAL_ID,
    HALTED_DIALOG_TUTORIAL_ANCHOR,
    NO_POWER_DIALOG_TUTORIAL_ANCHOR,
    PKG,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The no-power dialog's text, as its entry in the notifications drawer.
NO_POWER_TITLE = "ERROR: No Power"
NO_POWER_TEXT = (
    "DropBot currently has no power supply connected.\n"
    "Plug in the power supply cable, then click Retry to reconnect."
)

# Path to images bundled with this plugin
_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "images")


class DialogView(QWidget):
    """
    Manages popup dialogs (halted, no-power, shorts).
    Connects to DialogSignals from the message handler.
    """

    def __init__(self, dialog_signals, message_handler, parent=None):
        super().__init__(parent)
        self.message_handler = message_handler
        self.no_power_dialog = None

        # Connect dialog signals
        dialog_signals.show_halted_popup.connect(self.on_show_halted_popup)
        dialog_signals.show_no_power_dialog.connect(self.on_show_no_power)
        dialog_signals.close_no_power_dialog.connect(self.on_close_no_power)
        dialog_signals.show_shorts_popup.connect(self.on_show_shorts_popup)

    @Slot(dict)
    def on_show_halted_popup(self, data):
        reason = data.get("reason", "")
        message = data.get("message", "")
        title = data.get("title", "DropBot Halted")

        body = f"DropBot has halted {reason}." if reason else "DropBot has halted."

        error(
            parent=None,
            title=title,
            message=body + "<br><br>" + message,
            source=PKG,
            help_target=help_target(
                DROPBOT_STATUS_TUTORIAL_ID, HALTED_DIALOG_TUTORIAL_ANCHOR
            ),
        )

    @Slot(dict)
    def on_show_shorts_popup(self, data):
        title = data.get("title", "Shorts Detected")
        text = data.get("text", "")
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setFixedSize(300, 200)
        msg_box.exec()

    @Slot()
    def on_show_no_power(self):
        # A custom dialog, so recorded here as the wrapper records its own.
        record_dialog(
            SEVERITY_ERROR,
            NO_POWER_TITLE,
            NO_POWER_TEXT,
            source=PKG,
            help_target=help_target(
                DROPBOT_STATUS_TUTORIAL_ID, NO_POWER_DIALOG_TUTORIAL_ANCHOR
            ),
        )

        self.no_power_dialog = QDialog()
        self.no_power_dialog.setWindowTitle(NO_POWER_TITLE)
        self.no_power_dialog.setFixedSize(400, 300)

        layout = QVBoxLayout()
        self.no_power_dialog.setLayout(layout)

        browser = QTextBrowser()
        power_img_path = os.path.join(_IMAGES_DIR, "dropbot-power.png")

        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{NO_POWER_TITLE}</title>
        </head>
        <body>
            <h3>DropBot currently has no power supply connected.</h3>
            <strong>Plug in power supply cable<br></strong>
            <img src='{power_img_path}' width="104" height="90">
            <strong><br>Click the "Retry" button after plugging in the power
            cable to attempt reconnection</strong>
        </body>
        </html>
        """

        browser.setHtml(html_content)

        retry_button = QPushButton("Retry")
        retry_button.clicked.connect(self.message_handler.request_retry_connection)

        layout.addWidget(browser)
        layout.addWidget(retry_button)

        self.no_power_dialog.exec()

    @Slot()
    def on_close_no_power(self):
        if self.no_power_dialog:
            self.no_power_dialog.close()
            self.no_power_dialog = None
