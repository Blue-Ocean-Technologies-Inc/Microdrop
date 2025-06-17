from pathlib import Path

from dropbot_controller.consts import DROPBOT_SETUP_SUCCESS

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
                                 DROPBOT_SETUP_SUCCESS,
    ]}

scibots_icon_path = Path(__file__).parent/ "resources" / "scibots-icon.png"
menu_options_icons_path = Path(__file__).parent / "resources"

sidebar_menu_options = [
            ("File", "file.png"),
            ("Tools", "tools.png"),
            ("Help", "help.png"),
            ("Info", "info.png"),
            ("Diagnostics", "diagnostics.png"),
            ("Plugins", "plugins.png"),
            ("Protocol Repository", "protocol_repository.png"),
            ("Exit", "exit.png"),
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