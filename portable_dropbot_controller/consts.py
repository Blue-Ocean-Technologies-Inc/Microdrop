# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")


PORT_DROPBOT_STATUS_UPDATE = "portable_dropbot/signals/board_status_update"
TOGGLE_DROPBOT_LOADING = "portable_dropbot/signals/toggle_dropbot_loading"

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "dropbot/requests/#",
    ]}
