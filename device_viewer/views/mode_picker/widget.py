# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from functools import partial

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from pyface.tasks.dock_pane import DockPane
from traits.api import HasTraits, Instance, Property, observe

# Microdrop package imports.
from device_viewer.models.main_model import DeviceViewMainModel

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_AUTOMATION, ICON_DRAW, ICON_EDIT


def if_editable(func):
    """Decorator to check if the model is editable before executing the function."""

    def wrapper(self, *args, **kwargs):
        if self.model.editable:
            return func(self, *args, **kwargs)

    return wrapper


# ==========================================
# 1. THE SIGNAL BRIDGE
# ==========================================
class ModePickerSignals(QtCore.QObject):
    """
    Qt Signals for the ModePicker ViewModel.
    """

    # Emitted when the mode or editability changes, requiring a UI refresh
    state_changed = QtCore.Signal()


# ==========================================
# 2. THE VIEW MODEL
# ==========================================
class ModePickerViewModel(HasTraits):
    """
    Handles logic for mode switching, undo/redo, and validation.
    """

    # Dependencies (The "Model" layers this VM wraps)
    model = Instance(DeviceViewMainModel)
    pane = Instance(DockPane)
    signals = Instance(ModePickerSignals)

    current_mode = Property(observe="model.mode")
    mode_name = Property(observe="model.mode_name")
    is_editable = Property(observe="model.editable")

    #: Whether Undo/Redo would change anything: pyface's stack reports an
    #: empty undo_name/redo_name when there is no command on that side.
    can_undo = Property()
    can_redo = Property()

    def traits_init(self):
        self.signals = ModePickerSignals()

    # -- Properties for the View --
    def _get_current_mode(self):
        return self.model.mode

    def _get_mode_name(self):
        return self.model.mode_name

    def _get_is_editable(self):
        return self.model.editable

    def _get_can_undo(self):
        return self.model.editable and self.pane.undo_manager.undo_name != ""

    def _get_can_redo(self):
        return self.model.editable and self.pane.undo_manager.redo_name != ""

    # -- Actions --
    def set_mode(self, mode):
        self.model.flip_mode_activation(mode)

    @if_editable
    def undo(self):
        self.pane.undo()

    @if_editable
    def redo(self):
        self.pane.redo()

    @if_editable
    def reset_electrodes(self):
        self.model.electrodes.clear_electrode_states()

    @if_editable
    def reset_routes(self):
        self.model.routes.clear_routes()

    @observe("model:mode")
    def _on_underlying_mode_changed(self, event):
        """Forward underlying model changes to the Qt View."""
        self.signals.state_changed.emit()

    @observe("pane:undo_manager:stack_updated, model:editable")
    def _on_undo_availability_changed(self, event):
        """Refresh the Undo/Redo buttons after every push, undo, redo or clear."""
        self.signals.state_changed.emit()


# ==========================================
# 3. THE VIEW
# ==========================================
class ModePicker(QtWidgets.QWidget):
    def __init__(self, view_model: "ModePickerViewModel"):
        super().__init__()
        self.vm = view_model

        # Setup UI components
        self._init_ui_elements()
        self._layout_ui()

        # Initial State Sync
        self.sync_ui()

        # Connect Signals
        self._bind_signals()

    def _init_ui_elements(self):
        # Mode Buttons
        self.button_draw = QtWidgets.QPushButton(ICON_DRAW)
        self.button_draw.setToolTip("Draw")
        self.button_draw.setCheckable(True)

        self.button_edit = QtWidgets.QPushButton(ICON_EDIT)
        self.button_edit.setToolTip("Edit")
        self.button_edit.setCheckable(True)

        self.button_autoroute = QtWidgets.QPushButton(ICON_AUTOMATION)
        self.button_autoroute.setToolTip("Autoroute")
        self.button_autoroute.setCheckable(True)

        self.button_channel_edit = QtWidgets.QPushButton("Numbers")
        self.button_channel_edit.setToolTip("Edit Electrode Channels")
        self.button_channel_edit.setCheckable(True)

        # Action Buttons
        self.button_reset_routes = QtWidgets.QPushButton("remove_road")
        self.button_reset_routes.setToolTip("Clear Routes")

        self.button_reset_electrodes = QtWidgets.QPushButton("layers_clear")
        self.button_reset_electrodes.setToolTip("Clear Electrode States")

        self.button_undo = QtWidgets.QPushButton("Undo")
        self.button_undo.setToolTip("Undo")

        self.button_redo = QtWidgets.QPushButton("Redo")
        self.button_redo.setToolTip("Redo")

        self.mode_label = QtWidgets.QLabel()

    def _layout_ui(self):
        btn_layout = QtWidgets.QGridLayout()

        # Row 1: Mode selection
        btn_layout.addWidget(self.button_draw, 0, 0)
        btn_layout.addWidget(self.button_edit, 0, 1)
        btn_layout.addWidget(self.button_autoroute, 0, 2)
        btn_layout.addWidget(self.button_channel_edit, 0, 3)

        # Row 2: Actions
        btn_layout.addWidget(self.button_reset_electrodes, 1, 0)
        btn_layout.addWidget(self.button_reset_routes, 1, 1)
        btn_layout.addWidget(self.button_undo, 1, 2)
        btn_layout.addWidget(self.button_redo, 1, 3)

        # Stretch
        btn_layout.setColumnStretch(4, 1)

        # Main layout
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.mode_label)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _bind_signals(self):
        # View -> ViewModel (User Actions)
        self.button_draw.clicked.connect(partial(self.vm.set_mode, "draw"))
        self.button_edit.clicked.connect(partial(self.vm.set_mode, "edit"))
        self.button_autoroute.clicked.connect(partial(self.vm.set_mode, "auto"))
        self.button_channel_edit.clicked.connect(
            partial(self.vm.set_mode, "channel-edit")
        )

        self.button_reset_routes.clicked.connect(self.vm.reset_routes)
        self.button_reset_electrodes.clicked.connect(self.vm.reset_electrodes)
        self.button_undo.clicked.connect(self.vm.undo)
        self.button_redo.clicked.connect(self.vm.redo)

        # ViewModel -> View (State Updates)
        self.vm.signals.state_changed.connect(self.sync_ui)

    def sync_ui(self):
        """Update button checked states and label based on VM state."""
        current_mode = self.vm.current_mode

        self.button_draw.setChecked(current_mode in ("draw", "edit-draw"))
        self.button_edit.setChecked(current_mode == "edit")
        self.button_autoroute.setChecked(current_mode == "auto")
        self.button_channel_edit.setChecked(current_mode == "channel-edit")

        self.button_undo.setEnabled(self.vm.can_undo)
        self.button_redo.setEnabled(self.vm.can_redo)

        self.mode_label.setText(f"Mode: {self.vm.mode_name}")
