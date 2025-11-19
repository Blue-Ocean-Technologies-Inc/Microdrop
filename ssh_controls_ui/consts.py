# This module's package.
import os
from ssh_controls.consts import SSH_KEYGEN_SUCCESS, SSH_KEYGEN_WARNING, SSH_KEYGEN_ERROR, SSH_KEY_UPLOAD_SUCCESS, SSH_KEY_UPLOAD_ERROR

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        # published topics
        SSH_KEYGEN_SUCCESS,
        SSH_KEYGEN_WARNING,
        SSH_KEYGEN_ERROR,
        SSH_KEY_UPLOAD_SUCCESS,
        SSH_KEY_UPLOAD_ERROR
    ]
}