import os
from pathlib import Path

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QSplitter, QSizePolicy
from pyface.tasks.task_pane import TaskPane
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap


class MicrodropPane(TaskPane):
    id = "white_canvas.pane"
    name = "White Canvas Pane"

    def create(self, parent):
        widget = QWidget(parent)
        widget.setStyleSheet("background-color: white;")
        
        main_with_sidebar = create_with_sidebar(central_widget=widget)
        self.control = main_with_sidebar


class MicrodropSidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), '#575757')
        self.setPalette(palette)
        self.setStyleSheet("""background-color: none; QLabel, 
                           QPushButton { background: transparent; }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        pixmap = QPixmap(Path(__file__).parents[1]/ "resources" / "scibots-icon.png")
        if not pixmap.isNull():
            logo_label.setPixmap(pixmap.scaledToWidth(48, Qt.SmoothTransformation))
        logo_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout.addWidget(logo_label, alignment=Qt.AlignHCenter | Qt.AlignTop)
        layout.addSpacing(10)

        hamburger_btn = QPushButton()
        hamburger_btn.setFixedSize(QSize(40, 40))
        hamburger_btn.setText("☰")
        hamburger_btn.setStyleSheet("font-size: 24px; color: green; background: none; border: none;")
        hamburger_btn.setCursor(Qt.PointingHandCursor)
        layout.addWidget(hamburger_btn, alignment=Qt.AlignHCenter)

        layout.addStretch(1) # Spacer to push items to top

        self.setLayout(layout)
        self.setMinimumWidth(80)
        self.setMaximumWidth(200)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)


def create_with_sidebar(central_widget: QWidget):
    """
    Returns a QSplitter with a sidebar on the left and the given central widget on the right.
    You can use this as your main window's central widget.
    """
    splitter = QSplitter(Qt.Horizontal)
    sidebar = MicrodropSidebar()
    splitter.addWidget(sidebar)
    splitter.addWidget(central_widget)
    splitter.setSizes([80, 600])
    splitter.setCollapsible(0, False)
    splitter.setCollapsible(1, False)
    sidebar.setMinimumWidth(80)
    sidebar.setMaximumWidth(200)
    sidebar.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)
    return splitter