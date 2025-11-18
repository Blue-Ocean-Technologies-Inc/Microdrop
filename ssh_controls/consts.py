# This module's package.
import os

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

GENERATE_KEYPAIR = "ssh_service/request/generate_keypair"
KEY_UPLOAD = "ssh_service/request/key_upload"

ACTOR_TOPIC_DICT = {
    listener_name: [
        GENERATE_KEYPAIR,
        KEY_UPLOAD
    ]
}

# published topics
SSH_KEYGEN_SUCCESS = "ssh_service/success/ssh_keygen_success"
SSH_KEYGEN_WARNING = "ssh_service/warning/ssh_keygen_warning"
SSH_KEYGEN_ERROR = "ssh_service/error/ssh_keygen_error"

SSH_KEY_UPLOAD_SUCCESS = "ssh_service/success/ssh_keypair_uploaded"
SSH_KEY_UPLOAD_ERROR = "ssh_service/error/ssh_keypair_upload_error"
