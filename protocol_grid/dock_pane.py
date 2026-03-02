# enthought imports
from traits.api import Str, Instance
from pyface.tasks.dock_pane import DockPane

from .services.message_listener import MessageListener
# local imports
from .widget import PGCWidget
from logger.logger_service import get_logger
from .consts import PKG, PKG_name

logger = get_logger(__name__)


class PGCDockPane(DockPane):
    """Protocol grid dock pane."""

    id = f"{PKG}.dock_pane"
    name = Str(PKG_name)

    dramatiq_message_listener = Instance(MessageListener, MessageListener())

    logger.info("Protocol Grid MessageListener created")

    def create_contents(self, parent):
        return PGCWidget(dock_pane=self, parent=parent)

    # ---- Menu action delegates ----
    def new_protocol(self):
        self.control.widget().new_protocol()

    def load_protocol_dialog(self):
        self.control.widget().import_from_json()

    def save_protocol_dialog(self):
        self.control.widget().save_protocol()

    def save_as_protocol_dialog(self):
        self.control.widget().save_protocol_as()

    def setup_new_experiment(self):
        self.control.widget().setup_new_experiment()