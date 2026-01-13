from traits.api import HasTraits, Str, observe, Instance, Bool
from pyface.tasks.dock_pane import DockPane

from pathlib import Path

from logger.logger_service import get_logger
from protocol_grid.consts import PKG_name

logger = get_logger(__name__)


class ProtocolStateTracker(HasTraits):
    """tracks current protocol file state and modifications."""

    _protocol_name = Str("untitled")
    _is_modified = Bool(True)
    dock_pane = Instance(DockPane)

    def update_display_name(self):
        _modified_tag = self.modified_tag if self._is_modified else ""
        self.dock_pane.name = PKG_name + "\t-\t" + self._protocol_name + _modified_tag

    def traits_init(self):
        self._loaded_protocol_path = None
        self.modified_tag = " [modified]"

        self.update_display_name()

    @observe("_protocol_name")
    def __protocol_name_changed(self, event):
        logger.debug(f"Protocol name change event: {event}")
        self.update_display_name()

    @observe("_is_modified")
    def _is_modified_changed(self, event):
        logger.debug(f"Protocol modification change event: {event}")
        self.update_display_name()

    def set_loaded_protocol(self, file_path):
        """to set InformationPanel label as the currently loaded protocol file."""
        if file_path:
            path = Path(file_path)
            self._loaded_protocol_path = str(path)
            self._protocol_name = path.stem  # filename without extension
            self._is_modified = False
            logger.info(f"Protocol loaded: {self._protocol_name}")

    def reset(self):
        self._loaded_protocol_path = None
        self._protocol_name = "untitled"
        self._is_modified = True

    def set_saved_protocol(self, file_path):
        """to set InformationPanel label as saved protocol name."""
        if file_path:
            path = Path(file_path)
            self._loaded_protocol_path = str(path)
            self._protocol_name = path.stem
            self._is_modified = False
            logger.critical(f"Protocol saved as: {self._protocol_name}")

    def mark_modified(self, modified=True):
        """mark protocol as modified or unmodified."""
        self._is_modified = modified

    def get_protocol_name(self):
        return self._protocol_name

    def get_protocol_display_name(self):
        """get protocol name with modification status."""
        name = self._protocol_name
        if not self._is_modified or name == "untitled":
            return f"{name}"
        else:
            return f"{name} [modified]"
