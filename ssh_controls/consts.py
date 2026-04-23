# This module's package.
import os

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

GENERATE_KEYPAIR = "ssh_service/request/generate_keypair"
KEY_UPLOAD = "ssh_service/request/key_upload"
SYNC_EXPERIMENTS_REQUEST = "ssh_service/request/sync_experiments"

ACTOR_TOPIC_DICT = {
    listener_name: [
        GENERATE_KEYPAIR,
        KEY_UPLOAD,
        SYNC_EXPERIMENTS_REQUEST,
    ]
}

# published topics
SSH_KEYGEN_SUCCESS = "ssh_service/success/ssh_keygen_success"
SSH_KEYGEN_WARNING = "ssh_service/warning/ssh_keygen_warning"
SSH_KEYGEN_ERROR = "ssh_service/error/ssh_keygen_error"

SSH_KEY_UPLOAD_SUCCESS = "ssh_service/success/ssh_key_upload_success"
SSH_KEY_UPLOAD_ERROR = "ssh_service/error/ssh_key_upload_error"

# --- Remote experiments sync ----------------------------------------------
# Response topics (ssh_controls service -> frontend)
SYNC_EXPERIMENTS_STARTED = "ssh_service/started/sync_experiments"
SYNC_EXPERIMENTS_SUCCESS = "ssh_service/success/sync_experiments"
SYNC_EXPERIMENTS_ERROR   = "ssh_service/error/sync_experiments"

# Convenience publisher singleton (matches electrode_controller/consts.py style).
# Imported here so call sites can do:
#   from ssh_controls.consts import experiments_sync_publisher
#   experiments_sync_publisher.publish(host=..., ...)
from ssh_controls.models import ExperimentsSyncRequestPublisher
experiments_sync_publisher = ExperimentsSyncRequestPublisher(topic=SYNC_EXPERIMENTS_REQUEST)
