"""Tracks current protocol file state and dirty bookkeeping.

Owned by ``ProtocolTreePane``. Observers on ``protocol_name`` and
``is_modified`` rewrite ``self.dock_pane.name`` so the title reflects
the loaded file and unsaved-changes state.

The pane wires the ``dock_pane`` reference when the dock pane mounts;
in headless tests it stays ``None`` and the observers are no-ops.
"""

from pathlib import Path

from traits.api import Any, Bool, File, HasTraits, Str, observe

from logger.logger_service import get_logger
from pluggable_protocol_tree.consts import PKG_name

logger = get_logger(__name__)


class PluggableProtocolStateTracker(HasTraits):
    protocol_name = Str("untitled")
    loaded_protocol_path = File("")
    is_modified = Bool(False)

    modified_tag = Str(" [modified]")
    pkg_display_name = Str(PKG_name)

    # Duck-typed: anything with a writable `name` attribute. Avoids
    # importing pyface.DockPane just for an Instance() validator and
    # keeps the tracker headlessly testable with a plain stub.
    dock_pane = Any()

    def display_name(self) -> str:
        tag = self.modified_tag if self.is_modified else ""
        return f"{self.pkg_display_name} - {self.protocol_name}{tag}"

    def update_display_name(self) -> None:
        if self.dock_pane is None:
            return
        self.dock_pane.name = self.display_name()

    @observe("protocol_name, is_modified, dock_pane")
    def _on_display_relevant_change(self, event):
        self.update_display_name()

    def set_loaded(self, file_path: str) -> None:
        if not file_path:
            raise ValueError("set_loaded requires a non-empty file path")
        path = Path(file_path)
        self.loaded_protocol_path = str(path)
        self.protocol_name = path.stem
        self.is_modified = False
        logger.info(f"Protocol loaded: {self.protocol_name} ({self.loaded_protocol_path})")

    def set_saved(self, file_path: str) -> None:
        if not file_path:
            raise ValueError("set_saved requires a non-empty file path")
        path = Path(file_path)
        self.loaded_protocol_path = str(path)
        self.protocol_name = path.stem
        self.is_modified = False
        logger.info(f"Protocol saved: {self.protocol_name} ({self.loaded_protocol_path})")

    def reset(self) -> None:
        self.reset_traits(["protocol_name", "loaded_protocol_path", "is_modified"])

    def mark_modified(self) -> None:
        if not self.is_modified:
            self.is_modified = True
