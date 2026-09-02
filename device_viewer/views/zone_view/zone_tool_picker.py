# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Zone tool grid for the zones sidebar: a Paths-mode-picker-style widget of
checkable Draw/Select tool buttons plus Commit/Clear action buttons, bound to
a ``ZoneLayerManager``. Standalone: ``zone_tool_picker_factory`` is the
``CustomEditor`` factory used by ``zones_sidebar.zones_view``."""

# Standard library imports.
from functools import partial

# Enthought library imports.
from pyface.qt.QtCore import QObject, Signal
from pyface.qt.QtWidgets import QGridLayout, QPushButton, QWidget
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.consts import ZONE_DRAW_MODE, ZONE_SELECT_MODE
from device_viewer.models.zones import ZoneLayerManager

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_CHECK,
    ICON_CROP,
    ICON_DELETE,
    ICON_SELECT_All,
)


class ZoneToolPickerSignals(QObject):
    """Qt signal bridge for ``ZoneToolPickerViewModel``."""

    #: Emitted whenever any state the view renders (active tool, pending
    #: selection, edit-in-progress) changes, requiring a UI refresh.
    state_changed = Signal()


class ZoneToolPickerViewModel(HasTraits):
    """Qt-free logic for the zone tool grid: tool toggling and the
    commit/clear actions, plus the button states the view syncs to."""

    #: Zone state the picker edits.
    manager = Instance(ZoneLayerManager)

    #: Signal bridge to the Qt view.
    signals = Instance(ZoneToolPickerSignals)

    def traits_init(self):
        self.signals = ZoneToolPickerSignals()

    # -- Actions --
    def toggle_tool(self, mode):
        """Activate ``mode``, or turn the zone tools off if it is already
        active (clicking the active tool again)."""
        self.manager.mode = "" if self.manager.mode == mode else mode

    def commit(self):
        self.manager.commit_button = True

    def clear(self):
        self.manager.clear_pending_button = True

    # -- Properties for the view --
    @property
    def draw_active(self):
        return self.manager.mode == ZONE_DRAW_MODE

    @property
    def select_active(self):
        return self.manager.mode == ZONE_SELECT_MODE

    @property
    def commit_enabled(self):
        return (
            self.manager.mode == ZONE_DRAW_MODE
            and len(self.manager.pending_electrode_ids) > 0
        )

    @property
    def clear_enabled(self):
        return (
            len(self.manager.pending_electrode_ids) > 0
            or self.manager.editing_region is not None
        )

    @observe(
        "manager:mode, manager:pending_electrode_ids.items, manager:editing_region"
    )
    def _on_underlying_state_changed(self, event):
        """Forward underlying model changes to the Qt view."""
        self.signals.state_changed.emit()


class ZoneToolPicker(QWidget):
    """Draw / Select tool buttons and Commit / Clear action buttons, laid
    out like the Paths ``ModePicker`` grid."""

    def __init__(self, view_model):
        super().__init__()
        self.vm = view_model

        self._init_ui_elements()
        self._layout_ui()
        self._bind_signals()

        self.sync_ui()

    def _init_ui_elements(self):
        self.button_draw = QPushButton(ICON_CROP)
        self.button_draw.setToolTip("Draw zones")
        self.button_draw.setCheckable(True)

        self.button_select = QPushButton(ICON_SELECT_All)
        self.button_select.setToolTip("Select zones")
        self.button_select.setCheckable(True)

        self.button_commit = QPushButton(ICON_CHECK)
        self.button_commit.setToolTip("Commit zone")

        self.button_clear = QPushButton(ICON_DELETE)
        self.button_clear.setToolTip("Clear selection")

    def _layout_ui(self):
        layout = QGridLayout()

        layout.addWidget(self.button_draw, 0, 0)
        layout.addWidget(self.button_select, 0, 1)
        layout.addWidget(self.button_commit, 1, 0)
        layout.addWidget(self.button_clear, 1, 1)
        layout.setColumnStretch(2, 1)

        self.setLayout(layout)

    def _bind_signals(self):
        # View -> ViewModel (user actions)
        self.button_draw.clicked.connect(partial(self.vm.toggle_tool, ZONE_DRAW_MODE))
        self.button_select.clicked.connect(
            partial(self.vm.toggle_tool, ZONE_SELECT_MODE)
        )
        self.button_commit.clicked.connect(self.vm.commit)
        self.button_clear.clicked.connect(self.vm.clear)

        # ViewModel -> View (state updates)
        self.vm.signals.state_changed.connect(self.sync_ui)

    def sync_ui(self):
        """Update checked/enabled state from the view model."""
        self.button_draw.setChecked(self.vm.draw_active)
        self.button_select.setChecked(self.vm.select_active)
        self.button_commit.setEnabled(self.vm.commit_enabled)
        self.button_clear.setEnabled(self.vm.clear_enabled)


def zone_tool_picker_factory(parent, editor):
    """TraitsUI ``CustomEditor`` factory: the editor's object is the manager."""
    return ZoneToolPicker(ZoneToolPickerViewModel(manager=editor.object))
