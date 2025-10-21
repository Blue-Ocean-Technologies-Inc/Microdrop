# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

listener_name = f"{PKG}_listener"

# Topics published by this plugin
CHANGE_LOG_LEVEL = 'microdrop/signals/change_log_level'

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{listener_name}": [CHANGE_LOG_LEVEL]}