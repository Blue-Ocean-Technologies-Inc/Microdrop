import os

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QDialog,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from logger.logger_service import get_logger

logger = get_logger(__name__)


class DialogView(QWidget):
    """Manages popup dialogs triggered by the message handler's DialogSignals."""

    def __init__(self, dialog_signals, message_handler, parent=None):
        super().__init__(parent)
        self._message_handler = message_handler
        self._no_power_dialog = None

        dialog_signals.show_shorts_popup.connect(self._on_show_shorts)
        dialog_signals.show_halted_popup.connect(self._on_show_halted)
        dialog_signals.show_no_power_dialog.connect(self._on_show_no_power)
        dialog_signals.close_no_power_dialog.connect(self._on_close_no_power)

    @Slot(dict)
    def _on_show_shorts(self, data):
        QMessageBox.warning(self, data["title"], data["text"])

    @Slot(str)
    def _on_show_halted(self, text):
        QMessageBox.critical(self, "ERROR: DropBot Halted", text)

    @Slot()
    def _on_show_no_power(self):
        self._no_power_dialog = QDialog()
        self._no_power_dialog.setWindowTitle("ERROR: No Power")
        self._no_power_dialog.setFixedSize(400, 300)

        layout = QVBoxLayout()
        self._no_power_dialog.setLayout(layout)

        browser = QTextBrowser()
        images_dir = os.path.join(os.path.dirname(__file__), "images")
        power_img = os.path.join(images_dir, "dropbot-power.png")
        browser.setHtml(
            f"""
            <html><body>
            <h3>DropBot currently has no power supply connected.</h3>
            <strong>Plug in power supply cable<br></strong>
            <img src='{power_img}' width="104" height="90">
            <strong><br>Click "Retry" after plugging in the power cable.</strong>
            </body></html>
            """
        )

        retry_button = QPushButton("Retry")
        retry_button.clicked.connect(self._message_handler.request_retry_connection)

        layout.addWidget(browser)
        layout.addWidget(retry_button)
        self._no_power_dialog.exec()

    @Slot()
    def _on_close_no_power(self):
        if self._no_power_dialog:
            self._no_power_dialog.close()
            self._no_power_dialog = None
