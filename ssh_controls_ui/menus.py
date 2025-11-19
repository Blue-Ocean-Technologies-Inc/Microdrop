from PySide6.QtWidgets import QMainWindow
from dotenv import load_dotenv
from pyface.action.api import Action
from pyface.tasks.action.api import SGroup

from .dramatiq_listener import SSHControlUIListener
from .view_model import SSHControlViewModel, SSHControlViewModelSignals
from .widget import SSHControlView
from .model import SSHControlModel

load_dotenv()

class SshKeyUploaderApp(QMainWindow):
    """
    Main application window (View).
    It sets up the GUI, creates the ViewModel, and connects all signals.
    """

    def __init__(self, main_widget):
        super().__init__()
        self.title = "SSH Key Portal"
        self.setWindowTitle(self.title)
        self.setGeometry(100, 100, 480, 500)
        self.setCentralWidget(main_widget)

class ShowSshKeyUploaderAction(Action):
    """
    A Pyface action that creates and shows the SshKeyUploaderApp window.
    """
    # Define how the action appears in menus/toolbars
    name = "SSH Key Portal..."
    accelerator = "Ctrl+Shift+S"
    tooltip = "Launch the SSH Key Uploader application."
    style = "window" # Hint for where it might appear

    def traits_init(self, *args, **kwargs):
        self._window = None

        # intialize model
        self.model = SSHControlModel()
        # initialize view model
        self.view_model = SSHControlViewModel(model=self.model, view_signals=SSHControlViewModelSignals())

        # start listener
        self.listener = SSHControlUIListener(ui=self.view_model)

    def perform(self, event):
        """
        Instantiates and displays the SshKeyUploaderApp QMainWindow.
        """

        # Close any existing instance before opening a new one
        if self._window is not None:
            self._window.close()
            self._window = None

        # initialize main widget
        widget = SSHControlView(view_model=self.view_model)

        self._window = SshKeyUploaderApp(main_widget=widget)
        self._window.show()


def menu_factory():
    """Returns a menu factory function."""

    return SGroup(
        ShowSshKeyUploaderAction(),
        id="remote_controls")
