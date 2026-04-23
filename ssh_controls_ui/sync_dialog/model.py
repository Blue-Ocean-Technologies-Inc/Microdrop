"""Traits model for the Sync Remote Experiments dialog.

Holds field values edited by the user and the transient run state
(status text, in_progress flag). Pre-populates host/port/username
from the same .env variables used by SSHControlModel so the two
dialogs start in sync.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from traits.api import HasTraits, Str, Int, Bool
from traits.etsconfig.api import ETSConfig

load_dotenv()


class SyncDialogModel(HasTraits):
    """State of the Sync Remote Experiments dialog."""
    host = Str(os.getenv("REMOTE_HOST_IP_ADDRESS", ""))
    port = Int(int(os.getenv("REMOTE_SSH_PORT") or 22))
    username = Str(os.getenv("REMOTE_HOST_USERNAME", ""))

    # Identity file lives in ~/.ssh/<key_name> on the local host
    key_name = Str("id_rsa_microdrop")

    # Remote path to pull from (trailing slash => copy contents, not the dir)
    remote_experiments_path = Str("~/Documents/Sci-Bots/Microdrop/Experiments/")

    # Dialog run state
    status = Str("Idle")
    in_progress = Bool(False)

    def _default_dest(self) -> str:
        """Resolve the default local destination path."""
        return str(Path(ETSConfig.user_data) / "Remote-Experiments")

    def resolve_identity_path(self) -> str:
        return str(Path.home() / ".ssh" / self.key_name)

    def resolve_src(self) -> str:
        """Build ``user@host:path`` form expected by rsync."""
        return f"{self.username}@{self.host}:{self.remote_experiments_path}"
