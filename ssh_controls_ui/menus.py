from PySide6.QtWidgets import QMainWindow
from pyface.action.api import Action
from pyface.tasks.action.api import SGroup

from .dramatiq_listener import SSHControlUIListener
from .view_model import SSHControlViewModel, SSHControlViewModelSignals
from .widget import SSHControlView
from .model import SSHControlModel

from .sync_dialog.dramatiq_listener import SyncDialogListener
from .sync_dialog.model import SyncDialogModel
from .sync_dialog.view_model import SyncDialogViewModel, SyncDialogViewModelSignals
from .sync_dialog.widget import SyncDialogView


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
    accelerator = "Ctrl+Shift+S"
    tooltip = "Launch the SSH Key Uploader application."
    style = "window"

    def traits_init(self, *args, **kwargs):
        self._window = None
        self.model = SSHControlModel()
        self.view_model = SSHControlViewModel(
            model=self.model,
            view_signals=SSHControlViewModelSignals(),
        )
        self.listener = SSHControlUIListener(ui=self.view_model)

    def perform(self, event):
        if self._window is not None:
            self._window.close()
            self._window = None

        widget = SSHControlView(view_model=self.view_model)
        widget.initialize_field_values(
            host=self.model.host,
            port=self.model.port,
            username=self.model.username,
            password=self.model.password,
            key_name=self.model.key_name,
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
    tooltip = "Pull the remote backend's Experiments/ folder locally via rsync over SSH."
    style = "window"

    def traits_init(self, *args, **kwargs):
        self._window = None
        self.model = SyncDialogModel()
        self.view_model = SyncDialogViewModel(
            model=self.model,
            view_signals=SyncDialogViewModelSignals(),
        )
        self.listener = SyncDialogListener(ui=self.view_model)

    def perform(self, event):
        if self._window is not None:
            self._window.close()
            self._window = None

        widget = SyncDialogView(view_model=self.view_model)
        widget.initialize_field_values(
            host=self.model.host,
            port=self.model.port,
            username=self.model.username,
            key_name=self.model.key_name,
            remote_path=self.model.remote_experiments_path,
            local_dest=self.model._default_dest(),
        )
        widget.connect_signals()

        self._window = SyncDialogApp(main_widget=widget)
        self._window.show()


def menu_factory():
    """Menu group containing both SSH actions."""
    return SGroup(
        ShowSshKeyUploaderAction(),
        ShowSyncRemoteExperimentsAction(),
        id="remote_controls",
    )
