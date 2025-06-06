from pathlib import Path

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QSizePolicy
from pyface.tasks.task_pane import TaskPane
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon, QFont

from dropbot_tools_menu.plugin import DropbotToolsMenuPlugin
from dropbot_tools_menu.menus import dropbot_tools_menu_factory


class MicrodropCentralCanvas(TaskPane):
    id = "microdrop.central_canvas"
    name = "Microdrop Canvas"
    
    def create(self, parent):
        widget = MicrodropSidebar(parent, task = self.task)
        self.control = widget


class MicrodropSidebar(QWidget):
    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.task = task
        
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
        self.menu_layout.setSpacing(26)
        self.menu_widget.setLayout(self.menu_layout)

        # Menu buttons
        self.menu_buttons = []
        menu_options = [
            ("File", "file.png"),
            ("Tools", "tools.png"),
            ("Help", "help.png"),
            ("Info", "info.png"),
            ("Diagnostics", "diagnostics.png"),
            ("Plugins", "plugins.png"),
            ("Protocol Repository", "protocol_repository.png"),
            ("Exit", "exit.png"),
        ]
        icon_dir = Path(__file__).parents[1] / "resources"
        icon_size = QSize(22, 22)
        font = QFont()
        font.setBold(True)
        for option, icon in menu_options:
            btn = QPushButton("\n".join(option.split(" ")))
            btn.setFont(font)
            btn.setFixedWidth(140)
            btn.setIcon(QIcon(str(icon_dir / icon)))
            btn.setIconSize(icon_size)
            btn.setStyleSheet(
                """
                background: none;
                border: none;
                color: green;
                font-size:2em;
                text-align: left;
                padding-left: 8px;
                """
            )
            btn.setCursor(Qt.PointingHandCursor)
             
            self.menu_layout.addWidget(btn)
            self.menu_buttons.append(btn)
        
        self.menu_widget.setVisible(False)
        self.layout.addWidget(self.menu_widget, alignment=Qt.AlignHCenter)

        # connections
        button_names = [name for name, _ in menu_options]
        self.menu_buttons[button_names.index("Exit")].clicked.connect(self._handle_exit)
        self.menu_buttons[button_names.index("Diagnostics")].clicked.connect(self._handle_diagnostics)

        self.setLayout(self.layout)

    def toggle_menu(self):
        self.menu_widget.setVisible(not self.menu_widget.isVisible())

    def _handle_diagnostics(self):
        app = self.task.window.application
        dropbot_plugin = None
        for plugin in app.plugin_manager._plugins:
            if isinstance(plugin, DropbotToolsMenuPlugin):
                dropbot_plugin = plugin
                break
        if dropbot_plugin is None:
            print("DropbotToolsMenuPlugin not found.")
            return

        dropbot_menu = dropbot_tools_menu_factory(dropbot_plugin)
        run_all_tests_action = dropbot_menu.items[0]
        run_all_tests_action.perform(self)

    def _handle_exit(self):
        self.task.window.application.exit()
