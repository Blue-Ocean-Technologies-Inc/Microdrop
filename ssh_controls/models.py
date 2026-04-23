"""
Pydantic models and validated publishers for ssh_controls topics.

Follows the pattern from electrode_controller/models.py — each request
type is a Pydantic BaseModel paired with a ValidatedTopicPublisher
subclass that exposes a typed .publish(...) convenience method.
"""
from pydantic import BaseModel

from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher


class ExperimentsSyncRequest(BaseModel):
    """Payload for a remote experiments rsync-pull request.

    Attributes
    ----------
    host : str
        Hostname or IP address of the remote Microdrop backend.
    port : int
        SSH port on the remote host.
    username : str
        SSH username for the remote host.
    identity_path : str
        Absolute filesystem path to the SSH private key on the local
        (frontend) machine.
    src : str
        Remote source path, typically of the form
        ``"user@host:~/.../Experiments/"``. Trailing slash is significant —
        it tells rsync to copy directory *contents* rather than nest the
        directory inside the destination.
    dest : str
        Absolute local filesystem path where files will be written.
    """
    host: str
    port: int
    username: str
    identity_path: str
    src: str
    dest: str


class ExperimentsSyncRequestPublisher(ValidatedTopicPublisher):
    """Validated publisher for ``SYNC_EXPERIMENTS_REQUEST`` topic.

    Exposes a keyword-only .publish(...) method that mirrors the
    ExperimentsSyncRequest fields for call-site readability.
    """
    validator_class = ExperimentsSyncRequest

    def publish(self, *, host, port, username, identity_path, src, dest, **kw):
        super().publish({
            "host": host,
            "port": port,
            "username": username,
            "identity_path": identity_path,
            "src": src,
            "dest": dest,
        }, **kw)
