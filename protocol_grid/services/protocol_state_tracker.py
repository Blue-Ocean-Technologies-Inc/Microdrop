from pathlib import Path

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


class ProtocolStateTracker:
    """tracks current protocol file state and modifications."""
    
    def __init__(self):
        self._loaded_protocol_path = None
        self._protocol_name = "untitled"
        self._is_modified = False
        self._original_state_hash = None
    
    def set_loaded_protocol(self, file_path):
        """to set InformationPanel label as the currently loaded protocol file."""
        if file_path:
            path = Path(file_path)
            self._loaded_protocol_path = str(path)
            self._protocol_name = path.stem  # filename without extension
            self._is_modified = False
            logger.info(f"Protocol loaded: {self._protocol_name}")
        else:
            self._loaded_protocol_path = None
            self._protocol_name = "untitled"
            self._is_modified = False
    
    def set_saved_protocol(self, file_path):
        """to set InformationPanel label as saved protocol name."""
        if file_path:
            path = Path(file_path)
            self._loaded_protocol_path = str(path)
            self._protocol_name = path.stem
            self._is_modified = False
            logger.info(f"Protocol saved as: {self._protocol_name}")
    
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

    def is_modified(self):
        return self._is_modified
    
    def get_loaded_protocol_path(self):
        return self._loaded_protocol_path
    
    def has_loaded_protocol(self):
        """check if a protocol file is currently loaded."""
        return self._loaded_protocol_path is not None
    
    def reset_to_untitled(self):
        self._loaded_protocol_path = None
        self._protocol_name = "untitled"
        self._is_modified = False