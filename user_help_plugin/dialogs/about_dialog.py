from pathlib import Path

from PySide6.QtWebEngineWidgets import QWebEngineView
from pyface.qt.QtWidgets import QDialog, QVBoxLayout
from pyface.qt.QtCore import QUrl


ARCHITECTURE_HTML = Path(__file__).parent.parent / "resources" / "microdrop-architecture.html"


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About MicroDrop")
        self.resize(1024, 768)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        self.web_view.load(QUrl.fromLocalFile(str(ARCHITECTURE_HTML)))
        layout.addWidget(self.web_view)
