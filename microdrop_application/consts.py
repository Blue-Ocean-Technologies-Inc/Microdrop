from pathlib import Path

from dropbot_controller.consts import DROPBOT_SETUP_SUCCESS
from microdrop_style.icons.icons import (ICON_FOLDER_OPEN, ICON_EMOJI_OBJECTS,
                                         ICON_HEADSET_MIC, ICON_INFO,
                                         ICON_TROUBLESHOOT, ICON_EXTENSION,
                                         ICON_DESCRIPTION, ICON_CANCEL)

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
                                 DROPBOT_SETUP_SUCCESS,
    ]}

scibots_icon_path = Path(__file__).parent/ "resources" / "scibots-icon.png"

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

hamburger_btn_stylesheet = "QPushButton { font-size: 24px; background: none; border: none; color: %s;}"

sidebar_stylesheet = """QPushButton {
                background: none;
                border: none;
                font-size:2em;
                text-align: left;
                padding-left: 8px;
                color: %s; }
                """