from pathlib import Path

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QSizePolicy
from pyface.tasks.task_pane import TaskPane
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap


class MicrodropCentralCanvas(TaskPane):
    id = "microdrop.central_canvas"
    name = "Microdrop Canvas"
    
    def create(self, parent):
        widget = MicrodropSidebar(parent)
        self.control = widget


class MicrodropSidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 10, 0, 10) # add some padding to the top and bottom
        layout.setSpacing(15) # add some spacing between the items
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter) # Align the items to the top and center

        # Logo
        logo_label = QLabel()
        pixmap = QPixmap(Path(__file__).parents[1]/ "resources" / "scibots-icon.png")
        if not pixmap.isNull():
            logo_label.setPixmap(pixmap.scaledToWidth(48, Qt.SmoothTransformation))
        logo_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout.addWidget(logo_label)

        # Hamburger button
        hamburger_btn = QPushButton()
        hamburger_btn.setFixedSize(QSize(40, 40))
        hamburger_btn.setText("☰")
        hamburger_btn.setStyleSheet("font-size: 24px; color: green; background: none; border: none;")
        hamburger_btn.setCursor(Qt.PointingHandCursor)
        layout.addWidget(hamburger_btn, alignment=Qt.AlignHCenter)

        self.setLayout(layout)
