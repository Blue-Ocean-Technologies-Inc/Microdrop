# sys imports
import os
import sys
from pathlib import Path

from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icons.icons import ICON_MENU
# Local imports.
from .helpers import get_microdrop_redis_globals_manager
from .preferences import MicrodropPreferences
from dropbot_controller.consts import START_DEVICE_MONITORING
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_tools_menu.plugin import DropbotToolsMenuPlugin
from dropbot_tools_menu.menus import dropbot_tools_menu_factory
from .consts import (scibots_icon_path, sidebar_menu_options,
                     hamburger_btn_stylesheet, EXPERIMENT_DIR)

# Enthought library imports.
from traits.etsconfig.api import ETSConfig
from traits.api import Bool, Instance, List, Property, observe, Directory

from envisage.ui.tasks.tasks_application import DEFAULT_STATE_FILENAME
from envisage.ui.tasks.api import TasksApplication

from pyface.tasks.api import TaskWindowLayout
from pyface.action.api import StatusBarManager
from pyface.image_resource import ImageResource
from pyface.splash_screen import SplashScreen

from PySide6.QtWidgets import (QToolBar, QLabel,
                               QPushButton, QVBoxLayout,
                               QHBoxLayout, QWidget, QFrame)
from PySide6.QtCore import Qt, QEvent, QSize
from PySide6.QtGui import QPixmap, QFont


from logger.logger_service import get_logger
logger = get_logger(__name__)


# set some global consts used application wide.
ETSConfig.company = "Sci-Bots"
ETSConfig.user_data = str(Path.home() / "Documents" / ETSConfig.company / "Microdrop")
ETSConfig.application_home = str(Path(ETSConfig.application_data) / "Microdrop")


