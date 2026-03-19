from PySide6.QtWebEngineWidgets import QWebEngineView
from pyface.qt.QtWidgets import QDialog, QVBoxLayout
from pyface.qt.QtCore import QUrl

from ..consts import FEEDBACK_URL


class SendFeedbackDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Send Feedback")
        self.resize(600, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        self.web_view.load(QUrl(FEEDBACK_URL))
        layout.addWidget(self.web_view)