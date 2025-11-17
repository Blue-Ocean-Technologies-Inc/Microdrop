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
SSH_KEYPAIR_GENERATED = "ssh_service/success/ssh_keypair_generated"
SSH_KEY_UPLOADED = "ssh_service/success/ssh_keypair_uploaded"
SSH_SERVICE_WARNING = "ssh_service/warnings"
SSH_SERVICE_ERROR = "ssh_service/errors"
