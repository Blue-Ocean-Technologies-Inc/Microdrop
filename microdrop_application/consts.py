from pathlib import Path
import time

from microdrop_style.icons.icons import (ICON_FOLDER_OPEN, ICON_EMOJI_OBJECTS,
                                         ICON_HEADSET_MIC, ICON_INFO,
                                         ICON_TROUBLESHOOT, ICON_EXTENSION,
                                         ICON_DESCRIPTION, ICON_CANCEL)

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {}

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

EXPERIMENT_DIR = f"Exp_{time.strftime('%Y_%m_%d_%H_%M_%S')}"