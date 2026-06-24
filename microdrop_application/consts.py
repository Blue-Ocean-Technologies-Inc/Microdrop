from pathlib import Path

from dropbot_controller.consts import SHORTS_DETECTED
from microdrop_style.icons.icons import (ICON_FOLDER_OPEN, ICON_EMOJI_OBJECTS,
                                         ICON_HEADSET_MIC, ICON_INFO,
                                         ICON_TROUBLESHOOT, ICON_EXTENSION,
                                         ICON_DESCRIPTION, ICON_CANCEL)
from microdrop_utils.datetime_helpers import get_current_utc_datetime

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [ SHORTS_DETECTED ]
}

# Topics published
ADVANCED_MODE_CHANGE = "microdrop/advanced_mode_change"

# Runtime plugin-group hot load/unload. The optional magnet peripheral is split
# into two independently-toggled groups (see the Tools -> Manage Peripherals
# dialog / PluginGroupManager): a UI group (dock pane, status icon, protocol
# column) and a backend group (controller + connection search). The
# *_ENABLED_KEY app-globals flags persist each group's state so the dialog
# checkboxes and the launch-restore in MicrodropTask.activated() stay in sync
# across runs.
MAGNET_UI_GROUP = "magnet_ui"
MAGNET_BACKEND_GROUP = "magnet_backend"
PERIPHERAL_UI_ENABLED_KEY = "microdrop.peripheral_ui_enabled"
PERIPHERAL_BACKEND_ENABLED_KEY = "microdrop.peripheral_backend_enabled"


scibots_icon_path = Path(__file__).parent / "resources" / "scibots-icon.png"
application_home_directory = Path.home() / "Documents"/ "MicroDropNextGen"
APP_GLOBALS_REDIS_HASH = "microdrop_application_globals"

sidebar_menu_options = [
            ("File", ICON_FOLDER_OPEN),
            ("Tools", ICON_EMOJI_OBJECTS),
            ("Help", ICON_HEADSET_MIC),
            ("Info", ICON_INFO),
            ("Diagnostics", ICON_TROUBLESHOOT),
            ("Plugins", ICON_EXTENSION),
            ("Protocol \nRepository", ICON_DESCRIPTION),
            ("Exit", ICON_CANCEL),
        ]

# Custom hamburger button stylesheet without hover effects for sidebar compatibility
hamburger_btn_stylesheet = """QPushButton {
    font-size: 24px;
    background: none;
    border: none;
    color: %s;
    padding: 8px;
    border-radius: 4px;
}
QPushButton:hover {
    background: none;
    color: %s;
}
QPushButton:pressed {
    background: none;
    color: %s;
}
QPushButton:disabled {
    background: none;
    color: #666666;
}"""

sidebar_stylesheet = """QPushButton {
    background: none;
    border: none;
    font-size: 2em;: Invalid line ('[""]') (matched as neither section nor keyword) at line 1. 
    text-align: left;
    padding-left: 8px;
    color: %s;
}"""

EXPERIMENT_DIR = get_current_utc_datetime()