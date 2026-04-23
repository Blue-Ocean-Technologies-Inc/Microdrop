"""Transient per-session state for the Sync Remote Experiments dialog.

Persisted fields (host, port, username, key_name, remote_experiments_path,
device_id) live on ``SSHControlPreferences`` — see
``ssh_controls_ui/preferences.py``.
"""
from pathlib import Path

from traits.api import HasTraits, Str, Bool
from traits.etsconfig.api import ETSConfig


class SyncDialogModel(HasTraits):
    """Runtime state of the Sync Remote Experiments dialog."""
    status = Str("Idle")
    in_progress = Bool(False)

    def resolve_dest(self, device_id: str) -> str:
        """Build the local destination path, qualified by device_id."""
        base = Path(ETSConfig.user_data) / "Remote-Experiments"
        if device_id:
            return str(base / device_id)
        return str(base)

    def resolve_identity_path(self, key_name: str) -> str:
        return str(Path.home() / ".ssh" / key_name)

    def resolve_src(self, username: str, host: str, remote_path: str) -> str:
        """Build ``user@host:path`` form expected by rsync."""
        return f"{username}@{host}:{remote_path}"