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

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 10, 0, 10) # add some padding to the top and bottom
        self.layout.setSpacing(15) # add some spacing between the items
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter) # Align the items to the top and center

        # Logo
        self.logo_label = QLabel()
        pixmap = QPixmap(Path(__file__).parents[1]/ "resources" / "scibots-icon.png")
        if not pixmap.isNull():
            self.logo_label.setPixmap(pixmap.scaledToWidth(48, Qt.SmoothTransformation))
        self.logo_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout.addWidget(self.logo_label, alignment=Qt.AlignHCenter)

        # Hamburger button
        self.hamburger_btn = QPushButton()
        self.hamburger_btn.setFixedSize(QSize(40, 40))
        self.hamburger_btn.setText("☰")
        self.hamburger_btn.setStyleSheet("font-size: 24px; color: green; background: none; border: none;")
        self.hamburger_btn.setCursor(Qt.PointingHandCursor)
        self.hamburger_btn.clicked.connect(self.toggle_menu)
        self.layout.addWidget(self.hamburger_btn, alignment=Qt.AlignHCenter)

        self.menu_widget = QWidget()
        self.menu_layout = QVBoxLayout()
        self.menu_layout.setContentsMargins(0, 0, 0, 0)
        self.menu_layout.setSpacing(5)
        self.menu_widget.setLayout(self.menu_layout)

        # Menu buttons
        self.menu_buttons = []
        menu_options = ["File", "Tools", "Help", "Info", "Diagnostics", "Plugins", "Protocol Repository", "Exit"]
        for option in menu_options:
            btn = QPushButton(option)
            btn.setFixedWidth(140)
            btn.setStyleSheet("background: none; border: none; color: green; font-size:16px;")
            btn.setCursor(Qt.PointingHandCursor)
             
            self.menu_layout.addWidget(btn)
            self.menu_buttons.append(btn)
        
        self.menu_widget.setVisible(False)
        self.layout.addWidget(self.menu_widget, alignment=Qt.AlignHCenter)

        self.setLayout(self.layout)

    def toggle_menu(self):
        self.menu_widget.setVisible(not self.menu_widget.isVisible())
