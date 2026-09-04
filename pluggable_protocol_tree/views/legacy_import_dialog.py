# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dialog for picking a legacy MicroDrop device and protocol to import.

Model/view split as elsewhere in this package: ``LegacyImportDialogModel``
is Qt-free and holds the selections; ``LegacyImportDialog`` observes it and
rebuilds its dropdowns. Editing a path field directly overrides the
dropdowns, so protocols kept outside a standard Device Folder still import.
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from pyface.qt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from traits.api import HasTraits, Instance, Int, List, Str, observe

# Microdrop package imports.
from pluggable_protocol_tree.services.legacy_protocol_import import (
    LegacyDeviceFolder,
    scan_for_device_folders,
)
from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
    DEFAULT_DOCUMENTS_DIR_NAME,
    DEFAULT_MICRODROP_DIR_NAME,
    NO_SELECTION_INDEX,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def default_legacy_root_path() -> str:
    """``~/Documents/MicroDrop`` when it exists, else an empty string."""
    candidate = Path.home() / DEFAULT_DOCUMENTS_DIR_NAME / DEFAULT_MICRODROP_DIR_NAME
    return str(candidate) if candidate.is_dir() else ""


def _normalized(path: str) -> Path:
    """Comparison form of a path.

    ``Path`` equality already ignores separator style, redundant ``.``
    segments and (on Windows) case. ``resolve()`` is what additionally
    collapses ``..``, which the editable path fields let a user type and
    which is then persisted, so a stored ``.../Other/../Zika/device.svg``
    still matches its scanned dropdown entry."""
    return Path(path).resolve()


class LegacyImportDialogModel(HasTraits):
    """Selection state for the legacy import dialog."""

    root_path = Str()
    device_folders = List(Instance(LegacyDeviceFolder))
    selected_device_index = Int(NO_SELECTION_INDEX)
    selected_protocol_index = Int(NO_SELECTION_INDEX)
    device_svg_path = Str()
    protocol_path = Str()

    @observe("root_path")
    def _rescan_devices(self, event=None):
        self.device_folders = scan_for_device_folders(self.root_path)
        self.selected_device_index = 0 if self.device_folders else NO_SELECTION_INDEX
        # Trait assignment above is a no-op notification-wise when the
        # index happens to already equal the new value (e.g. both 0), so
        # the device/protocol paths must be re-resolved explicitly rather
        # than relying on the `selected_device_index` observer to fire.
        self._resolve_device_selection()

    @observe("selected_device_index")
    def _apply_device_selection(self, event=None):
        self._resolve_device_selection()

    def _resolve_device_selection(self):
        device = self.selected_device()
        self.device_svg_path = device.device_svg_path if device else ""
        self.selected_protocol_index = (
            0 if device and device.protocol_paths else NO_SELECTION_INDEX
        )
        # Same reasoning as above: the protocol index may already equal
        # the value just assigned, so explicitly resolve `protocol_path`
        # instead of trusting the `selected_protocol_index` observer.
        self._resolve_protocol_path()

    @observe("selected_protocol_index")
    def _apply_protocol_selection(self, event=None):
        self._resolve_protocol_path()

    def _resolve_protocol_path(self):
        device = self.selected_device()
        index = self.selected_protocol_index
        if device is None or not (0 <= index < len(device.protocol_paths)):
            self.protocol_path = ""
            return
        self.protocol_path = device.protocol_paths[index]

    def restore_selection(self, device_svg_path: str, protocol_path: str) -> None:
        """Re-apply a previously used selection after the root scan.

        A path that matches a scanned dropdown entry restores that
        dropdown; one that doesn't (a manual override last time) lands
        back in the editable path field. Files that no longer exist are
        ignored, leaving the scan's own defaults in place."""
        if device_svg_path and Path(device_svg_path).is_file():
            wanted = _normalized(device_svg_path)
            for index, device in enumerate(self.device_folders):
                if _normalized(device.device_svg_path) == wanted:
                    self.selected_device_index = index
                    break
            else:
                self.device_svg_path = device_svg_path
        if protocol_path and Path(protocol_path).is_file():
            wanted = _normalized(protocol_path)
            device = self.selected_device()
            paths = device.protocol_paths if device else []
            for index, path in enumerate(paths):
                if _normalized(path) == wanted:
                    self.selected_protocol_index = index
                    break
            else:
                self.protocol_path = protocol_path

    def selected_device(self):
        if 0 <= self.selected_device_index < len(self.device_folders):
            return self.device_folders[self.selected_device_index]
        return None

    def protocol_names(self) -> list:
        device = self.selected_device()
        if device is None:
            return []
        return [Path(path).name for path in device.protocol_paths]


