# This module's package.
import os

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    "manual_controls_listener": [
        "dropbot/signals/realtime_mode_updated"
    ]
}