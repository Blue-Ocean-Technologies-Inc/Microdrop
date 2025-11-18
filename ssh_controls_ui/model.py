import os

from traits.api import HasTraits, Str


class SSHControlModel(HasTraits):
    """A dataclass to hold the application's state."""
    host = Str(os.getenv("REMOTE_HOST_IP_ADDRESS"))
    port = Str(os.getenv("REMOTE_SSH_PORT"))
    username = Str(os.getenv("REMOTE_HOST_USERNAME"))
    password = Str(os.getenv("REMOTE_PASSWORD"))
    key_name = "id_rsa_microdrop"
    generated_pub_key = ""
    generated_pub_key_path: str = ""