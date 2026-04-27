# This module's package.
import os

from ssh_controls.consts import (
    SSH_KEYGEN_SUCCESS, SSH_KEYGEN_WARNING, SSH_KEYGEN_ERROR,
    SSH_KEY_UPLOAD_SUCCESS, SSH_KEY_UPLOAD_ERROR,
    SYNC_EXPERIMENTS_STARTED, SYNC_EXPERIMENTS_SUCCESS, SYNC_EXPERIMENTS_ERROR,
)

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

# Listener for the SSH Key Portal dialog
listener_name = f"{PKG}_listener"

# Listener for the Sync Remote Experiments dialog (separate so each dialog
# owns its own topic set)
sync_listener_name = f"{PKG}_sync_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        SSH_KEYGEN_SUCCESS,
        SSH_KEYGEN_WARNING,
        SSH_KEYGEN_ERROR,
        SSH_KEY_UPLOAD_SUCCESS,
        SSH_KEY_UPLOAD_ERROR,
    ],
    sync_listener_name: [
        SYNC_EXPERIMENTS_STARTED,
        SYNC_EXPERIMENTS_SUCCESS,
        SYNC_EXPERIMENTS_ERROR,
    ],
}