class MicrodropApplication(TasksApplication):
    """Device Viewer application based on enthought envisage's The chaotic attractors Tasks application."""

    #### 'IApplication' interface #############################################

    # The application's globally unique identifier.
    id = "microdrop.frontend.app"

    # The application's user-visible name.
    name = "Microdrop Next Gen"

    #### 'TasksApplication' interface #########################################

    ###### DONE USING ETSConfig NOW #################################################################

    # #: The directory on the local file system used to persist application data. Should be same as state_location for convenience.
    # home = application_home_directory
    #
    # #: The directory on the local file system used to persist window layout
    # #: information.
    # state_location = application_home_directory / ".save_state"
    #
    # #: We don't use this directory, but it defaults to "~/enthought" and keeps creating it so we set it to our save location
    # user_data = application_home_directory / "Experimental_Data "

    #################################################################################################

    #: The filename that the application uses to persist window layout
    #: information.
    state_filename = DEFAULT_STATE_FILENAME

    # The default window-level layout for the application.
    default_layout = List(TaskWindowLayout)

    # Whether to restore the previous application-level layout when the applicaton is started.
    always_use_default_layout = Property(Bool)

    # experiments directory
    experiments_directory = Property(Directory)
    current_experiment_directory = Property(Directory)

    # branding
    icon = Instance(ImageResource)
    splash_screen = Instance(SplashScreen)

    #### 'Application' interface ####################################

    preferences_helper = Instance(MicrodropPreferences)

    ###########################################################################
    # Private interface.
    ###########################################################################

    #### Trait initializers ###################################################

    # note: The _default after a trait name to define a method is a convention to indicate that the trait is a
    # default value for another trait.

    def _default_layout_default(self):
        """
        Trait initializer for the default_layout task, which is the active task to be displayed. It is gotten from the
        preferences.

        """
        active_task = self.preferences_helper.default_task
        tasks = [factory.id for factory in self.task_factories]
        return [
            TaskWindowLayout(*tasks, active_task=active_task, size=(800, 600))
        ]

    def _preferences_helper_default(self):
        """
        Retireve the preferences from the preferences file using the DeviceViewerPreferences class.
        """
        return MicrodropPreferences(preferences=self.preferences)

    def _icon_default(self):
        icon_path = Path(__file__).parent.parent / 'microdrop_style' / 'icons' / 'Microdrop_Icon.png'
        return ImageResource(str(icon_path))

    def _splash_screen_default(self):
        splash_image_path = Path(__file__).parent.parent / 'microdrop_style' / 'icons' / 'Microdrop_Primary_Logo_FHD.png'
        return SplashScreen(
            image=ImageResource(str(splash_image_path)),
            text="Microdrop-Next-Gen v.alpha"
        )

    #### Trait property getter/setters ########################################

    # the _get and _set tags in the methods are used to define a getter and setter for a trait property.

    def _get_always_use_default_layout(self):
        return self.preferences_helper.always_use_default_layout

    def _get_experiments_directory(self) -> Path:
        return Path(self.preferences_helper.EXPERIMENTS_DIR)

    def _get_current_experiment_directory(self) -> Path:
        # try to get experiment directory from app globals
        globals = get_microdrop_redis_globals_manager()

        current_exp_dir = globals.get("experiment_directory", None)

        if current_exp_dir is None:
            current_exp_dir = EXPERIMENT_DIR
            globals["experiment_directory"] = EXPERIMENT_DIR

        return self.experiments_directory / current_exp_dir

    @observe('application_initialized')
    def _on_application_initialized(self, event):
        publish_message(message="", topic=START_DEVICE_MONITORING)


    ############################# Initialization ############################################################
    def traits_init(self):
        self.current_experiment_directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized microdrop application. Current experiment directory: {self.current_experiment_directory}")

    #### Handler for Layout Restore Errors if any ##########################
    def start(self):
        try:
            logger.debug("Starting new Microdrop application instance.")
            return super().start()
        except Exception as e:
            
            import traceback
            logger.debug("Error restoring layout, falling back to default layout.")
            traceback.print_exc()
            
            self.preferences_helper.always_use_default_layout = True
            
            return super().start()

    @observe('windows:items')
    def _on_windows_updated(self, event):

        if self.active_window:
            window = self.active_window

            if is_dark_mode():
                stylesheet = """
                QStatusBar {
                    color: #dadedf;              
                    font-weight: bold;  
                    font-size: 14x; 
                    font-family: Arial;
                    background: #222222;
                    border-top: 2px solid #333333 ;
                    border-bottom: 2px solid #333333;
                }
                QStatusBar::item {border: None;}
            """
            else:
                stylesheet = """
                            QStatusBar {
                                color: #222222;
                                font-weight: bold;
                                font-size: 14x;
                                font-family: Arial;
                                background: #f2f3f4;
                                border-top: 2px solid #dadedf;
                                border-bottom: 2px solid #dadedf;
                            }
                            QStatusBar::item {border: None;}
                         """

            window.status_bar_manager = StatusBarManager(messages=["\t" * 10 + "Free Mode"], size_grip=True)
            window.status_bar_manager.status_bar.setStyleSheet(stylesheet)
            window.status_bar_manager.status_bar.setContentsMargins(30, 0, 30, 0)

            # if not hasattr(window.control, "_left_toolbar"):
            #     left_toolbar = MicrodropSidebar(window.control, task=window.active_task)
            #
            #     # Add to the left of the main window
            #     window.control.addToolBar(Qt.LeftToolBarArea, left_toolbar)
            #
            #     # Optionally, prevent closing the toolbar
            #     left_toolbar.setContextMenuPolicy(Qt.PreventContextMenu)
            #
            #     # Store a reference so it's not re-added
            #     window.control._left_toolbar = left_toolbar