class LegacyImportDialog(QDialog):
    """Root directory -> device -> protocol, with editable path overrides."""

    def __init__(
        self,
        parent=None,
        initial_root_path="",
        initial_device_svg_path="",
        initial_protocol_path="",
    ):
        super().__init__(parent)
        self.setWindowTitle("Import Legacy Protocol")
        self.model = LegacyImportDialogModel()
        self._build_widgets()
        self._connect_widgets()
        self.model.observe(self._refresh_devices, "device_folders")
        self.model.observe(self._refresh_selected_device, "selected_device_index")
        self.model.observe(self._refresh_selected_protocol, "selected_protocol_index")
        self.model.observe(self._refresh_paths, "device_svg_path,protocol_path")
        self.model.root_path = initial_root_path or default_legacy_root_path()
        self._root_edit.setText(self.model.root_path)
        if initial_device_svg_path or initial_protocol_path:
            self.model.restore_selection(initial_device_svg_path, initial_protocol_path)

    def _build_widgets(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._root_edit = QLineEdit()
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse)
        root_row = QHBoxLayout()
        root_row.addWidget(self._root_edit)
        root_row.addWidget(browse_button)
        form.addRow("MicroDrop folder:", root_row)

        self._device_combo = QComboBox()
        form.addRow("Device:", self._device_combo)

        self._protocol_combo = QComboBox()
        form.addRow("Protocol:", self._protocol_combo)

        self._device_svg_edit = QLineEdit()
        form.addRow("Device SVG:", self._device_svg_edit)

        self._protocol_path_edit = QLineEdit()
        form.addRow("Protocol file:", self._protocol_path_edit)

        layout.addLayout(form)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        self._buttons.button(QDialogButtonBox.Ok).setText("Import")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _connect_widgets(self):
        self._root_edit.editingFinished.connect(
            lambda: setattr(self.model, "root_path", self._root_edit.text())
        )
        self._device_combo.currentIndexChanged.connect(
            lambda index: setattr(self.model, "selected_device_index", index)
        )
        self._protocol_combo.currentIndexChanged.connect(
            lambda index: setattr(self.model, "selected_protocol_index", index)
        )
        self._device_svg_edit.editingFinished.connect(
            lambda: setattr(self.model, "device_svg_path", self._device_svg_edit.text())
        )
        self._protocol_path_edit.editingFinished.connect(
            lambda: setattr(
                self.model, "protocol_path", self._protocol_path_edit.text()
            )
        )

    def _on_browse(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Select MicroDrop or device folder", self.model.root_path
        )
        if chosen:
            self._root_edit.setText(chosen)
            self.model.root_path = chosen

    def _refresh_devices(self, event=None):
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        self._device_combo.addItems(
            [device.name for device in self.model.device_folders]
        )
        self._device_combo.setCurrentIndex(self.model.selected_device_index)
        self._device_combo.blockSignals(False)
        self._refresh_protocols()

    def _refresh_selected_device(self, event=None):
        # Keeps the device combo in step with programmatic index changes
        # (e.g. restoring the last-used selection) -- user-driven changes
        # come *from* the combo, which then shows the value already.
        self._device_combo.blockSignals(True)
        self._device_combo.setCurrentIndex(self.model.selected_device_index)
        self._device_combo.blockSignals(False)
        self._refresh_protocols()

    def _refresh_selected_protocol(self, event=None):
        self._protocol_combo.blockSignals(True)
        self._protocol_combo.setCurrentIndex(self.model.selected_protocol_index)
        self._protocol_combo.blockSignals(False)

    def _refresh_protocols(self, event=None):
        self._protocol_combo.blockSignals(True)
        self._protocol_combo.clear()
        self._protocol_combo.addItems(self.model.protocol_names())
        self._protocol_combo.setCurrentIndex(self.model.selected_protocol_index)
        self._protocol_combo.blockSignals(False)

    def _refresh_paths(self, event=None):
        self._device_svg_edit.setText(self.model.device_svg_path)
        self._protocol_path_edit.setText(self.model.protocol_path)

    def selected_paths(self):
        """``(device_svg_path, protocol_path)`` as currently shown, so a
        hand-edited path wins over the dropdown selection."""
        return (
            self._device_svg_edit.text().strip(),
            self._protocol_path_edit.text().strip(),
        )
