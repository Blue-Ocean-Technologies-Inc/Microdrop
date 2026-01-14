from traits.api import HasTraits, Str, observe, Instance, Bool, File
from pyface.tasks.dock_pane import DockPane

from pathlib import Path

from logger.logger_service import get_logger
from protocol_grid.consts import PKG_name

logger = get_logger(__name__)


class ProtocolStateTracker(HasTraits):
    """tracks current protocol file state and modifications."""

    protocol_name = Str("untitled")
    loaded_protocol_path = File()
    modified_tag = Str(" [modified]")
    is_modified = Bool(True)
    dock_pane = Instance(DockPane)

    def update_display_name(self):
        _modified_tag = self.modified_tag if self.is_modified else ""
        self.dock_pane.name = PKG_name + "\t-\t" + self.protocol_name + _modified_tag

    def traits_init(self):
        self.update_display_name()

    @observe("protocol_name")
    def _protocol_name_changed(self, event):
        logger.debug(f"Protocol name change event: {event}")
        self.update_display_name()

    @observe("is_modified")
    def _is_modified_changed(self, event):
        logger.debug(f"Protocol modification change event: {event}")
        self.update_display_name()

    def set_loaded_protocol(self, file_path):
        """to set InformationPanel label as the currently loaded protocol file."""
        if file_path:
            path = Path(file_path)
            self.loaded_protocol_path = str(path)
            self.protocol_name = path.stem  # filename without extension
            self.is_modified = False
            logger.info(f"Protocol loaded: {self.protocol_name}")

        else:
            raise Warning("Cannot set loaded protocol to tracker. Need a non empty string file path.")

    def reset(self):
        self.reset_traits(["loaded_protocol_path", "protocol_name", "is_modified"])

    def set_saved_protocol(self, file_path):
        """to set InformationPanel label as saved protocol name."""
        if file_path:
            path = Path(file_path)
            self.loaded_protocol_path = str(path)
            self.protocol_name = path.stem
            self.is_modified = False
            logger.critical(f"Protocol saved as: {self.protocol_name}")

    def get_protocol_display_name(self):
        """get protocol name with modification status."""
        name = self.protocol_name
        if not self.is_modified or name == "untitled":
            return f"{name}"
        else:
            return f"{name} [modified]"
