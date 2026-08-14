from PySide6.QtWidgets import QMainWindow
from pyface.action.api import Action
from pyface.tasks.action.api import SGroup, SMenu

from .preferences import SSHControlPreferences
from .dramatiq_listener import SSHControlUIListener
from .view_model import SSHControlViewModel, SSHControlViewModelSignals
from .widget import SSHControlView
from .model import SSHControlModel

from .sync_dialog.dramatiq_listener import SyncDialogListener
from .sync_dialog.model import SyncDialogModel
from .sync_dialog.view_model import SyncDialogViewModel, SyncDialogViewModelSignals
from .sync_dialog.widget import SyncDialogView

# ---------------------------------------------------------------------------
# One view-model + listener per dialog, shared by every Action instance.
#
# The menu bar is REBUILT whenever plugin groups hot-mount, recreating
# these Actions — but a dramatiq listener name can register only once,
# so the first registration's view-model receives every message
# forever. An Action that built its own view-model would show a window
# wired to signals the listener never fires (the "stuck on Starting…"
# portal). The session below outlives the Actions, so every rebuild's
# windows connect to the very view-model the listener drives.
# ---------------------------------------------------------------------------
_key_portal_session = None
_sync_session = None


def key_portal_view_model():
    global _key_portal_session
    if _key_portal_session is None:
        view_model = SSHControlViewModel(
            model=SSHControlModel(),
            prefs=SSHControlPreferences(),
            view_signals=SSHControlViewModelSignals(),
        )
        _key_portal_session = (view_model,
                               SSHControlUIListener(ui=view_model))
    return _key_portal_session[0]


def sync_view_model():
    global _sync_session
    if _sync_session is None:
        view_model = SyncDialogViewModel(
            model=SyncDialogModel(),
            prefs=SSHControlPreferences(),
            view_signals=SyncDialogViewModelSignals(),
        )
        _sync_session = (view_model, SyncDialogListener(ui=view_model))
    return _sync_session[0]


class SshKeyUploaderApp(QMainWindow):
    """Main window for the SSH Key Portal dialog."""

    def __init__(self, main_widget):
        super().__init__()
        self.setWindowTitle("SSH Key Portal")
        self.setGeometry(100, 100, 480, 500)
        self.setCentralWidget(main_widget)


class ShowSshKeyUploaderAction(Action):
    """Pyface action that shows the SSH Key Portal window."""
    name = "SSH &Key Portal..."
    tooltip = "Launch the SSH Key Uploader application."
    style = "window"

    def traits_init(self, *args, **kwargs):
        self._window = None
        self.view_model = key_portal_view_model()
        self.prefs = self.view_model.prefs
        self.model = self.view_model.model

    def perform(self, event):
        if self._window is not None:
            self._window.close()
            self._window = None

        widget = SSHControlView(view_model=self.view_model)
        widget.initialize_field_values(
            host=self.prefs.host,
            port=self.prefs.port,
            username=self.prefs.username,
            password=self.model.password,
            key_name=self.prefs.key_name,
        )
        widget.connect_signals()

        self._window = SshKeyUploaderApp(main_widget=widget)
        self._window.show()


class SyncDialogApp(QMainWindow):
    """Main window for the Sync Remote Experiments dialog."""

    def __init__(self, main_widget):
        super().__init__()
        self.setWindowTitle("Sync Remote Experiments")
        self.setGeometry(150, 150, 480, 360)
        self.setCentralWidget(main_widget)


class ShowSyncRemoteExperimentsAction(Action):
    """Pyface action that shows the Sync Remote Experiments dialog."""
    name = "Sync Remote &Experiments..."
    accelerator = "Ctrl+Shift+S"
    tooltip = "Pull the remote backend's Experiments/ folder locally via rsync over SSH."
    style = "window"

    def traits_init(self, *args, **kwargs):
        self._window = None
        self.view_model = sync_view_model()
        self.prefs = self.view_model.prefs
        self.model = self.view_model.model

    def perform(self, event):
        if self._window is not None:
            self._window.close()
            self._window = None

        widget = SyncDialogView(view_model=self.view_model)
        widget.initialize_field_values(
            host=self.prefs.host,
            port=self.prefs.port,
            username=self.prefs.username,
            key_name=self.prefs.key_name,
            remote_path=self.prefs.remote_experiments_path,
            local_dest=self.model.resolve_dest(self.prefs.device_id),
            device_id=self.prefs.device_id,
        )
        widget.connect_signals()

        self._window = SyncDialogApp(main_widget=widget)
        self._window.show()


def menu_factory():
    """Menu group containing both SSH actions."""
    return SMenu(
        ShowSshKeyUploaderAction(),
        ShowSyncRemoteExperimentsAction(),
        id="remote_controls",
        name="&Remote Controls",
    )