class MicrodropSidebar(QToolBar):
    def __init__(self, parent=None, task=None):
        super().__init__("Permanent Sidebar", parent)
        self.task = task
        
        #self.setOrientation(Qt.Vertical)
        #self.setMovable(False)
       # self.setFloatable(False)
       # self.setAllowedAreas(Qt.LeftToolBarArea)
        #self.setFixedWidth(160)
        self.setObjectName("PermanentLeftToolbar")

        container = QWidget()
        self.layout = QVBoxLayout()
       # self.layout.setContentsMargins(0, 10, 0, 10)
       # self.layout.setSpacing(15)
       # self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Logo
        self.logo_label = QLabel()
        pixmap = QPixmap(scibots_icon_path)
        if not pixmap.isNull():
            self.logo_label.setPixmap(pixmap.scaledToWidth(48, Qt.SmoothTransformation))
        #self.logo_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout.addWidget(self.logo_label, alignment=Qt.AlignHCenter)

        # Hamburger button
        self.hamburger_btn = QPushButton(ICON_MENU)
        self.hamburger_btn.setFont(QFont("Material Symbols Outlined"))
        self.hamburger_btn.setFixedSize(QSize(40, 40))
        self.hamburger_btn.setStyleSheet(hamburger_btn_stylesheet)
        self.hamburger_btn.setCursor(Qt.PointingHandCursor)
        self.hamburger_btn.clicked.connect(self.toggle_menu)
        self.layout.addWidget(self.hamburger_btn, alignment=Qt.AlignHCenter)

        self.menu_widget = QWidget()
        self.menu_layout = QVBoxLayout()
        self.menu_layout.setContentsMargins(0, 0, 0, 0)
        self.menu_layout.setSpacing(15)
        self.menu_widget.setLayout(self.menu_layout)

        # Menu buttons
        self.menu_buttons = []
        icon_font = QFont("Material Symbols Outlined")
        icon_font.setPointSize(22)
        color_str = "white" if is_dark_mode() else "black"

        for option, icon_code in sidebar_menu_options:
            btn = SidebarMenuButton(icon_code, option, icon_font, color_str)
            self.menu_layout.addWidget(btn)
            self.menu_buttons.append((btn, option))
        
        self.menu_widget.setVisible(False)
        self.layout.addWidget(self.menu_widget, alignment=Qt.AlignHCenter)
        # connections
        button_names = [name for name, _ in sidebar_menu_options]
        self.menu_buttons[button_names.index("Exit")][0].clicked.connect(self._handle_exit)
        self.menu_buttons[button_names.index("Diagnostics")][0].clicked.connect(self._handle_diagnostics)

        container.setLayout(self.layout)
        self.addWidget(container)
        self.update_menu_colors()

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

    def event(self, event):
        if event.type() == QEvent.PaletteChange:
            self.update_menu_colors()
            self.toggle_menu
        return super().event(event)

    def update_menu_colors(self):
        if is_dark_mode():
            color_str = "white"
        else:
            color_str = "black"
        for btn, _ in self.menu_buttons:
            btn.set_color(color_str)
        # Apply hamburger button stylesheet with three color placeholders (normal, hover, pressed)
        self.hamburger_btn.setStyleSheet(hamburger_btn_stylesheet % (color_str, color_str, color_str))


class SidebarMenuButton(QFrame):
    def __init__(self, icon_code, label, icon_font, color_str, text_font=None, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarMenuButton")
        self.setStyleSheet(f"QFrame#SidebarMenuButton {{ background: none; }}")
        self.setCursor(Qt.PointingHandCursor)
        self.icon_label = QLabel(icon_code)
        self.icon_label.setFont(icon_font)
        self.icon_label.setStyleSheet(f"color: {color_str};")
        self.icon_label.setFixedWidth(28)
        self.text_label = QLabel(label)
        text_font = QFont()
        text_font.setPointSize(11)
        self.text_label.setFont(text_font)
        self.text_label.setStyleSheet(f"color: {color_str};")
        self.text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(8, 0, 0, 0)
        hbox.setSpacing(12)
        hbox.addWidget(self.icon_label)
        hbox.addWidget(self.text_label)
        self.setLayout(hbox)
        self.setFixedHeight(37)
        self.setMinimumWidth(140)

    def set_color(self, color_str):
        self.icon_label.setStyleSheet(f"color: {color_str};")
        self.text_label.setStyleSheet(f"color: {color_str};")

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    from PySide6.QtCore import Signal
    clicked = Signal()
    
    
def is_dark_mode():
    if sys.platform == "darwin":
        import subprocess
        try:
            mode = subprocess.check_output(
                "defaults read -g AppleInterfaceStyle",
                shell=True
            ).strip()
            return mode == b"Dark"
        except Exception:
            return False
    elif sys.platform.startswith("win"):
        try:
            import winreg
            reg = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(
                reg,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            apps_use_light_theme, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return apps_use_light_theme == 0
        except Exception:
            return False
    else:
        gtk_theme = os.environ.get("GTK_THEME", "").lower()
        if "dark" in gtk_theme:
            return True
        qt_theme = os.environ.get("QT_QPA_PLATFORMTHEME", "").lower()
        if "dark" in qt_theme:
            return True
        # KDE check
        kde_globals = os.path.expanduser("~/.config/kdeglobals")
        if os.path.isfile(kde_globals):
            try:
                with open(kde_globals, "r") as f:
                    if "ColorScheme=Dark" in f.read():
                        return True
            except Exception:
                pass
        return False