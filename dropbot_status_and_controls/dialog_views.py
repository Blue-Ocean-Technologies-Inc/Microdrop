import os

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QPushButton, QMessageBox, QDialog, QTextBrowser, QWidget

from logger.logger_service import get_logger

logger = get_logger(__name__)

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

    @Slot(str)
    def on_show_halted_popup(self, text):
        QMessageBox.critical(self, "ERROR: DropBot Halted", text)

    @Slot(dict)
    def on_show_shorts_popup(self, data):
        title = data.get('title', 'Shorts Detected')
        text = data.get('text', '')
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setFixedSize(300, 200)
        msg_box.exec()

    @Slot()
    def on_show_no_power(self):
        self.no_power_dialog = QDialog()
        self.no_power_dialog.setWindowTitle("ERROR: No Power")
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
            <title>ERROR: No Power</title>
        </head>
        <body>
            <h3>DropBot currently has no power supply connected.</h3>
            <strong>Plug in power supply cable<br></strong> <img src='{power_img_path}' width="104" height="90">
            <strong><br>Click the "Retry" button after plugging in the power cable to attempt reconnection</strong>
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
